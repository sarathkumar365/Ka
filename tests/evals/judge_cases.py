"""About 10 answers graded by hand, to check the judge agrees with the owner. Parked: cases to write."""

from dataclasses import dataclass


@dataclass
class JudgeCase:
    question: str
    answer: str
    rubric: str
    human_pass: bool


JUDGE_CASES: list[JudgeCase] = []
