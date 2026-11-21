"""The account: created once at setup, then username and password login with a lockout."""

import re
from datetime import datetime, timedelta

from server.store.db import Db

from .passwords import check_password, hash_password

USERNAME = re.compile(r"^[a-z][a-z0-9_-]{2,31}$")
MIN_PASSWORD = 10
MAX_FAILURES = 5
LOCK_FOR = timedelta(minutes=15)
WRONG = "wrong username or password"
# Checked when the username is unknown, so timing does not tell which part was wrong.
_DUMMY = hash_password("not a real password")


class AuthError(Exception):
    """Safe to show at the login screen."""


def user_count(db: Db) -> int:
    return db.conn.execute("select count(*) from users").fetchone()[0]


def create_user(db: Db, username: str, password: str, now: datetime) -> str:
    if user_count(db):
        raise AuthError("an account already exists")
    if not USERNAME.match(username):
        raise AuthError(
            "username: 3 to 32 lower-case letters, digits, - or _, starting with a letter"
        )
    if len(password) < MIN_PASSWORD:
        raise AuthError(f"password: at least {MIN_PASSWORD} characters")
    with db.conn:
        db.conn.execute(
            "insert into users (id, username, password_hash, created_at) values (?,?,?,?)",
            (username, username, hash_password(password), now.isoformat()),
        )
    return username


def authenticate(db: Db, username: str, password: str, now: datetime) -> str:
    row = db.conn.execute(
        "select id, password_hash, failed_logins, locked_until from users where username=?",
        (username,),
    ).fetchone()
    if row is None:
        check_password(_DUMMY, password)
        raise AuthError(WRONG)
    uid, stored, failures, locked_until = row
    if locked_until and datetime.fromisoformat(locked_until) > now:
        raise AuthError("locked, try again later")
    if not check_password(stored, password):
        failures += 1
        lock = (now + LOCK_FOR).isoformat() if failures >= MAX_FAILURES else None
        with db.conn:
            db.conn.execute(
                "update users set failed_logins=?, locked_until=? where id=?",
                (0 if lock else failures, lock, uid),
            )
        raise AuthError(WRONG)
    with db.conn:
        db.conn.execute("update users set failed_logins=0, locked_until=null where id=?", (uid,))
    return uid
