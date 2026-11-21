"""LLM judge for fuzzy qualities (helpfulness, resume quality): binary PASS or FAIL with a reason."""

from server.agent.adapters import Adapter

PROMPT = """You grade one answer from a personal assistant. Reply with PASS or FAIL on the first
line, then one sentence of reason. Grade only against the rubric.

Rubric: {rubric}

Question: {question}

Answer: {answer}"""


def judge(adapter: Adapter, question: str, answer: str, rubric: str) -> tuple[bool, str]:
    text = adapter.complete(
        [{"role": "user", "content": PROMPT.format(rubric=rubric, question=question, answer=answer)}],
        [],
    ).text or ""
    first, _, rest = text.strip().partition("\n")
    head = first.strip().lower()
    verdict = head.startswith("pass")
    reason = rest.strip() or first.partition(":")[2].strip()
    return verdict, reason
