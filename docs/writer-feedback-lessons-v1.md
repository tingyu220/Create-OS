# Writer Feedback → 作者经验 → Future Context V1

## 设计与实施

沿用已验收的 Conversation、Proposal 和持久 Feedback，以及现有 JsonMemoryStore、Memory 审批、MemoryRetriever、ContextCompiler 和 CommandBoundary。未另建 KnowledgeStore，未改变 Proposal 接受/拒绝及工作稿保存语义。

采用保守的作者提炼入口：选择已有反馈，填写具体可复用方法及适用条件、标题，选择“仅本章/整个项目”，保存为经验候选。空内容拒绝创建；accept/reject/cancel/revise 本身不会自动生成经验或通用规则。候选必须再经明确批准才 ACTIVE，拒绝和归档均不供后续请求使用。本轮不增加模型自动归纳调用。

实施顺序：临时项目 Fake 模型失败测试 → 来源核验与 Memory 候选 → 可恢复命令审批 → 检索及实际提示消息 → 中文折叠审阅入口 → HTTP/Node/浏览器及原功能回归。

界面复用现有 Writer 三栏、颜色和间距；在 Agent 区增加“作者经验 · 候选与状态”折叠入口，表单、中文状态、证据展开及明确审批按钮。窄屏沿用原面板切换，长编号和 SHA256 在容器内换行。

## 来源与数据契约

- 候选是原有 `MemoryItem`：`kind=experience`、`scope=project`、`scope_id=权威project_id`、`status=candidate`、`tags` 含 `writer_lesson`，`applicability=writing`。创建编号由完整来源、标题、经验及范围确定，同一输入不重复创建。
- `content` 是 schema_version=1 的经验信封：具体经验、chapter/project 范围、来源章节、完整 Feedback 快照、原审阅作者、proposal_id、冻结原稿 source/version/ref/hash、候选 result ref/hash。原稿与候选正文继续保存在原 Proposal，不把候选正文写成领域事实。
- 只接受唯一持久 Feedback，完整校验项目/章节/会话、Proposal 已完成审阅、原反馈快照、task/message 关联及冻结原稿/候选内容 SHA256；不接受伪造、跨项目、未完成审阅或不一致证据。候选创建和审阅操作者必须为明确人类作者，禁止 system。
- 主数据仍在 `.creative_os/memory/items/*.json`；审批复用 `approve_candidate/reject_candidate/archive_memory`；审计仍为 `.creative_os/memory/audit.jsonl`。
- `.creative_os/agent/lesson_operations/*.json` 仅是先写操作意图的恢复日志，含确定的 Memory 快照、原命令关联、决定及完成/冲突回执，不提供第二套经验查询或状态权威。

## Query / Command

`GET /api/agent/conversations/{chapter}?project_id=...` 新增 `lesson_review={project_id,chapter_number,feedback,lessons}`，以及任务中的 `experience_context`。返回本章来源反馈、本章经验及明确适用全项目的经验，刷新/服务重启均可恢复。

`POST /api/commands/manage-writer-lesson` 沿用 WebCommand DTO：

```json
{
  "command_id": "manage_writer_lesson",
  "request_id": "lesson-request-id",
  "actor": "作者",
  "target": {
    "project_id": "project-id",
    "chapter_number": 1,
    "session_id": "source-session-id",
    "feedback_id": "source-feedback-id"
  },
  "payload": {
    "action": "create",
    "title": "动机表达",
    "content": "本章通过可见动作承载人物动机，保留犹豫过程。",
    "range": "chapter"
  },
  "expected_version": null,
  "idempotency_key": "lesson-request-id"
}
```

审阅 `payload` 严格为 `{action: approve|reject|archive,memory_id,version,note}`。必须填写审阅说明，version 为当前 Memory 版本；项目经验在别章显示时，审阅目标仍使用原反馈的章节/会话归属。回执 `emitted_event_refs` 为 `memory:<id>:<action>`。

项目锁覆盖 reserve→意图→Memory→审计→回执。相同幂等键不同内容冲突；同一候选同版本的批准/拒绝共用一个决定槽位，不同决定或说明冲突。原指纹匹配的 RESERVED 请求可用原请求续办，保留原预留记录。状态已落盘但审计缺失时补一次审计，不重复审批；意图前中断时由原请求重新核验来源并续办。若期间 Memory 版本/内容/状态变化，恢复拒绝旧操作、保留新版本，补齐拒绝回执，不阻止正常 Runtime 启动。

## 真正进入模型的经验与下一来源面板接线点

实际链路为 `WriterAgentRuntime._run → CreativeContextBuilder → compile_writer_experience → MemoryRetriever → ContextCompiler → RuntimeRequest.messages → ModelAdapter`。

Writer 读取同项目、ACTIVE、experience、writer_lesson、writing 经验，再按明确的本章/全项目范围筛选。项目范围意味着作者明确允许所有章节使用，未增加语义向量检索。其他旧 Memory 类型沿用原有使用链路。

经验独立预算为 **4000 字符**，调用现有 ContextCompiler 保留完整经验或按整条排除，不从中间截断方法。实际渲染片段在最后一条 user 消息的“作者已批准的写作经验”段内，注明其为写作参考，不是人物/世界/情节事实。该预算只覆盖经验片段，原会话历史与正文的总预算限制未改变。

任务在模型调用前持久记录 `experience_context`，会话 Query 可直接读取：

- `selected[]`：memory_id/version/scope_id/approved_by/source_ref、实际渲染 `content_snapshot/content_hash`、原 Memory `memory_content_snapshot/memory_content_hash`、evidence、检索 reasons、`truncated=false`。
- `excluded[]`：本章范围不匹配或 `budget_exceeded`，预算排除含原片段字符数。
- `budget_chars/rendered_chars/truncated`、compiler_fingerprint/version；truncated 表示存在预算整条省略，不表示改写经验。
- CreativeContext.source_refs 也包含实际选入的 `memory:<id>:v<version>`；下轮独立来源面板应读取该任务快照，不重新检索当前 Memory 冒充历史输入。

## 文件职责

- `writer_lesson.py`：来源核验、确定候选、现有 Memory 查询。
- `writer_lesson_command.py`：独立领域命令边界、恢复意图和审计对账。
- `writer_experience_context.py`：现有检索/编译适配、片段与来源快照。
- `creative_context.py`、`agent_runtime.py`：实际模型消息及任务快照接线。
- `web_command_dto.py`、`web_workspace.py`：命令与 Query/静态资源接线。
- `web/writer-lessons.js`：独立经验控制器；`writer-agent.js` 只接入会话刷新，html/css 提供原生表单及样式。
- `tests/test_writer_lessons.py`、`test_writer_lessons_http.py`、`test_writer_lessons_ui.js`：隔离功能、故障与 UI 契约测试。
- `scripts/validate_writer_lessons_ui.py`：临时项目及 Fake Client 的可复现 Chromium 验收。

## 验证与限制（2026-10-17）

所有验证均使用临时项目及 Fake Client，无真实付费模型调用，未向文明升阶写稿，未切分支/commit/push/merge，HEAD 保持 c67d87c。PowerShell 7.6.5，动态解析 pwsh.exe。

- 首批新增测试先见缺少 lesson_commands 的 3 项失败，再实现。
- Python 受影响回归首轮 **246 passed，29.70s**：全部 test_writer*.py，Agent Runtime/Intent/Conversation/Proposal/HTTP、CreativeContext、Web Workspace/DTO、Feedback、Memory 审批/检索/预算及通用命令边界/集成。
- 最后补充候选创建中断恢复、校验收紧后，经验专项及真实 HTTP **17 passed，5.66s**；三个前端脚本 `node --check` 通过，`git diff --check` 通过。
- Node **24 passed**：经验真实控制器、原会话/Proposal、实际 writer.js 的保存隔离、丢响应恢复及切章竞态。
- 真实 Chromium：1440×1000、390×844，候选创建、未批准模型消息、批准后实际消息、刷新、归档后不选入；原工作稿及版本不变、页面错误 0、无横向溢出。截图 `.backup/lesson-ui/lesson-desktop.png` 与 `lesson-mobile.png`。
- 故障覆盖审批意图前、状态落盘后审计前、命令回执前 × 同进程/重启；并发审批只有一次状态与审计；新 Memory 版本阻止旧审批恢复。

限制：本轮由作者填写具体经验，不做模型自动提炼或泛化；沿用单项目单 Runtime 服务进程的运行约束，未扩张领域阅读面板。磁盘损坏和断电级 fsync 保证不在本轮范围；文件证据不可读时保留失败/未知状态，不推定成功。

DONE：来源核验、经验候选及人工批准、ACTIVE 检索与真实提示、范围隔离、预算/来源快照、中文入口和隔离验收。

CURRENT：交付总控安排只读独立复审，全部变更保留未提交。

TODO：由总控接下一独立受控来源面板；用户确认前不提交或推送。
