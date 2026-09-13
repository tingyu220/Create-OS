from __future__ import annotations

from dataclasses import replace

import pytest

from creative_os.workspace_command import CommandBoundary, CommandRejectedError, CommandRequest, CommandStatus
from creative_os.workspace_dto import ProjectionSection
from creative_os.workspace_refresh import RefreshReceipt, RefreshResult, RefreshStatus
from creative_os.workspace_command_adapter import (
    WorkspaceCommandAdapter,
    WorkspaceProjectionRefreshScheduler,
    WorkspaceRefreshCommandHandler,
)


class StubCoordinator:
    def __init__(self, refresh_id: str = "refresh-1") -> None:
        self.refresh_id = refresh_id
        self.calls: list[tuple[str, set[ProjectionSection]]] = []
        self.trace_ids: list[str | None] = []

    def refresh(self, project_id: str, sections: set[ProjectionSection], trace_id: str | None = None):
        self.calls.append((project_id, sections))
        self.trace_ids.append(trace_id)
        trace = trace_id or "trace-fallback"
        receipt = RefreshReceipt(self.refresh_id, project_id, tuple(sorted(item.value for item in sections)), "snapshot-1", trace)
        return RefreshResult(self.refresh_id, RefreshStatus.SUCCEEDED, 1, trace_id=trace, receipt=receipt)


def _request(payload: dict[str, object] | None = None, *, target: str = "novel-1", key: str = "refresh-key-1") -> CommandRequest:
    return CommandRequest(
        "refresh_workspace_projection",
        "request-1",
        "local-user",
        target,
        payload or {"sections": ["project", "operations"]},
        None,
        key,
    )


def build_adapter(coordinator: StubCoordinator, project_id: str = "novel-1") -> WorkspaceCommandAdapter:
    handler = WorkspaceRefreshCommandHandler(project_id)
    boundary = CommandBoundary(
        handler,
        version_reader=lambda _target: 0,
        refresh_scheduler=WorkspaceProjectionRefreshScheduler(coordinator),
        request_validator=handler.validate,
    )
    return WorkspaceCommandAdapter(boundary)


def test_refresh_command_returns_real_refresh_receipt():
    coordinator = StubCoordinator()
    result = build_adapter(coordinator).execute(_request())

    assert result.status is CommandStatus.ACCEPTED
    assert result.projection_refresh_id == "refresh-1"
    assert coordinator.calls == [("novel-1", {ProjectionSection.PROJECT, ProjectionSection.OPERATIONS})]


def test_refresh_command_rejects_wrong_target_and_invalid_sections():
    coordinator = StubCoordinator()
    adapter = build_adapter(coordinator)

    wrong_target = adapter.execute(_request(target="other-novel"))
    empty_sections = adapter.execute(_request({"sections": []}, key="empty"))
    unknown_section = adapter.execute(_request({"sections": ["project", "editor"]}, key="unknown"))
    duplicate_section = adapter.execute(_request({"sections": ["project", "project"]}, key="duplicate"))

    assert (wrong_target.status, wrong_target.error.code) == (CommandStatus.REJECTED, "target_not_found")
    assert (empty_sections.status, empty_sections.error.code) == (CommandStatus.REJECTED, "validation_failed")
    assert (unknown_section.status, unknown_section.error.code) == (CommandStatus.REJECTED, "validation_failed")
    assert (duplicate_section.status, duplicate_section.error.code) == (CommandStatus.REJECTED, "validation_failed")
    assert coordinator.calls == []


def test_refresh_command_rejects_expected_version_in_direct_calls():
    request = CommandRequest(
        "refresh_workspace_projection", "request-versioned", "local-user", "novel-1",
        {"sections": ["project"]}, 1, "versioned",
    )

    with pytest.raises(CommandRejectedError, match="不支持 expected_version"):
        WorkspaceRefreshCommandHandler("novel-1")(request)


def test_direct_adapter_rejects_expected_version_before_any_side_effect():
    coordinator = StubCoordinator()
    calls = {"handler": 0, "version": 0, "reserve": 0}

    class CountingHandler:
        def __init__(self) -> None:
            self._delegate = WorkspaceRefreshCommandHandler("novel-1")

        def validate(self, request: CommandRequest) -> None:
            self._delegate.validate(request)

        def __call__(self, request: CommandRequest) -> tuple[str, ...]:
            calls["handler"] += 1
            return self._delegate(request)

    class CountingStore:
        def reserve(self, _key, _fingerprint):
            calls["reserve"] += 1
            raise AssertionError("非法版本请求不得预留幂等记录")

    handler = CountingHandler()
    boundary = CommandBoundary(
        handler,
        version_reader=lambda _target: calls.__setitem__("version", calls["version"] + 1) or 1,
        store=CountingStore(),
        refresh_scheduler=WorkspaceProjectionRefreshScheduler(coordinator),
        request_validator=handler.validate,
    )
    result = WorkspaceCommandAdapter(boundary).execute(
        CommandRequest(
            "refresh_workspace_projection", "request-versioned", "local-user", "novel-1",
            {"sections": ["project"]}, 1, "versioned",
        )
    )

    assert result.status is CommandStatus.REJECTED
    assert result.error.code == "validation_failed"
    assert calls == {"handler": 0, "version": 0, "reserve": 0}
    assert coordinator.calls == []


@pytest.mark.parametrize(
    "mutate",
    [
        lambda receipt: replace(receipt, refresh_id="other-refresh"),
        lambda receipt: replace(receipt, project_id="other-project"),
        lambda receipt: replace(receipt, sections=("operations",)),
        lambda receipt: replace(receipt, snapshot_id=""),
        lambda receipt: replace(receipt, trace_id="other-trace"),
    ],
)
def test_scheduler_rejects_fabricated_or_unbound_receipt(mutate):
    class ForgingCoordinator(StubCoordinator):
        def refresh(self, project_id, sections, trace_id=None):
            result = super().refresh(project_id, sections, trace_id)
            return replace(result, receipt=mutate(result.receipt))

    coordinator = ForgingCoordinator()
    result = build_adapter(coordinator).execute(_request())

    assert result.status is CommandStatus.FAILED
    assert result.error.code == "command_outcome_unknown"
    assert result.trace_id


def test_adapter_rejects_unknown_command_id():
    coordinator = StubCoordinator()
    adapter = build_adapter(coordinator)
    result = adapter.execute(CommandRequest("delete_project", "request-1", "local-user", "novel-1", {"sections": ["project"]}, None, "unknown"))

    assert result.status is CommandStatus.REJECTED
    assert result.error.code == "command_not_allowed"
    assert coordinator.calls == []


def test_refresh_command_idempotency_conflict_does_not_refresh_twice():
    coordinator = StubCoordinator()
    adapter = build_adapter(coordinator)

    first = adapter.execute(_request())
    duplicate = adapter.execute(_request())
    conflict = adapter.execute(_request({"sections": ["project"]}))

    assert duplicate == first
    assert conflict.status is CommandStatus.REJECTED
    assert conflict.error.code == "idempotency_conflict"
    assert len(coordinator.calls) == 1


def test_refresh_failure_is_unknown_and_keeps_refresh_context_explicit():
    class FailingCoordinator(StubCoordinator):
        def refresh(self, project_id: str, sections: set[ProjectionSection], trace_id: str | None = None):
            self.calls.append((project_id, sections))
            raise RuntimeError("refresh failed")

    coordinator = FailingCoordinator()
    result = build_adapter(coordinator).execute(_request())

    assert result.status is CommandStatus.FAILED
    assert result.error.code == "command_outcome_unknown"
    assert result.trace_id
    assert result.projection_refresh_id is None


def test_scheduler_passes_request_context_to_coordinator():
    coordinator = StubCoordinator()
    scheduler = WorkspaceProjectionRefreshScheduler(coordinator)
    request = _request({"sections": ["operations"]})

    refresh_id = scheduler(request, (), "trace-1")

    assert refresh_id == "refresh-1"
    assert coordinator.calls == [("novel-1", {ProjectionSection.OPERATIONS})]
    assert coordinator.trace_ids == ["trace-1"]


def test_adapter_does_not_import_authority_layers():
    import ast
    from pathlib import Path

    tree = ast.parse(Path("creative_os/workspace_command_adapter.py").read_text(encoding="utf-8"))
    imported = {
        node.module or ""
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }
    forbidden = ("creative_os.domains", "creative_os.knowledge", "creative_os.runtime", "creative_os.projection.builder", "creative_os.projection.filesystem_source", "creative_os.projection.repository")
    assert not any(name.startswith(forbidden) for name in imported)
