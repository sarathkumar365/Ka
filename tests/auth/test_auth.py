import hashlib
from datetime import datetime, timedelta

import pytest

from server.auth.passwords import check_password, hash_password
from server.auth.ratelimit import LoginLimiter
from server.auth.sessions import new_session, resolve, revoke
from server.auth.users import AuthError, authenticate, create_user
from server.store.db import Db

T0 = datetime(2031, 4, 5, 12, 0)
PW = "correct horse 1"


@pytest.fixture
def sysdb():
    return Db.system(":memory:")


def test_password_is_hashed_and_checked():
    h = hash_password(PW)
    assert "correct" not in h and check_password(h, PW) and not check_password(h, "x")
    assert not check_password("not-a-hash", PW)


def test_session_slides_but_never_passes_hard_max(sysdb):
    uid = create_user(sysdb, "avery", PW, T0)
    tok = new_session(sysdb, uid, T0, "test")
    assert resolve(sysdb, tok, T0 + timedelta(days=13)) == uid
    assert resolve(sysdb, tok, T0 + timedelta(days=26)) == uid  # slid
    assert resolve(sysdb, tok, T0 + timedelta(days=31)) is None  # hard max
    digest = hashlib.sha256(tok.encode()).hexdigest()
    assert sysdb.conn.execute("select count(*) from sessions where token_hash=?", (digest,)).fetchone()[0] == 0


def test_idle_session_expires(sysdb):
    uid = create_user(sysdb, "avery", PW, T0)
    tok = new_session(sysdb, uid, T0, "test")
    assert resolve(sysdb, tok, T0 + timedelta(days=15)) is None


def test_token_is_never_stored_raw_and_revoke_ends_it(sysdb):
    uid = create_user(sysdb, "avery", PW, T0)
    tok = new_session(sysdb, uid, T0, "test")
    assert sysdb.conn.execute("select count(*) from sessions where token_hash=?", (tok,)).fetchone()[0] == 0
    revoke(sysdb, tok)
    assert resolve(sysdb, tok, T0) is None


def test_lockout_after_five_failures(sysdb):
    create_user(sysdb, "avery", PW, T0)
    for _ in range(5):
        with pytest.raises(AuthError):
            authenticate(sysdb, "avery", "bad", T0)
    with pytest.raises(AuthError, match="locked"):
        authenticate(sysdb, "avery", PW, T0)
    assert authenticate(sysdb, "avery", PW, T0 + timedelta(minutes=16)) == "avery"


def test_unknown_user_gets_the_same_message(sysdb):
    with pytest.raises(AuthError, match="wrong username or password"):
        authenticate(sysdb, "nobody", PW, T0)


def test_second_account_and_bad_input_are_refused(sysdb):
    with pytest.raises(AuthError):
        create_user(sysdb, "A", PW, T0)
    with pytest.raises(AuthError):
        create_user(sysdb, "avery", "short", T0)
    create_user(sysdb, "avery", PW, T0)
    with pytest.raises(AuthError):
        create_user(sysdb, "blake", "correct horse 2", T0)


def test_login_limiter_window():
    lim = LoginLimiter(max_attempts=2, window=timedelta(minutes=10))
    assert lim.allow("c", T0) and lim.allow("c", T0) and not lim.allow("c", T0)
    assert lim.allow("c", T0 + timedelta(minutes=11))
