"""战斗专家的范围、冻结请求与自由正文结果契约。"""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class CombatScope:
    chapter_numbers: tuple[int, ...]
    purpose: str

    def __post_init__(self):
        if (not isinstance(self.chapter_numbers, tuple)
                or any(type(number) is not int or number <= 0 for number in self.chapter_numbers)
                or len(set(self.chapter_numbers)) != len(self.chapter_numbers)
                or not isinstance(self.purpose, str) or not self.purpose.strip()):
            raise ValueError("combat_scope_invalid")


@dataclass(frozen=True, slots=True)
class CombatRequest:
    project_id: str
    session_id: str
    job_id: str
    instruction: str
    scope: CombatScope
    confirmed_story: dict | None
    sources: tuple[dict, ...]


@dataclass(frozen=True, slots=True)
class CombatResult:
    result_id: str
    project_id: str
    job_id: str
    verdict: Literal["combat", "setup", "noncombat", "insufficient"]
    reply: str
    alternatives: tuple[str, ...]
    foreshadowing: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    unknowns: tuple[str, ...]
    scope: CombatScope

    def __post_init__(self):
        if not isinstance(self.verdict, str) or self.verdict not in {"combat", "setup", "noncombat", "insufficient"}:
            raise ValueError("combat_verdict_invalid")
