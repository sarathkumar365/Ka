"""Run a background job once for every account, each in its own account view."""

import logging
from collections.abc import Callable

from server.config import Config
from server.locks import user_lock
from server.store.db import Db
from server.users import user_config

log = logging.getLogger(__name__)


def account_ids(cfg: Config) -> list[str]:
    db = Db.system(cfg.db_path)
    try:
        return [r[0] for r in db.conn.execute("select id from users order by created_at, id")]
    finally:
        db.conn.close()


def for_each_account(cfg: Config, job: Callable[[Config], None], name: str) -> Callable[[], None]:
    """A scheduler callable. One account failing or still busy never stops the others."""

    def run() -> None:
        for user in account_ids(cfg):
            lock = user_lock(name, user)
            if not lock.acquire(blocking=False):
                continue  # the previous run for this account is still going
            try:
                job(user_config(cfg, user))
            except Exception:  # a background job must never take the server down
                log.exception("%s failed for %s", name, user)
            finally:
                lock.release()

    return run
