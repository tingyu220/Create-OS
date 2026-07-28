from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum, StrEnum


class TaskLifecycleError(ValueError):
    pass


class TaskStatus(StrEnum):
    PENDING = "pending"
    DOING = "doing"
    DONE = "done"
    BLOCKED = "blocked"


class TaskPriority(IntEnum):
    LOW = 1
    NORMAL = 2
    HIGH = 3


@dataclass(slots=True)
class Task:
    id: str
    title: str
    kind: str
    domain: str
    goal: str
    tags: set[str] = field(default_factory=set)
    status: TaskStatus = TaskStatus.PENDING
    priority: TaskPriority = TaskPriority.NORMAL
    owner: str | None = None
    dependencies: list[str] = field(default_factory=list)

    def start(self) -> "Task":
        return self.with_status(TaskStatus.DOING)

    def complete(self) -> "Task":
        return self.with_status(TaskStatus.DONE)

    def block(self) -> "Task":
        return self.with_status(TaskStatus.BLOCKED)

    def with_status(self, status: TaskStatus) -> "Task":
        if status not in self._allowed_next_statuses(self.status):
            raise TaskLifecycleError(f"Invalid Task status transition: {self.status} -> {status}")
        return Task(
            id=self.id,
            title=self.title,
            kind=self.kind,
            domain=self.domain,
            goal=self.goal,
            tags=set(self.tags),
            status=status,
            priority=self.priority,
            owner=self.owner,
            dependencies=list(self.dependencies),
        )

    def is_runnable(self, completed_task_ids: set[str]) -> bool:
        return self.status == TaskStatus.PENDING and all(dependency in completed_task_ids for dependency in self.dependencies)

    def _allowed_next_statuses(self, current: TaskStatus) -> set[TaskStatus]:
        return {
            TaskStatus.PENDING: {TaskStatus.DOING, TaskStatus.BLOCKED},
            TaskStatus.DOING: {TaskStatus.DONE, TaskStatus.BLOCKED},
            TaskStatus.DONE: set(),
            TaskStatus.BLOCKED: {TaskStatus.PENDING},
        }[current]


class TaskStore:
    def __init__(self) -> None:
        self._tasks: dict[str, Task] = {}

    def add(self, task: Task) -> None:
        if task.id in self._tasks:
            raise ValueError(f"Task already exists: {task.id}")
        self._validate_dependencies(task)
        self._tasks[task.id] = task

    def update(self, task: Task) -> None:
        if task.id not in self._tasks:
            raise KeyError(task.id)
        self._validate_dependencies(task)
        self._tasks[task.id] = task

    def get(self, task_id: str) -> Task:
        return self._tasks[task_id]

    def items(self) -> list[Task]:
        return list(self._tasks.values())

    def runnable(self) -> list[Task]:
        completed = {task.id for task in self._tasks.values() if task.status == TaskStatus.DONE}
        runnable = [task for task in self._tasks.values() if task.is_runnable(completed)]
        return sorted(runnable, key=lambda task: (-task.priority, task.id))

    def _validate_dependencies(self, task: Task) -> None:
        missing = [dependency for dependency in task.dependencies if dependency not in self._tasks and dependency != task.id]
        if missing:
            raise ValueError(f"Unknown Task dependencies: {', '.join(sorted(missing))}")
