# Writer Agent Proposal 审阅与反馈 V1

## 已批准设计与实施计划

沿用章节会话、RuntimeRunner、WriterDraftStore 和 CommandBoundary。新增 Proposal 存储只保存冻结输入、候选结果和审阅记录，不另建 Runtime/Memory。原会话持久化改动全部保留，不切分支、提交、推送或合并。

执行开始在项目锁内冻结工作稿（优先）、正式稿或空稿，记录内容、来源、版本和 SHA256。候选独立保存，任务/消息关联 proposal_id。差异始终来自同一 Proposal 的 base/result。继续修改明确指定 candidate 或 base，继承原冻结写入基线，作者改稿后仍需重新发起提案，不能借继续修改绕过冲突。

审阅命令 review_writer_proposal 目标严格包含 project/chapter/session/proposal；action 为 accept/reject/cancel/revise。接受在项目锁内核对原工作稿版本及当前实际基线 hash 后落稿；拒绝、取消、继续修改均不修改正文。审阅先持久化意图，再执行幂等副作用，重复命令及新编号同一决定不会重复版本、反馈或模型任务；不同决定/原因拒绝。反馈复用 FeedbackRecord/FeedbackStore，记录完整归属，仅追加审阅事实，预留 LessonCandidate 输入，不自动生成或激活经验。

1. [x] 隔离 Fake 模型测试先覆盖首次拒绝、冻结差异、接受冲突/幂等、恢复、归属、继续修改与只读。
2. [x] 实现小型 Proposal 存储与审阅命令处理器；Runtime 生成候选并接现有 HTTP 命令边界。
3. [x] 前端增加候选阅读、冻结差异、接受/拒绝/取消/继续修改和原因；保护原保存、切章和实时状态逻辑。
4. [x] 运行受影响 Python/Node 回归、记录证据；交付总控独立复审。

## 风险检查

生成期间人工保存、无工作稿正式稿发生变化、首次空稿、反复审阅、服务重启、反馈写入后响应失败、候选继续修改跨章、前端迟到响应。所有验收使用临时项目，无真实小说写入与付费调用。

## 数据与接口契约

- `.creative_os/agent/proposals/proposal-<uuid>.json`：schema_version=1。含 project_id/chapter_number/session_id/task_id/message_id/decision_id/parent_proposal_id。
- base 保存 source、原稿版本、hash、content、冻结快照 ref 和原始 source_ref；result 保存独立候选正文、hash 和 ref。input 明确保存本次生成输入（初次原稿、父候选或父冻结原稿），不会用最新稿替换。
- 状态：generating / failed / pending / reviewing / accepted / rejected / cancelled / revised。失败不改正文。已有历史 Act 工作稿保持原样，仅新执行生成 Proposal，不伪造历史基线。
- `GET /api/agent/conversations/{chapter}?project_id=...` 补充 proposals，刷新恢复已生成和已审阅提案。
- `GET /api/agent/proposals/{proposal_id}?project_id=...&chapter_number=...&session_id=...` 返回冻结正文与 diff，严格校验完整作用域。
- `POST /api/commands/review-writer-proposal` 使用现有 WebCommand DTO 和 CommandBoundary：command_id=`review_writer_proposal`，target 严格为 `{project_id, chapter_number, session_id, proposal_id}`，payload 为 `{action, reason}`；revise 还须 `source=candidate|base`。expected_version 必须 null，实际并发保护来自服务端冻结基线。
- accepted HTTP 回执沿用 202，失败沿用现有边界规则。emitted_event_refs 含 writer-proposal、接受时的 writer-draft、继续修改时的 agent-job，以及 feedback 引用。
- accept 不发布正式稿；reject/cancel/revise 不创建正文版本。非接受操作必须填写原因。提案只允许一次确定的审阅决定，相同决定、原因和来源可幂等重放，不同决定拒绝。
- revise 保留原 decision、章节与会话，使用稳定的后继任务编号及 parent_proposal_id。原稿已变化时，后继提案继承的旧基线仍阻止覆盖；作者必须基于当前稿重新发起独立写作命令。

## 恢复与反馈

审阅意图先落盘，再执行工作稿、后继任务和 Feedback 副作用。正文版本附加 operation_id，审阅另存 draft_version 回执。只有持久证据才能证明工作稿已经应用：新正文版本的 operation_id 或已落盘的 draft_version。满足此条件时，重启仅补齐缺失反馈与命令回执，不再次落稿或覆盖后来的人工编辑。若尚无已应用证据且期间原稿变化，记录冲突尝试，恢复 pending 状态供拒绝或取消，禁止覆盖。

正文完全相同的 save 会沿用当前版本，不生成 operation_id；这种接受以审阅 draft_version 回执的原子落盘为可恢复提交点。若 save 返回后、回执落盘前中断，只有待确认的审阅意图，不能声称已接受事实可恢复。期间人工改稿时，同进程重放或重启恢复均返回 proposal_base_conflict，提案回到 pending、不追加接受反馈；回执已持久化后则能恢复原接受事实，且不改人工新稿。

复用 `.creative_os/runtime/feedback.jsonl`，FeedbackRecord 新增可选 proposal/session/message/decision/base_ref/base_hash/result_hash，新增 cancelled outcome；旧记录可照常读取。追加式 append_once 使用稳定 feedback ID 去重，调用方持有项目锁。revise 的 revision_ref 指向后继 agent-job。未来 LessonCandidate 可明确消费这些 FeedbackRecord；当前不调用 create_lesson_candidate、不创建或激活长期经验，也不另造 Memory/Runtime。

## 文件职责

- `creative_os/agent_proposal_store.py`：冻结快照、候选持久化、固定 base→result 差异。
- `creative_os/agent_proposal_command.py`：提案专用 CommandBoundary、作用域、审阅状态、乐观并发、幂等副作用和重启对账。
- `creative_os/agent_runtime.py`：在现有执行链中生成独立候选，记录消息/任务/决策关联；会话与重试能力继续复用。
- `creative_os/writer_draft_store.py`：接受操作落稿编号和恢复查询，不改变人工保存/恢复/发布命令。
- `creative_os/memory/feedback.py`：扩展现有反馈归属和幂等追加。
- `creative_os/web_workspace.py`、`web_command_dto.py`：查询与现有命令边界接线。
- `creative_os/web/writer-agent.js`、`writer.js`、`writer.html`、`writer.css`：候选列表/阅读、冻结差异、中文状态、四项审阅命令；保留原保存与切章隔离。
- `tests/test_agent_proposal.py`：23 项行为与故障测试；HTTP/原 Runtime/UI 测试按候选语义更新。
- `scripts/validate_writer_proposal_ui.py`：临时项目、Fake 模型、真实 Chromium 的可复现验收，保留临时数据与截图。

## 验证记录（2026-10-17）

PowerShell 7.6.5，所有测试使用临时项目和 Fake 模型，不向文明升阶正文或工作稿写入，也无真实付费调用。

- 首轮 Python：147 项通过，18.81s。全部 `test_writer*.py`，Agent Runtime/Intent/Conversation/Proposal、CreativeContext、Web Workspace/DTO 和 Feedback；P1 后续验证见下。
- Node：20 项通过，含真实 writer.js 的原有保存隔离/丢响应恢复、会话恢复、候选审阅、接受冲突和幂等编号；两个前端脚本 `node --check` 通过。
- TDD：先见 6 项 Proposal 旧行为失败、3 项 UI 缺契约失败；随后逐项补测并修复审阅回执中断、已写反馈去重、无内容变化接受的恢复边界。新测试最终全部通过。
- 真浏览器：1440×1000 与 390×844。候选与冻结差异不修改编辑器；拒绝和刷新保持原版本；从冻结原稿继续修改后，接受才由版本 1 增至 2；三条反馈分别归属拒绝、继续修改、接受。页面脚本错误 0，无整页横向溢出。
- 最新浏览器临时项目：`C:\Users\tingyu\AppData\Local\Temp\creative-os-proposal-ui-5t4cysb0`。截图在 `.backup/proposal-ui/proposal-desktop.png`、`proposal-mobile.png`、`proposal-accepted.png`。

## P1 复审修复：首份审阅意图前中断

复审复现：通用 CommandBoundary 已 reserve，但首个 review 快照尚未写入时中断，原命令只有持久指纹。旧恢复扫描仅处理已有 review，导致同键长期 command_outcome_unknown。新增 4 项用例（reserve 后/首份意图前 × 同进程/重启）先复现失败。

修复只接入 AgentProposalCommandBoundary，未修改通用 `workspace_command.py`：

- 项目锁覆盖完整 reserve→审阅意图→副作用→命令回执，重放不能与尚在运行的原请求同时续办。
- 原保留记录和原指纹始终保留，不释放、不清除、不重新 reserve。同键不同 payload 仍由原指纹判为 idempotency_conflict。
- 只有同指纹重放才进入提案级证据核对：已有审阅意图按稳定操作/任务/反馈编号续办；缺意图时必须为 pending，且不存在该提案的已落稿 operation、后继任务或反馈，才允许从头续办并最终补齐原命令回执。
- 发现无意图却有不明副作用，或任何核对证据不可读，均保留 RESERVED，返回 command_outcome_unknown；不会推定“没有 review 就没有副作用”。
- 启动扫描仍不凭不完整指纹猜测命令内容；客户端重放原请求提供 target/payload，与原指纹匹配后才能恢复。这同时兼容修复前已经留下的 RESERVED 记录。
- 同内容接受在提交点前中断的边界按上一节明确；冲突尝试完整保留在 review_attempts，同进程也会恢复 pending，无需重启才能拒绝。

P1 最终验证：`python -m pytest tests/test_agent_proposal.py tests/test_agent_runtime.py tests/test_agent_conversation.py tests/test_agent_conversation_http.py tests/test_workspace_boundary.py tests/test_workspace_command_adapter.py tests/test_workspace_integration.py tests/test_workspace_review_command.py tests/test_web_command_dto.py tests/test_writer_command.py tests/test_writer_draft_store.py tests/test_feedback.py -q`，**141 passed，14.95s**。包括 Proposal 23 项、通用命令边界/集成、HTTP 与原会话/反馈回归。既有已落稿/已写反馈在同进程及重启后均不重复，额外覆盖原请求并发、不同载荷冲突、不明副作用与证据不可读。前端未改动，未盲目重跑浏览器或不受影响的全量测试。

## 限制与交付

仍沿用单项目单 Runtime 服务进程约束；断电级 fsync/磁盘损坏、真实模型服务不在本轮验收范围。原会话完整历史的上下文预算限制未变。后继任务若已受理后服务中断，沿用持久会话的显式重试，不自动重复执行模型。审阅单项决定为终态，后续独立创作使用新命令生成新提案。

DONE：冻结基线、独立候选、固定差异、四项审阅、持久反馈、恢复/冲突/幂等与前后端验收；复审 P1 首份意图前中断修复及提交点边界验证。

CURRENT：修复交付总控安排第二轮独立复审，所有改动保留未提交。

TODO：总控独立复审及用户之后决定是否提交/集成；本轮无 commit/push/merge，未切分支，HEAD 仍为 c67d87c。
