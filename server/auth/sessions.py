"""Server-side sessions: a random token in an HttpOnly cookie, only its SHA-256 in SQLite."""

import hashlib
import secrets
from datetime import datetime, timedelta

from server.store.db import Db

IDLE = timedelta(days=14)  # sliding: each use moves expiry forward
HARD = timedelta(days=30)  # never past this, however often it is used
TOUCH_EVERY = timedelta(minutes=1)


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_session(db: Db, user_id: str, now: datetime, user_agent: str | None) -> str:
    token = secrets.token_urlsafe(32)
    with db.conn:
        db.conn.execute(
            "insert into sessions (token_hash, user_id, created_at, last_seen, expires_at,"
            " hard_expires_at, user_agent) values (?,?,?,?,?,?,?)",
            (
                _digest(token), user_id, now.isoformat(), now.isoformat(),
                (now + IDLE).isoformat(), (now + HARD).isoformat(), (user_agent or "")[:200],
            ),
        )  # fmt: skip
    return token


def resolve(db: Db, token: str | None, now: datetime) -> str | None:
    """The session's user, sliding its expiry; None (and the row removed) once expired."""
    if not token:
        return None
    digest = _digest(token)
    row = db.conn.execute(
        "select user_id, last_seen, expires_at, hard_expires_at from sessions where token_hash=?",
        (digest,),
    ).fetchone()
    if row is None:
        return None
    user_id, last_seen, expires, hard = row
    if now >= datetime.fromisoformat(expires) or now >= datetime.fromisoformat(hard):
        revoke(db, token)
        return None
    if now - datetime.fromisoformat(last_seen) >= TOUCH_EVERY:
        new_expiry = min(now + IDLE, datetime.fromisoformat(hard))
        with db.conn:
            db.conn.execute(
                "update sessions set last_seen=?, expires_at=? where token_hash=?",
                (now.isoformat(), new_expiry.isoformat(), digest),
            )
    return user_id


def expires_at(db: Db, token: str) -> datetime | None:
    row = db.conn.execute(
        "select expires_at from sessions where token_hash=?", (_digest(token),)
    ).fetchone()
    return datetime.fromisoformat(row[0]) if row else None


def revoke(db: Db, token: str) -> None:
    with db.conn:
        db.conn.execute("delete from sessions where token_hash=?", (_digest(token),))
