# Minimal Interactive Workspace Refresh Command Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在单小说 Web Workspace 中实现第一条低风险、可审计的 Projection 刷新命令，让用户能通过统一 Command Boundary 请求刷新并看到最新只读投影。

**Architecture:** 新增独立的 Web Command Adapter，将严格校验后的 HTTP 请求转换为现有 `CommandRequest`，再交给 `CommandBoundary`。应用层命令处理器只调度 `ProjectionRefreshCoordinator`，不修改 Domain、Knowledge 或 Projection 文件；前端提交后仍通过 `/api/workspace` 回读结果。该命令是运维命令切片，不宣称已经验证小说领域事实的 `Domain → Event` 写链路。

**Tech Stack:** Python 3.12、标准库 `http.server`、现有 Workspace Query/Command/Refresh 契约、原生 HTML/CSS/JavaScript、pytest

**Spec:** `docs/superpowers/specs/2026-09-01-workspace-query-command-boundary-design.md`

## Global Constraints

- 仅支持单小说项目，不引入 Portfolio。
- UI 只能通过 Web Adapter 调用 Query Adapter 与 Command Boundary，禁止读取 Domain、Knowledge、Runtime 或底层 Projection。
- Projection 仍是只读、可丢弃的派生数据；刷新命令不得创造领域事实。
- 首版只开放 `refresh_workspace_projection`，不开放编辑器、审批、生产控制或任意命令转发。
- 每次请求必须包含 `command_id`、`request_id`、`actor`、`target`、`idempotency_key`；服务端拒绝未知字段与未知命令。
- 命令结果必须保持 `accepted/rejected/failed`、稳定错误码、`audit_ref`、`trace_id`、`projection_refresh_id`。
- TDD：每个实现任务先写失败测试，再写最小实现。

---

## File Structure

- Create: `creative_os/workspace_command_adapter.py` — 将唯一允许的 Web 命令映射到现有 Command Boundary。
- Create: `creative_os/web_command_dto.py` — 严格解码请求并编码稳定的 Web 命令结果。
- Modify: `creative_os/workspace_command.py` — 让刷新调度器显式接收当前请求，并支持处理器的类型化拒绝，避免共享闭包与并发串单。
- Modify: `creative_os/web_workspace.py` — 增加受限的命令端点，不承载业务语义。
- Modify: `scripts/novel_web_workspace.py` — 在 composition root 注入命令边界、持久化结果存储与刷新协调器。
- Modify: `creative_os/web/index.html` — 增加只读工作台中的刷新控制与结果区域。
- Modify: `creative_os/web/app.js` — 提交命令、展示状态并在 accepted 后重新查询 Workspace。
- Modify: `creative_os/web/styles.css` — 增加命令状态与禁用态样式。
- Create: `tests/test_web_command_dto.py` — DTO 严格校验与稳定编码测试。
- Create: `tests/test_workspace_command_adapter.py` — 命令白名单、幂等和刷新映射测试。
- Modify: `tests/test_web_workspace.py` — HTTP、前端依赖隔离和只开放单一路由测试。
- Modify: `tests/test_workspace_integration.py` — Web → Command → refresh → Query 端到端测试。
- Modify: `README.md` — 启动方式、命令边界与非目标说明。

### Task 1: 固化 Web Command DTO

**Files:**
- Create: `creative_os/web_command_dto.py`
- Create: `tests/test_web_command_dto.py`

**Interfaces:**
- Consumes: JSON object received by the HTTP adapter.
- Produces: `decode_web_command(raw: object) -> CommandRequest` and `encode_command_result(result: CommandResult) -> dict[str, object]`.

- [ ] **Step 1: Write the failing request-decoding test**

```python
def test_decode_refresh_command_requires_exact_fields():
    request = decode_web_command({
        "command_id": "refresh_workspace_projection",
        "request_id": "request-1",
        "actor": "local-user",
        "target": "novel-1",
        "payload": {"sections": ["project", "operations"]},
        "expected_version": None,
        "idempotency_key": "refresh-1",
    })
    assert request.command_id == "refresh_workspace_projection"
    assert request.payload == {"sections": ["project", "operations"]}
```

- [ ] **Step 2: Run the focused test and verify RED**

Run: `python -m pytest -q tests/test_web_command_dto.py::test_decode_refresh_command_requires_exact_fields`

Expected: FAIL because `creative_os.web_command_dto` does not exist.

- [ ] **Step 3: Implement strict DTO decoding**

Implement `decode_web_command` with an exact seven-field key set, exact string checks, JSON-object payload validation, and `expected_version: int | None`. Raise `WebCommandValidationError(code="validation_failed", message=...)` for missing, extra, or invalid fields. Reject all `command_id` values except `refresh_workspace_projection` with code `command_not_allowed`.

- [ ] **Step 4: Add result-encoding and rejection tests**

```python
def test_encode_command_result_preserves_trace_and_refresh_receipt():
    result = CommandResult(
        CommandStatus.ACCEPTED, "refresh_workspace_projection", "request-1",
        audit_ref="audit-request-1", trace_id="trace-1",
        emitted_event_refs=(), projection_refresh_id="refresh-1",
    )
    assert encode_command_result(result) == {
        "status": "accepted", "command_id": "refresh_workspace_projection",
        "request_id": "request-1", "error": None,
        "audit_ref": "audit-request-1", "trace_id": "trace-1",
        "emitted_event_refs": [], "projection_refresh_id": "refresh-1",
    }
```

Also assert unknown commands, unknown fields, booleans passed as `expected_version`, blank identity fields, and non-object payloads are rejected.

- [ ] **Step 5: Run DTO tests and commit**

Run: `python -m pytest -q tests/test_web_command_dto.py`

Expected: PASS.

Commit: `git commit -m "固化 Web 命令 DTO 契约"`

### Task 2: 实现唯一允许的刷新命令适配器

**Files:**
- Create: `creative_os/workspace_command_adapter.py`
- Create: `tests/test_workspace_command_adapter.py`

**Interfaces:**
- Consumes: `CommandRequest`, `CommandBoundary`, and `ProjectionRefreshCoordinator`.
- Produces: `WorkspaceRefreshCommandHandler.__call__(request: CommandRequest) -> tuple[str, ...]`, `WorkspaceProjectionRefreshScheduler.__call__(request: CommandRequest, event_refs: tuple[str, ...], trace_id: str) -> str`, and `WorkspaceCommandAdapter.execute(request: CommandRequest) -> CommandResult`.

- [ ] **Step 1: Write the failing adapter test**

```python
def test_refresh_command_returns_real_refresh_receipt():
    coordinator = StubCoordinator(refresh_id="refresh-1")
    adapter = build_adapter(coordinator, project_id="novel-1")
    result = adapter.execute(CommandRequest(
        "refresh_workspace_projection", "request-1", "local-user", "novel-1",
        {"sections": ["project", "operations"]}, None, "refresh-key-1",
    ))
    assert result.status is CommandStatus.ACCEPTED
    assert result.projection_refresh_id == "refresh-1"
    assert coordinator.calls == [("novel-1", {ProjectionSection.PROJECT, ProjectionSection.OPERATIONS})]
```

- [ ] **Step 2: Run the focused test and verify RED**

Run: `python -m pytest -q tests/test_workspace_command_adapter.py::test_refresh_command_returns_real_refresh_receipt`

Expected: FAIL because the adapter does not exist.

- [ ] **Step 3: Extend the boundary with explicit request-aware scheduling**

Change `ProjectionRefreshScheduler` to `__call__(request: CommandRequest, event_refs: tuple[str, ...], trace_id: str) -> str` and make `CommandBoundary` pass the current request. Add `CommandRejectedError(code: str, message: str, retryable: bool = False)` and optional `request_validator: Callable[[CommandRequest], None]`; the validator must run before fingerprinting, idempotency reservation, version reads and handler execution. Typed validation rejection maps to `rejected`; an unexpected validator exception maps to stable `failed/command_validation_failed` without reserving a key or invoking downstream dependencies. Update existing boundary tests and call sites to the three-argument scheduler signature.

- [ ] **Step 4: Implement handler and scheduler composition**

`WorkspaceRefreshCommandHandler.validate` rejects non-null `expected_version`, validates that `request.target` equals the configured project, and requires `payload.sections` to be a non-empty, duplicate-free list of exact `ProjectionSection` values. `__call__` repeats the validation defensively and returns `()` because this operation creates no domain event. `WorkspaceProjectionRefreshScheduler` receives the request and command trace explicitly, calls `ProjectionRefreshCoordinator.refresh(request.target, sections, trace_id=trace_id)`, then verifies refresh id, project id, normalized sections, snapshot id and trace id before returning the real receipt; any mismatch becomes `command_outcome_unknown`.

- [ ] **Step 5: Add boundary-behavior tests**

Test the following exact cases:

- same idempotency key + same fingerprint returns the original result without a second refresh;
- same idempotency key + different sections returns `idempotency_conflict`;
- wrong project target returns `rejected/target_not_found`;
- empty or unknown sections return `rejected/validation_failed`;
- non-null `expected_version` is rejected before fingerprinting, reservation, version reading, handler or refresh;
- unexpected validator failure returns `failed/command_validation_failed` without downstream side effects;
- refresh failure returns `failed/command_outcome_unknown` and exposes `trace_id`;
- two concurrent requests with different section sets cannot exchange scheduler context;
- forged refresh receipts with mismatched refresh id, project, sections, snapshot or trace are never accepted;
- adapter imports no Domain, Knowledge, Runtime, projection builder, filesystem source, or repository implementation.

- [ ] **Step 6: Run adapter tests and commit**

Run: `python -m pytest -q tests/test_workspace_command_adapter.py tests/test_workspace_boundary.py`

Expected: PASS.

Commit: `git commit -m "接入工作区刷新命令边界"`

### Task 3: 增加受限 HTTP 命令端点

**Files:**
- Modify: `creative_os/web_workspace.py`
- Modify: `scripts/novel_web_workspace.py`
- Modify: `tests/test_web_workspace.py`

**Interfaces:**
- Consumes: `WorkspaceCommandAdapter.execute(CommandRequest) -> CommandResult`.
- Produces: `POST /api/commands/refresh-workspace` with JSON request/response; every other POST route remains 404 or 405.

- [ ] **Step 1: Write failing HTTP tests**

Add tests that start the in-process server and assert:

```python
connection.request(
    "POST", "/api/commands/refresh-workspace",
    body=json.dumps(valid_request),
    headers={"Content-Type": "application/json"},
)
response = connection.getresponse()
assert response.status == 202
assert json.loads(response.read())["status"] == "accepted"
```

Also assert malformed JSON → 400, payload above 16 KiB → 413, wrong content type → 415, rejected command → 422, conflict → 409, failed command → 503, and arbitrary POST routes → 404.

- [ ] **Step 2: Run HTTP tests and verify RED**

Run: `python -m pytest -q tests/test_web_workspace.py`

Expected: FAIL because POST is still globally disabled.

- [ ] **Step 3: Implement the narrow HTTP route**

Inject an optional `WorkspaceCommandAdapter` into `create_server`. Read at most 16 KiB, require `application/json`, decode through `decode_web_command`, and encode only through `encode_command_result`. Do not add a generic `/api/commands/{name}` dispatcher.

- [ ] **Step 4: Wire the composition root**

In `scripts/novel_web_workspace.py`, construct `FileCommandResultStore(project_root)`, `ProjectionRefreshCoordinator`, `WorkspaceRefreshCommandHandler`, `CommandBoundary`, and `WorkspaceCommandAdapter`. Keep `creative_os/web_workspace.py` free of filesystem, Domain, Runtime, repository, and projection builder imports.

- [ ] **Step 5: Run HTTP and architecture tests and commit**

Run: `python -m pytest -q tests/test_web_workspace.py tests/test_workspace_command_adapter.py tests/test_workspace_boundary.py`

Expected: PASS.

Commit: `git commit -m "开放受限工作区刷新接口"`

### Task 4: 增加最小交互界面

**Files:**
- Modify: `creative_os/web/index.html`
- Modify: `creative_os/web/app.js`
- Modify: `creative_os/web/styles.css`
- Modify: `tests/test_web_workspace.py`

**Interfaces:**
- Consumes: `POST /api/commands/refresh-workspace` and `GET /api/workspace`.
- Produces: one explicit “刷新投影” action with pending/succeeded/rejected/failed presentation.

- [ ] **Step 1: Write failing static-contract tests**

Assert the UI contains one button with `data-command="refresh-workspace"`, the JavaScript posts only to `/api/commands/refresh-workspace`, and accepted completion triggers the existing `loadWorkspace()` query. Assert there are no editor fields, arbitrary payload editors, approval controls, production controls, or generic command URL construction.

- [ ] **Step 2: Run the static test and verify RED**

Run: `python -m pytest -q tests/test_web_workspace.py::test_frontend_exposes_only_refresh_workspace_command`

Expected: FAIL because the control does not exist.

- [ ] **Step 3: Implement the interaction**

Generate `request_id` and `idempotency_key` once per user click with `crypto.randomUUID()`. Disable the button while pending; show accepted/rejected/failed, stable error code, `trace_id`, and `projection_refresh_id`. On accepted, call `loadWorkspace()` and render the new `refresh_id`; never mutate displayed Projection data locally.

- [ ] **Step 4: Add accessibility and failure-state assertions**

Require an accessible button name, `aria-live="polite"` status region, keyboard operability, visible disabled state, and preserved diagnostic text after failure. Verify unknown values stay “未提供” rather than `0`.

- [ ] **Step 5: Run frontend checks and commit**

Run:

```text
python -m pytest -q tests/test_web_workspace.py
node --check creative_os/web/app.js
```

Expected: both pass.

Commit: `git commit -m "增加投影刷新交互界面"`

### Task 5: 端到端契约、回归与可视化验收

**Files:**
- Modify: `tests/test_workspace_integration.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: the complete HTTP command and query chain.
- Produces: executable evidence that command acceptance leads to a real refreshed snapshot visible through the Query Adapter.

- [ ] **Step 1: Write the end-to-end test**

Build a temporary project, materialize an initial bundle, change an authoritative source so Query reports `stale`, then POST `refresh_workspace_projection`. Assert the response is `accepted`, the returned `projection_refresh_id` equals the subsequently queried envelope `refresh_id`, and both sections cease to be `stale`.

- [ ] **Step 2: Add restart/idempotency coverage**

Restart the server with the same temporary project and replay the same request. Assert `FileCommandResultStore` returns the original accepted result and no second refresh journal entry is created.

- [ ] **Step 3: Document operation and boundary**

README must show the exact launch command, request schema, response schema, and state explicitly that this operation refreshes disposable Projection only; it neither changes novel facts nor proves a domain editing workflow.

- [ ] **Step 4: Run complete verification**

Run:

```text
python -m pytest -q tests/projection tests/test_workspace_boundary.py tests/test_workspace_integration.py tests/test_workspace_command_adapter.py tests/test_web_command_dto.py tests/test_web_workspace.py
python -m compileall -q creative_os scripts tests
node --check creative_os/web/app.js
git diff --check
python -m pytest -q
```

Expected: all targeted checks pass. Any full-suite failure must be reproduced on `origin/main`; no new failure is allowed.

- [ ] **Step 5: Perform real-browser verification**

Using `projects/文明升阶`, verify one click transitions pending → accepted, displays `trace_id` and `projection_refresh_id`, reloads all four views, and does not create or expose any editor/approval/production/Portfolio UI. Remove only the disposable test Projection cache after verification.

- [ ] **Step 6: Request independent review and close the branch**

Review gates:

- Critical: unauthorized generic command execution, boundary bypass, or fabricated domain facts.
- Important: broken idempotency/conflict mapping, false freshness, missing traceability, or frontend-local Projection mutation.
- Minor: accessibility, copy, or layout defects that do not affect the contract.

After review passes, follow repository rules for Chinese commit messages, Git Bash push, PR, full check, and merge without history rewriting.

## Completion Criteria

- The only write endpoint is `POST /api/commands/refresh-workspace`.
- A real `CommandBoundary` and persistent idempotency store process the request.
- Accepted results contain a real refresh receipt; Query returns the matching refreshed envelope.
- Rejected, conflict, failed, retry, and restart behavior are covered by tests.
- UI never edits Projection locally and never reads lower layers.
- Documentation clearly distinguishes an operational Projection command from a domain mutation.
- Full regression introduces no new failures and independent review has no unresolved Critical/Important findings.

## Explicit Follow-up — Not Part of This Plan

After this slice is stable, audit existing Novel Domain application services and choose one genuine, reversible domain command. That separate feature must prove `Web → Command Boundary → Application/Domain → Event → Projection Refresh`; do not infer that proof from the Projection refresh command implemented here.
