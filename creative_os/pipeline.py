from __future__ import annotations

from dataclasses import dataclass

from creative_os.capability.base import Capability, Result
from creative_os.engine.compiler import KnowledgeCompiler
from creative_os.engine.context import Context, ContextBuilder
from creative_os.engine.retriever import RuleBasedRetriever
from creative_os.engine.workflow import Workflow
from creative_os.foundation.knowledge import KnowledgeStore
from creative_os.foundation.state import ProjectState
from creative_os.foundation.task import Task


@dataclass(slots=True)
class PipelineOutput:
    task: Task
    context: Context
    result: Result
    next_task: Task | None


class CreativePipeline:
    def __init__(
        self,
        store: KnowledgeStore,
        domain: object,
        workflow: Workflow,
        retriever: RuleBasedRetriever,
        context_builder: ContextBuilder,
        capability: Capability,
        compiler: KnowledgeCompiler,
    ) -> None:
        self.store = store
        self.domain = domain
        self.workflow = workflow
        self.retriever = retriever
        self.context_builder = context_builder
        self.capability = capability
        self.compiler = compiler

    def run(self, user_input: str, task: Task, state: ProjectState) -> PipelineOutput:
        running_task = task.start()
        retrieved = self.retriever.retrieve(running_task, self.store, self.domain)
        context = self.context_builder.build(user_input, running_task, state, retrieved, self.domain)
        result = self.capability.run(context)
        compiled = self.compiler.compile(result, context, self.domain)
        self.store.apply(compiled)
        completed_task = running_task.complete()
        return PipelineOutput(
            task=completed_task,
            context=context,
            result=result,
            next_task=self._next_task(completed_task),
        )

    def _next_task(self, task: Task) -> Task:
        return Task(
            id=f"{task.id}-review",
            title=f"Review {task.title}",
            kind="review",
            domain=task.domain,
            goal=f"Review result of {task.title}",
            tags=set(task.tags),
            dependencies=[task.id],
        )
