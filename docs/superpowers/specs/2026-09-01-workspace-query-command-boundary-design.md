# Workspace Query Adapter 与 Unified Command Boundary

## 目标

在现有单项目 Projection Layer 之上提供稳定的 Web-facing 查询契约，并固化未来 Web Workspace 可直接调用的通用命令边界。Projection 仍是可丢弃、只读、可重建的派生结果；Adapter 不读取领域文件、不创造领域事实。

## 架构

`ProjectionReader` 只负责读取已物化投影。`WorkspaceQueryAdapter` 组合 `ProjectSnapshot` 与独立的 `OperationsSnapshot`，输出不可变 DTO。`ProjectionEnvelope` 暴露整体及每个分区的 `fresh/stale/partial/unavailable` 状态，并保留 SourceRef、trace、diagnostic、refresh_id。

`ProjectionRefreshCoordinator` 接收领域变更事件，按受影响 section 计算刷新请求；首版允许全量 builder，但契约保留 section 集合。每次刷新生成 refresh_id、attempts、延迟与诊断；失败结果可按 refresh_id 重试。

`CommandBoundary` 只校验和转发通用 `CommandRequest`，由 handler 处理领域语义。契约覆盖 request/command/actor/target/payload、expected_version、idempotency、validation、conflict、accepted/rejected/failed、audit/trace。重复请求返回原结果；版本冲突不调用 handler。

## 一致性与错误

查询读取 envelope 时比较 projection source heads 与 reader 当前 heads，发现变化即明示 stale，不静默伪装为最新。分区刷新失败只影响对应分区，整体状态为 partial；无法读取既有投影则为 unavailable。所有失败包含稳定 code、message、refresh_id 与可追踪 SourceRef。

## 测试边界

跨层测试覆盖 Domain change → Event → refresh → Query 最新状态、stale 明示、失败诊断与 retry、Adapter 只能经 ProjectionReader、命令重复提交/乐观并发/失败重试，以及 Web-facing DTO 的稳定字段。

## 实现状态

### 1. Query Adapter

`WorkspaceQueryAdapter.get_workspace(project_id)` 是未来 Web Workspace 的唯一只读入口。它只依赖 `ProjectionRepository` 协议，不导入 Domain、Knowledge、Runtime 或文件系统 source。Repository 读取失败映射为 `unavailable`；已物化 bundle 与当前 source heads 不一致时，Project 和 Operations 同时映射为 `stale`。

### 2. Web-facing DTO

`ProjectionEnvelope` 统一返回 `project_id/snapshot/operations/overall/sections/source_heads/refresh_id`。`OperationsSnapshot` 提供 Task、Execution/Runtime、Error、attempts、token usage、recovery 和 retry 视图；所有 DTO 均为 frozen dataclass。不存在权威事实时不推断值：usage、recovery、retry 分别以 `None/None/()` 返回，并通过稳定诊断码暴露，因此 Operations 为 `partial`。

### 3. Event → Projection

当前 Event Log 中所有已知 `EventType` 都会影响 Project 的 Trace，同时 Operations 也由同一 Trace 派生，因此全部刷新 `project + operations`；未知事件不获得隐式刷新范围。首版刷新为同步触发、原子发布，允许调用方在事件提交与刷新完成之间观察到短暂的延迟一致，此时 source-head drift 必须显示 `stale`。Builder 接收 `refresh_id`，成功回执绑定 project、sections、snapshot、trace，并把同一 refresh_id 写入 bundle。

刷新失败保留上一份只读 bundle，journal 记录 attempts、requested/completed 时间、trace 与诊断；调用方通过 refresh_id 显式 retry。成功记录为 terminal，重启后重复 retry 直接返回原回执，禁止覆盖。

### 4. Unified Command Boundary

`CommandRequest` 固定 command_id、request_id、actor、target、payload、expected_version、idempotency_key 和 request_fingerprint。边界先做稳定输入校验，再以 canonical JSON SHA-256 指纹保留幂等语义；相同键与相同指纹返回原结果，不同指纹返回 `idempotency_conflict`。expected_version 实现乐观并发。

标准结果为 `accepted/rejected/failed`，并携带稳定 error、audit_ref、trace_id、event refs 和真实 projection refresh receipt。刷新 ID 只能由注入的 `refresh_scheduler` 返回；未配置时为 `None`，禁止伪造。领域处理或刷新调度后的副作用不确定时返回非自动重试的 `command_outcome_unknown`；命令存储忙、版本源暂不可用等尚未进入领域处理的失败才允许安全重试。

文件命令存储使用 reserve → complete 状态机、进程间锁和原子替换。只有领域处理尚未开始的版本读取失败可以释放 reservation；处理开始后的未知结果保留 reservation，防止重复副作用。

### 5. 契约测试

跨层测试验证 Domain change → Event → Projection refresh → Query 最新状态、同源 bundle stale、刷新失败跨重启诊断与 retry、Adapter 依赖隔离、Command 的输入校验/乐观并发/幂等/持久化/未知结果保护，以及真实刷新回执。提交前必须运行 workspace、integration、projection 定向测试、compileall、diff check 和全量 pytest；全量失败必须与 `main` 基线逐项比对。

### 6. 尚存风险

- 首版仍是全量 Projection 构建；section 与 refresh 契约已为后续增量构建保留，但当前没有增量优化。
- 当前权威源尚未提供 token usage、recovery、retry 事实；UI 必须展示 Operations `partial` 与诊断，不得把空值解释为零或正常。
- 文件锁只保证单机工作区并发，不是跨主机分布式锁。
- 本阶段没有 HTTP/Web Adapter、认证授权或业务命令批量实现。

### 7. Web Workspace 准入结论

具备进入“最小可交互 Web Workspace”的架构准入条件，但只允许先实现只读 API/页面，并通过 Query Adapter 读取。首个写操作必须把真实 Application/Domain handler 与 refresh scheduler 接入 Command Boundary，并完成 actor/auth、冲突和审计的端到端验证；在此之前不得开放编辑、审批或生产控制能力。

## 非目标

不实现完整 Web UI、编辑器、审批/生产控制页面、跨项目 Portfolio、大规模领域模型或第二套业务逻辑。
