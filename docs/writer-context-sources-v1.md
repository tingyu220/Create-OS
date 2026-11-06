# Writer 当次上下文来源阅读 V1

## 小设计与实施计划

沿用 Conversation / Proposal / Memory / RuntimeRunner，不新增领域事实或路径读取接口。模型适配器 complete 边界持久化任务快照，来源内容从真正组成消息的同一字符串提取，记录 SHA256、来源版本、字符截断范围和消息定位。查询只按完整 project/chapter/session/job 与快照内 source_id 白名单寻址，不接受文件路径。

界面沿用三栏、绿色强调、现有字号和间距。中间消息/任务选择当次来源，右侧“详情”页签独立滚动；优先显示当次使用状态、正文片段，再列版本、哈希、截断和经验依据。空态、加载、失败、旧任务无快照、未入模均明确中文说明。窄屏复用正文面板切换，不改变编辑器内容，不扩展人物等领域模型。

实施：真实消息 Fake 捕获测试 → 快照/受控 Query → 来源控制器及详情 → 作用域、竞态、历史不漂移与临时项目浏览器验证。保留现有未提交改动；不切分支、commit/push/merge。

## 数据与 Query 契约

- `AgentJob.context_snapshot`（schema_version=1）随原章节会话原子持久化。只有真实 `ModelAdapter.complete(messages)` 边界进入后才写快照，不在 Query 时重新读取正文/Memory/投影。快照写入失败会阻止下游模型调用。
- 来源含 `source_id/label/source_ref/version/usage/reason`；入模片段含原样 `content_snapshot/content_hash`、原内容哈希、原长及 `[excerpt_start,excerpt_end)` Unicode 字符范围。正式稿没有独立版本时由 SHA256 标识；工作稿版本取自读取正文的同一 JSONL 记录。
- `message_location={index,role,start,end}` 定位实际发送消息。另保留系统消息、每条历史对话和最后完整请求，便于核对提示包装及未展开的上下文摘要。片段必须与最后 user 消息逐字一致，否则阻止调用。
- `source_id=source-<job UUID>-<序号>`，同会话不同任务也不能交叉借用。查询只检查内存中恢复的任务快照白名单，不将来源引用解析成路径。
- `GET /api/agent/jobs/{job_id}/context-sources?project_id=...&chapter_number=...&session_id=...` 返回来源索引；增加 `source_id=...` 返回该来源详情与完整作用域。参数必须唯一、齐全，不接受额外 `path` 等参数；跨项目/章节/会话/任务、未知来源和路径串返回 422。
- 会话 Query 仅新增 `context_available`，不携带整份快照；旧 job 查询和任务受理响应也不暴露新快照正文。UI 仅使用上述来源 Query。
- 复用 `job.experience_context.selected` 的原片段、hash/version、Memory 原文、evidence/reasons、审批信息；历史归档后仍是当次参考，不声明当前 ACTIVE。
- `included` 是当次适配器调用输入；`delivery=adapter_call_started` 只证明进入适配器调用边界，失败/中断不能据此声称远端已接收。`not_in_model` 覆盖范围/预算排除、仅登记的投影引用、Act 被冻结输入替代的当前稿正文；这些条目不返回伪造正文。
- 无完整快照的旧任务 `delivery=unavailable`；章节/当前稿不可恢复。若旧任务已有经验快照则显示 `recorded`（旧选入证据，送达未知），不会回查当前文件或 Memory。

## 文件职责

- `creative_os/writer_context_sources.py`：片段登记、适配器观察及受控 Query。
- `creative_os/agent_runtime.py`：同一组装字符串登记、任务持久化和 Query 接线；`creative_context.py` 仅补同记录工作稿版本。
- `creative_os/web_workspace.py`：只读 GET 与静态资源；不增加 Command 或领域写入。
- `creative_os/web/writer-sources.js`：来源列表、详情、完整归属核对和独立请求代次；`writer-agent.js` 仅补消息/任务入口与重置；`writer.js` 打开详情及窄屏导航。
- `writer.html/writer.css`：原详情页签内的独立滚动区，片段前置、校验折叠、长文本换行；项目概览明确不代表当次入模。
- `tests/test_writer_context_sources.py`、`test_writer_context_sources_http.py`、`test_writer_sources_ui.js`：Fake 实际消息、历史/范围/路径与前端竞态；`scripts/validate_writer_sources_ui.py` 为临时项目 Chromium 验收。

## 验证（2026-10-17）

全部使用临时项目/Fake 模型，无付费模型调用；未向文明升阶写入正文、工作稿或会话，无删除操作。保持原分支及全部既有改动，未 commit/push/merge。

- Python 受影响回归：**110 passed，26.70s**，含 Runtime、Conversation/HTTP、Proposal、经验/HTTP、CreativeContext、Web Workspace、页面契约及新来源测试。
- Node：**28 passed**，含来源控制器、既有会话/提案/经验和真实 writer.js 保存隔离/丢响应恢复。最后窄屏页签滚动次序修正后，来源及保存测试再次 **13 passed**。
- 最后补充旧经验快照降级与归档证据后，来源 Python/真实 HTTP 专项 **18 passed，3.86s**。覆盖逐条捕获消息与范围/hash核对、历史文件修改、经验归档、重启、跨项目/章/会话/job/source 拒绝、路径攻击、预算/范围排除、旧任务不可用和调用失败送达未知。
- Chromium **1440×1000、390×844**：长工作稿历史片段逐字等于实际 Fake messages；归档经验显示当次使用，投影无正文；刷新与移动导航、右侧独立滚动、详情标签可见，无整页或详情横向溢出，编辑器正文和版本不变，**页面错误 0**。
- 最新临时项目：`C:\Users\tingyu\AppData\Local\Temp\creative-os-source-ui-l2rj159y`。截图 `.backup/source-ui/source-desktop.png`、`source-mobile.png`；截图已实际检查。
- `node --check`（writer.js / writer-agent.js / writer-sources.js）及 `git diff --check` 通过。

## 限制与交付

沿用单项目单 Runtime 服务进程约束；未提供远端服务接收证明、磁盘损坏恢复或断电级 fsync 保证。完整消息快照提高历史可核验性，也增大章节会话文件；现有完整对话发送和全局上下文预算限制未改变，暂不增加压缩或清理策略。旧任务缺快照无法补还原。仅作为缓存/投影与运行证据，不新增人物/世界/情节事实。

## P2 定向修复：重复文本的来源位置

独立复审发现：正文 `DUPLICATE` 同时出现在用户意图中时，原 `message.index(text)` 返回意图里的首次出现位置。正文/hash 虽一致，归属位置有误。

修复在实际拼接时登记前文章节、当前正式稿/工作稿、冻结输入及各条经验的相对偏移；完整 user 请求前缀长度作为统一偏移加入。适配器边界只验证指定切片与快照片段逐字相等，不再使用 `index/find/rfind` 搜索文本；未登记位置或边界内容不符均阻止调用。提示消息内容、Query 契约、经验/提案与旧快照不改写。

新增测试先复现 4 项失败（用户指令同文、多来源相同/互相包含与多次出现，analyze/act），再修复。后补纯 ASCII 原复现和 Unicode 字符范围，共 8 个参数用例；逐个按独立拼接段计算预期位置，验证前文、当前稿/冻结输入、每条经验均落在各自边界。

定向回归：`python -m pytest tests/test_writer_context_sources.py tests/test_writer_context_sources_http.py tests/test_agent_runtime.py tests/test_agent_conversation.py tests/test_agent_proposal.py tests/test_writer_lessons.py tests/test_creative_context.py -q`，**90 passed，17.94s**；`git diff --check` 通过。前端没有变更，未重复浏览器验收。本次只改 `agent_runtime.py`、`writer_context_sources.py`、`test_writer_context_sources.py` 与本文；分支/HEAD 仍为 `codex/writer-agent-conversation-v1` / `c67d87c`，无生产写入、真实模型或 commit/push/merge。交总控定向复审。

DONE：受控 Query、当次快照、历史阅读、中文详情、作用域/竞态/长文与隔离验收。

CURRENT：本独立功能交付总控安排独立复审，全部改动未提交。

TODO：总控复审与集成决定；不自行宣布 Writer Agent 总目标完成。
