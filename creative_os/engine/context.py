from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from creative_os.foundation.knowledge import KnowledgeItem
from creative_os.foundation.state import ProjectState
from creative_os.foundation.task import Task


class ContextBoundaryError(ValueError):
    pass


@dataclass(slots=True)
class Context:
    user_input: str
    task: Task
    state: ProjectState
    knowledge: list[KnowledgeItem]
    domain_rules: list[str]
    created_at: datetime
    size_chars: int


class ContextBuilder:
    def __init__(self, max_items: int = 8, max_chars: int = 12000) -> None:
        self.max_items = max_items
        self.max_chars = max_chars

    def build(
        self,
        user_input: str,
        task: Task,
        state: ProjectState,
        retrieved: list[KnowledgeItem],
        domain: object,
    ) -> Context:
        domain_name = str(getattr(domain, "name", ""))
        if domain_name and task.domain != domain_name:
            raise ContextBoundaryError(f"Task domain does not match domain package: {task.domain} != {domain_name}")
        if task.domain != state.active_domain:
            raise ContextBoundaryError(f"Task domain does not match active state domain: {task.domain} != {state.active_domain}")
        if task.id != state.current_task_id:
            raise ContextBoundaryError(f"Task id does not match state current task: {task.id} != {state.current_task_id}")

        rules = list(getattr(domain, "rules", []))
        knowledge = retrieved[: self.max_items]
        size_chars = self._estimate_size(user_input, task, state, knowledge, rules)
        if size_chars > self.max_chars:
            raise ContextBoundaryError(f"Context too large: {size_chars} > {self.max_chars}")
        return Context(
            user_input=user_input,
            task=task,
            state=state,
            knowledge=knowledge,
            domain_rules=rules,
            created_at=datetime.now(timezone.utc),
            size_chars=size_chars,
        )

    def _estimate_size(
        self,
        user_input: str,
        task: Task,
        state: ProjectState,
        knowledge: list[KnowledgeItem],
        rules: list[str],
    ) -> int:
        knowledge_size = sum(len(item.title) + len(item.body) for item in knowledge)
        rules_size = sum(len(rule) for rule in rules)
        state_size = sum(len(str(value)) for value in state.compact().values())
        task_size = len(task.title) + len(task.goal) + len(task.kind) + len(task.domain)
        return len(user_input) + task_size + state_size + knowledge_size + rules_size
