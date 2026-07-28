from __future__ import annotations

from creative_os.capability.base import Issue, Result, ResultKind
from creative_os.engine.context import Context
from creative_os.foundation.task import Task, TaskPriority


class RuleFirstReviewCapability:
    def run(self, context: Context) -> Result:
        issues: list[Issue] = []
        follow_up_tasks: list[Task] = []
        if not context.knowledge:
            issues.append(
                Issue(
                    code="missing_retrieved_knowledge",
                    message="Review requires retrieved Knowledge for consistency checks.",
                    severity="high",
                )
            )
            follow_up_tasks.append(
                Task(
                    id=f"{context.task.id}-fix-missing-knowledge",
                    title="补齐 Review 所需 Knowledge",
                    kind="fix",
                    domain=context.task.domain,
                    goal="为 Review 任务补齐必要 Knowledge 后重新审核",
                    tags=set(context.task.tags),
                    priority=TaskPriority.HIGH,
                    owner="system",
                    dependencies=[context.task.id],
                )
            )
        content = "Review completed." if not issues else "Review found issues."
        return Result(content=content, kind=ResultKind.REVIEW, issues=issues, follow_up_tasks=follow_up_tasks)
