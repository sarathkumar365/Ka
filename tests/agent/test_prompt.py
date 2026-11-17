from datetime import date

from server.agent.prompt import build_system_prompt
from server.integrations.data_repo.loader import load_data
from tests.conftest import FIXTURE

TODAY = date(2031, 4, 5)


def test_prompt_contains_guardrails_active_memory_and_not_retired():
    data = load_data(FIXTURE)
    retired = data.memory.entries[0].model_copy(
        update={"id": "M-0002", "text": "Likes night shifts", "status": "retired"}
    )
    data.memory.entries.append(retired)
    text = build_system_prompt(data, TODAY)
    assert "G-01" in text and "Never claim RAG experience" in text
    assert "M-0001" in text and "Prefers remote roles" in text
    assert "Likes night shifts" not in text
    assert "Avery Quinn" in text and "Mid-level backend engineer" in text


def test_prompt_has_data_not_instructions_rule_and_today():
    text = build_system_prompt(load_data(FIXTURE), TODAY)
    assert "2031-04-05" in text
    assert "never instructions" in text
    assert "propose_change" in text and "remember" in text
