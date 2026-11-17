import json

import pytest

from server.agent.adapters import AdapterError
from server.agent.adapters.base import Reply
from server.agent.adapters.fake import FakeAdapter
from server.intake.draft import DraftProfile
from server.intake.extract import MAX_CHARS, extract_resume
from server.intake.readers import IntakeError

SOURCE = "Jane Example. Acme Widgets, Engineer, 2022-03 to now. Cut report time by 40%."


def draft_json(**over):
    d = {
        "profile": {"name": "Jane Example", "emails": ["jane@example.test"]},
        "education": [],
        "domains": ["Backend"],
        "jobs": [
            {
                "company": "Acme Widgets",
                "position": "Engineer",
                "start": "2022-03",
                "highlights": [
                    {
                        "text": "Cut report time",
                        "numbers": [
                            {"value": "40", "unit": "percent", "label": "faster"},
                            {"value": "90", "unit": "percent", "label": "invented"},
                        ],
                    }
                ],
            }
        ],
    }
    d.update(over)
    return json.dumps(d)


def test_valid_json_in_prose_becomes_a_draft_and_invented_numbers_drop():
    adapter = FakeAdapter([Reply(text="Here you go:\n```json\n" + draft_json() + "\n```")])
    draft, warnings = extract_resume(SOURCE, adapter, [])
    assert draft.jobs[0].company == "Acme Widgets"
    numbers = draft.jobs[0].highlights[0].numbers
    assert [str(n.value) for n in numbers] == ["40"]
    assert any("1 number" in w for w in warnings)


def test_invalid_json_is_retried_once_then_fails_readably():
    adapter = FakeAdapter([Reply(text="sorry"), Reply(text="still no")])
    with pytest.raises(IntakeError):
        extract_resume(SOURCE, adapter, [])
    assert len(adapter.calls) == 2
    ok = FakeAdapter([Reply(text="sorry"), Reply(text=draft_json())])
    assert extract_resume(SOURCE, ok, [])[0].profile.name == "Jane Example"


def test_provider_error_is_readable():
    class Down:
        def complete(self, messages, tools):
            raise AdapterError("provider reports no credits remaining")

    with pytest.raises(IntakeError, match="no credits"):
        extract_resume(SOURCE, Down(), [])


def test_long_text_is_cut_with_warning():
    adapter = FakeAdapter([Reply(text=draft_json())])
    _, warnings = extract_resume("x" * (MAX_CHARS + 5000), adapter, [])
    assert "text truncated" in warnings
    assert len(adapter.calls[0][1]["content"]) <= MAX_CHARS + 200


def test_year_only_dates_are_normalised_and_profile_has_no_forbidden_fields():
    j = json.loads(draft_json())
    j["jobs"][0]["start"] = "2022"
    draft, _ = extract_resume(SOURCE, FakeAdapter([Reply(text=json.dumps(j))]), [])
    assert draft.jobs[0].start == "2022-01"
    assert not {"date_of_birth", "addresses"} & set(DraftProfile.model_fields)


def test_null_string_fields_from_the_model_are_accepted():
    j = json.loads(draft_json())
    j["jobs"][0]["location"] = None
    j["education"] = [
        {"level": "bachelor", "institution": "X", "program": "Y", "city": None, "grade": None}
    ]
    draft, _ = extract_resume(SOURCE, FakeAdapter([Reply(text=json.dumps(j))]), [])
    assert draft.jobs[0].location == "" and draft.education[0].city == ""


def test_highlight_text_with_an_unfounded_number_is_dropped():
    j = json.loads(draft_json())
    j["jobs"][0]["highlights"] = [
        {"text": "Cut report time by 40%"},
        {"text": "Cut latency by 90%"},
        {"text": "Led the team"},
    ]
    draft, warnings = extract_resume(SOURCE, FakeAdapter([Reply(text=json.dumps(j))]), [])
    assert [h.text for h in draft.jobs[0].highlights] == ["Cut report time by 40%", "Led the team"]
    assert any("not found in the resume" in w for w in warnings)


def test_number_match_is_by_value_not_by_stripped_digits():
    src = "Grew revenue 1.5x and processed 2 million requests"
    j = json.loads(draft_json())
    j["jobs"][0]["highlights"] = [
        {
            "text": "Grew revenue",
            "numbers": [
                {"value": "15", "unit": "x", "label": "wrong"},
                {"value": "1.5", "unit": "x", "label": "right"},
                {"value": "2", "unit": "million", "label": "right"},
            ],
        }
    ]
    draft, _ = extract_resume(src, FakeAdapter([Reply(text=json.dumps(j))]), [])
    assert [str(n.value) for n in draft.jobs[0].highlights[0].numbers] == ["1.5", "2"]


def test_odd_types_and_dates_from_the_model_do_not_crash():
    j = json.loads(draft_json())
    j["jobs"][0].update({"start": 2019, "end": "Present"})
    j["profile"]["location"] = {"city": None, "country": "Testland"}
    j["education"] = [{"level": "bachelor", "institution": "X", "program": "Y", "end": "2019"}]
    draft, _ = extract_resume(SOURCE, FakeAdapter([Reply(text=json.dumps(j))]), [])
    assert draft.jobs[0].start == "2019-01" and draft.jobs[0].end is None
    assert draft.education[0].end == "2019-12"
