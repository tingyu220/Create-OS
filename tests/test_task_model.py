import pytest

from creative_os.foundation.task import (
    Task,
    TaskLifecycleError,
    TaskPriority,
    TaskStatus,
    TaskStore,
)


def test_task_lifecycle_allows_only_valid_transitions_and_preserves_owner():
    task = Task(
        id="t1",
        title="整理 Knowledge",
        kind="knowledge",
        domain="core",
        goal="完成 Knowledge 模型",
        owner="system",
    )

    with pytest.raises(TaskLifecycleError):
        task.complete()

    doing = task.start()
    done = doing.complete()

    assert done.status == TaskStatus.DONE
    assert done.owner == "system"


def test_task_dependencies_must_be_done_before_task_is_runnable():
    store = TaskStore()
    store.add(Task(id="t1", title="M1", kind="knowledge", domain="core", goal="完成 M1"))
    store.add(
        Task(
            id="t2",
            title="M2",
            kind="project",
            domain="core",
            goal="完成 M2",
            dependencies=["t1"],
            priority=TaskPriority.HIGH,
        )
    )

    assert [task.id for task in store.runnable()] == ["t1"]

    store.update(store.get("t1").start().complete())

    assert [task.id for task in store.runnable()] == ["t2"]


def test_task_store_orders_runnable_tasks_by_priority_then_id():
    store = TaskStore()
    store.add(Task(id="t-low", title="低优先级", kind="doc", domain="core", goal="低", priority=TaskPriority.LOW))
    store.add(Task(id="t-high-b", title="高优先级 B", kind="doc", domain="core", goal="高", priority=TaskPriority.HIGH))
    store.add(Task(id="t-high-a", title="高优先级 A", kind="doc", domain="core", goal="高", priority=TaskPriority.HIGH))

    assert [task.id for task in store.runnable()] == ["t-high-a", "t-high-b", "t-low"]


def test_task_store_rejects_unknown_dependencies():
    store = TaskStore()

    with pytest.raises(ValueError):
        store.add(Task(id="t1", title="孤立任务", kind="doc", domain="core", goal="失败", dependencies=["missing"]))
