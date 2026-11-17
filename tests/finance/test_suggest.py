import json
from datetime import date, datetime

from server.agent.adapters.base import Reply
from server.agent.adapters.fake import FakeAdapter
from server.finance.suggest import queue_suggestions, suggest_categories, suggest_types
from server.intake.approve import approve_bundle
from server.integrations.data_repo.loader import load_data
from server.store.db import Db

NOW = datetime(2031, 4, 6, 9, 0)


def reply(items):
    return FakeAdapter([Reply(text=json.dumps({"items": items}))])


def test_drops_unknown_category_and_bad_match(ctx):
    data = load_data(ctx.config.data_repo)
    adapter = reply(
        [
            {"description": "FRESHMART #12 TORONTO", "match": "Freshmart", "category": "groceries"},
            {"description": "ODD SHOP", "match": "Odd Shop", "category": "not-a-category"},
            {"description": "AB LTD", "match": "ab", "category": "other"},
            {"description": "ZED STORE", "match": "Nowhere", "category": "other"},
        ]
    )
    out = suggest_categories(
        ["FRESHMART #12 TORONTO", "ODD SHOP", "AB LTD", "ZED STORE"], data, adapter
    )
    assert [(s.match, s.category) for s in out] == [("Freshmart", "groceries")]


def test_types_drop_unknown_tag():
    adapter = reply(
        [{"type_text": "Bill payment", "tag": "debt_payment"}, {"type_text": "X", "tag": "nope"}]
    )
    out = suggest_types(["Bill payment", "X"], adapter)
    assert [(t.type_text, t.tag) for t in out] == [("Bill payment", "debt_payment")]


def test_queue_dedupes_pending(ctx):
    data = load_data(ctx.config.data_repo)
    db = Db(":memory:")
    for _ in range(2):
        cats = suggest_categories(
            ["FRESHMART #12"],
            data,
            reply(
                [{"description": "FRESHMART #12", "match": "Freshmart", "category": "groceries"}]
            ),
        )
        queue_suggestions(db, cats, [], "test", NOW)
    cards = db.list_pending()
    assert len(cards) == 1
    assert len(cards[0].payload["items"]) == 1


def test_approve_categories_card_writes_rule(ctx):
    repo = ctx.config.data_repo
    data = load_data(repo)
    db = Db(":memory:")
    cats = suggest_categories(
        ["FRESHMART #12"],
        data,
        reply([{"description": "FRESHMART #12", "match": "Freshmart", "category": "groceries"}]),
    )
    queue_suggestions(db, cats, [], "test", NOW)
    approve_bundle(db.list_pending()[0].id, None, repo, db, date(2031, 4, 6))
    rule = load_data(repo).merchant_rules.rules[-1]
    assert (rule.match, rule.category, str(rule.approved)) == (
        "Freshmart",
        "groceries",
        "2031-04-06",
    )


def test_approve_types_card_writes_type_rule(ctx):
    repo = ctx.config.data_repo
    db = Db(":memory:")
    types = suggest_types(
        ["Bill payment"], reply([{"type_text": "Bill payment", "tag": "debt_payment"}])
    )
    queue_suggestions(db, [], types, "test", NOW)
    approve_bundle(db.list_pending()[0].id, None, repo, db, date(2031, 4, 6))
    t = load_data(repo).transaction_types.types[-1]
    assert (t.bank, t.type_text, t.tag) == ("scotiabank", "Bill payment", "debt_payment")


def test_items_matched_by_line_number(ctx):
    data = load_data(ctx.config.data_repo)
    adapter = reply(
        [
            {
                "n": 2,
                "description": "freshmart (edited)",
                "match": "Freshmart",
                "category": "groceries",
            }
        ]
    )
    out = suggest_categories(["CORNER STORE 1", "FRESHMART #12"], data, adapter)
    assert [(s.description, s.match) for s in out] == [("FRESHMART #12", "Freshmart")]


def test_same_merchant_other_match_not_queued_twice(ctx):
    data = load_data(ctx.config.data_repo)
    db = Db(":memory:")
    for match in ("Freshmart", "Freshmart #12"):
        cats = suggest_categories(
            ["FRESHMART #12"],
            data,
            reply(
                [{"n": 1, "description": "FRESHMART #12", "match": match, "category": "groceries"}]
            ),
        )
        queue_suggestions(db, cats, [], "test", NOW)
    assert sum(len(c.payload["items"]) for c in db.list_pending()) == 1


def test_same_match_other_store_not_queued_twice(ctx):
    data = load_data(ctx.config.data_repo)
    db = Db(":memory:")
    items = [
        {
            "n": 1,
            "description": "FRESHMART #12 TORONTO",
            "match": "Freshmart",
            "category": "groceries",
        },
        {
            "n": 2,
            "description": "FRESHMART #13 OTTAWA",
            "match": "Freshmart",
            "category": "groceries",
        },
    ]
    cats = suggest_categories(["FRESHMART #12 TORONTO", "FRESHMART #13 OTTAWA"], data, reply(items))
    queue_suggestions(db, cats, [], "test", NOW)
    assert sum(len(c.payload["items"]) for c in db.list_pending()) == 1


def test_pending_merchants_not_asked_again(ctx):
    from server.finance.suggest import not_pending

    data = load_data(ctx.config.data_repo)
    db = Db(":memory:")
    cats = suggest_categories(
        ["FRESHMART #12"],
        data,
        reply(
            [
                {
                    "n": 1,
                    "description": "FRESHMART #12",
                    "match": "Freshmart",
                    "category": "groceries",
                }
            ]
        ),
    )
    queue_suggestions(db, cats, [], "test", NOW)
    assert not_pending(db, ["FRESHMART #12", "ZED STORE"]) == ["ZED STORE"]
