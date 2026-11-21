from server.api.approvals import ApprovalBroker
from server.locks import user_lock


def test_cannot_answer_another_accounts_approval():
    b = ApprovalBroker()
    aid = b.request("u_a")
    assert b.resolve(aid, True, user_id="u_b") is False
    assert b.resolve(aid, True, user_id="u_a") is True


def test_locks_are_per_account():
    assert user_lock("pending", "u_a") is user_lock("pending", "u_a")
    assert user_lock("pending", "u_a") is not user_lock("pending", "u_b")
