# Writer Agent 章节会话 V1

2026-10-17 后续进展：本文件保留会话阶段的历史设计与验收记录。新的写作执行已改为独立候选提案，审阅后才落工作稿；冻结基线、接受/拒绝/取消、继续修改与持久反馈见 [Proposal 审阅与反馈 V1](writer-agent-proposal-v1.md)。

## 设计与实施计划

目的：章节对话在刷新和服务重启后可恢复，运行状态不会替换历史消息；下一轮模型调用收到当前章节正文和同章对话。

采用现有 `WriterAgentRuntime → RuntimeRunner → ModelAdapter` 执行链路，继续通过 `WriterDraftStore` 保存工作稿。新增存储适配器只负责会话快照，不建立另一套 Runtime。

实施顺序：隔离测试 → 会话/任务持久化 → API 作用域校验 → 前端恢复与轮询 → 失败重试与回归验证。用户已授权实施；不合并、不提交、不推送。

## 数据与调用契约

- 会话文件：项目下 `.creative_os/agent/conversations/chapter_NNN.json`，`schema_version=1`。
- 一章一个稳定 `session_id`；父记录明确 `project_id/chapter_number`，任务同时记录 `project_id/chapter_number/session_id/job_id`。
- 消息含 `message_id/task_id/role/content/created_at`；`job_id` 即现有 Runtime 的 `task_id`。
- 消息与任务在同一快照原子替换，沿用 `project_authority_lock`。状态更新只改任务；用户消息在受理时添加，助手消息在完成时添加。
- 当前正式稿和工作稿正文完整传入模型，前文沿用现有最多三章片段，同章已完成对话以实际消息内容传入。不同章的对话隔离。
- 目标章固定为页面选择的章节，取消按最大正式章节隐式跳章。自然语言内容不授予写入权限，`submit` 与 intents 的 `mode` 默认 `analyze`。只有明确传入 `mode=act` 的写作按钮命令，或确认方案的 decisions/act 命令才转执行。
- 执行前读取工作稿版本，落稿时校验该版本，防止覆盖生成期间作者的新修改。
- 每次编辑冻结保存快照的项目、章节、正文和预期版本。切章先完成旧章待保存及在途保存，失败留在旧章；连续编辑只承接同一编辑会话中已确认的保存版本。版本取自保存命令的 `emitted_event_refs`，不从新章或最新列表推测。
- 保存结果未确认的原请求使用独立 `unconfirmedSave` 槽位保留，后续编辑使用 `pendingSave`。恢复时先用原始编号、正文及预期版本重放原幂等请求，取得确认版本后才衔接后续编辑；外部更新造成的版本冲突仍阻止写入和切章。
- 决策执行任务持久保留原 `decision_id`，失败重试继续保留其模式与决策关联；刷新后可明确提交原决策与作者补充要求再次执行。

API：

| 方法 | 路径 | 行为 |
| --- | --- | --- |
| GET | `/api/agent/conversations/{chapter}?project_id=...` | 恢复会话、消息、所有任务 |
| POST | `/api/agent/intents` | 同章受理下一轮，支持 `session_id` 校验；`mode` 默认 `analyze`，显式写作命令传 `act` |
| GET | `/api/agent/jobs/{job_id}` | 保留旧接口，补充会话、错误及重试信息 |
| POST | `/api/agent/jobs/{job_id}/retry` | 显式重试，需项目、章节、会话匹配 |
| POST | `/api/agent/decisions/act` | 在原会话中执行决策，需作用域匹配 |

所有写请求明确项目与章节。同章只允许一个未完成任务。失败重试产生新任务，保留原始错误与 `retry_of/retry_job_id` 关联，不重复添加用户消息；同一失败任务重复重试返回同一个任务。已被后续对话取代的失败任务拒绝重新执行。

## 刷新、失败与重启

页面消息区与任务状态区分开，轮询不替换已有消息节点。切章使用作用域代次校验，迟到响应不能更新新章节。刷新会恢复未完成任务轮询；已完成的历史任务不会自动打开工作稿。请求响应不确定时仅重新查询，不自动重发模型执行请求。

启动时将遗留未完成任务标记失败。保存前中断可手动重试；保存阶段中断或保存冲突禁止直接重试，需先核对现有工作稿版本。模型或连接异常保留实际错误文本。分析结果仍支持作者确认后生成工作稿。

## 验证记录

2026-10-15，PowerShell 7.6.5。全部验收使用 pytest 临时目录及 Fake Client，不触发真实付费写作，不向文明升阶正式稿或工作稿写入内容。

- Python：112 项通过。覆盖全部 `test_writer*.py`，Agent Runtime/Intent、会话持久化与真实 HTTP 边界、CreativeContext、Web Workspace。
- Node：`node --test tests/test_writer_agent_ui.js tests/test_writer_save_scope_ui.js`，15 项通过。除会话控制器外，直接执行实际 `writer.js`，用可控定时器与延迟网络模拟保存及切章。
- `node --check`：`writer.js`、`writer-agent.js` 通过。
- 新增持久化测试先执行，确认因缺少新契约失败，再实现；最终回归通过。

独立审查 P1 修复证据：

1. 三句“为什么这样写？”“继续解释一下原因”“为什么建议修改结尾？”分别在有/无工作稿时验证只读，稿件及版本完全不变；HTTP 与 UI 验证默认只读和显式 Act 正例。先复现 6 个失败用例，再移除关键词授权。
2. 保存串章先在同版本、均无工作稿两种状态复现；修复后旧章定时保存及在途保存只写旧章，旧加载不覆盖新章，同章连续编辑按确认版本串行保存，保存冲突阻止切章并保留编辑内容。
3. Act 持久保留原决策，Runtime 重启后可继续执行；UI 刷新恢复后继续修改入口提交原 `decision_id`、会话作用域和作者补充要求。测试先复现刷新后入口消失，再完成修复。
4. 后续复审发现 A 已保存但响应丢失时 B 会丢掉原幂等编号。新增 3 项测试先复现失败：B 在响应丢失前/后输入均通过原请求确认 A，再以版本 2 保存 B，且切章可恢复；存在真正外部版本 3 时 B 仍冲突，外部正文不变。原请求确认前后请求体完全一致，A 不生成重复版本。

## 变更文件

- `creative_os/agent_conversation_store.py`：新增章节会话快照适配器。
- `creative_os/agent_runtime.py`：持久任务、多轮上下文、重启恢复及安全重试。
- `creative_os/web_workspace.py`：会话查询、重试入口与作用域校验。
- `creative_os/web/writer-agent.js`：新增会话控制器。
- `creative_os/web/writer.js`：对话接线、章节地址与异步响应保护。
- `creative_os/web/writer.html`：历史、任务状态、会话操作三个独立容器。
- `scripts/novel_web_workspace.py`：把权威项目 ID 传入已有 Runtime。
- `tests/test_agent_conversation.py`：新增会话与故障恢复测试。
- `tests/test_agent_conversation_http.py`：新增实际 HTTP 契约测试。
- `tests/test_writer_agent_ui.js`：新增页面控制器行为测试。
- `tests/test_writer_save_scope_ui.js`：实际 Writer 脚本的定时保存、在途保存和切章竞态测试。
- `tests/test_agent_runtime.py`：默认使用模型替身，禁止单元测试触发真实写作。
- `docs/writer-agent-conversation-v1.md`：设计、接口、验证与交付记录。

## 限制与下个集成点

当前仍按一个项目一个 Runtime 服务进程运行；不支持多个服务进程同时消费同一项目任务。会话历史完整保留并发送，长会话可能达到模型上下文上限，后续需要显式预算与摘要策略。自由文本即使提到写作也默认只读，需通过写作按钮或确认方案执行。断电级持久性、模型真实服务验收及实际浏览器人工验收不在本轮验证范围。Proposal 冻结基线、接受/拒绝语义仍留下一独立任务。

下个集成点：总控审阅本分支差异后，接入统一会话查询展示与上下文预算；反馈学习、右侧领域详情暂未开发。

DONE：持久会话、真实上下文、作用域隔离、独立状态、失败重试及隔离测试。

CURRENT：交付当前开发分支，等待总控集成审阅。

TODO：由用户确认后再决定提交或集成；本轮无 commit/push。
