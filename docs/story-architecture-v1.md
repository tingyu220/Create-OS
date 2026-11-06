# Idea 到小说前期架构 Agent 首版

## 交付边界

安全创建新书 → 自主多轮讨论 → 作者编辑候选 → 明确确认指定 revision/hash → 继续讨论不替换正式设定 → 显式生成第一章 Proposal → 作者接受工作稿。

不接完整 NovelDomain 合同生产链，不发布正文，不做 Portfolio。当前只做实现交付，总目标由总控独立复审后判断。

## 权威与接口

- `NovelProjectCreator.create(title, idea, operation_id=...)`：父 projects 根锁与 `.creative_os/new-books.json` 创建意图；Windows 保留名、点路径、尾点空格、大小写/清洗碰撞及同名拒绝；完成记录及所有权标记防覆盖，半初始化同键续办。
- `StoryArchitectureStore`：`.creative_os/story/architecture.json` 为唯一权威。原子聚合包含候选 revisions、不可变 confirmed_versions、唯一 current 与幂等 operations；内容块可自由扩展，未定问题独立保存。
- `StoryCommandBoundary`：沿用 CommandBoundary 与结果存储，确认强制 project/story/session、revision、hash、expected_confirmed_version，采用 CAS；领域副作用与 operation receipt 原子提交，同指纹 reservation 可从中断恢复。
- `WriterAgentRuntime`：story scope 使用 `chapter_number=None`，沿用同一队列、持久任务与重试。默认项目注册进入 registry 后复用原 Runtime，禁止同项目新增第二条写作队列。Query 的只读装配不恢复写入；中断任务仅在 Query 中显示恢复需求，显式重试才接管。
- `story_architecture_agent.py`：模型逐步选择 read_candidate/read_confirmed/propose_revision/finish_turn，最多 6 步；完整历史、当前候选、正式设定实际入模。没有 confirm/publish 工具；坏包或非法动作不能写候选。步数用尽可继续讨论。必需输入超过明确字符预算时拒绝，不裁剪为假事实。
- `story_context.py`：章节受理时冻结正式 text/version/hash/source_ref，重试保留冻结版本；`_run` 实际拼入 ModelMessage 并记录 included、准确消息偏移及内容哈希。新书未确认阻断写章，旧项目兼容。
- 透明委派 v3：仅 `_run` 与 `_execute_story_step` 可直接构造适配器，各自恰一次、不能在循环内；适配器仍只 capture 后原样委派，RuntimeRunner 为唯一业务模型出口。v1/v2 清单保留。

## Web

- `GET /story` 新书入口；`POST /api/projects/create` 使用稳定 operation_id，可重放，不自动调用模型。
- `GET /p/{project}/story`、`GET /p/{project}/writer?chapter=1`：项目绑定路由，registry 仅允许 projects 直接子目录。初始化 Idea 预填讨论框，由作者发送开始讨论。
- `GET /api/story/session?project_id=...&scope=story` 仅发现会话 ID 与初始 Idea；后续对象查询强制 project_id/scope/session_id。
- `GET /api/story`：对话、任务、候选及正式版，严格上述作用域；`GET /api/story/sources` 另外要求 job_id/step，返回当步真实输入快照。
- `POST /api/story/intents`、`/retry`、`/start-first-chapter`：明确作用域；第一章启动绑定已确认 version/hash。
- `POST /api/commands/edit-story-candidate` 与 `/confirm-story-candidate`：严格 WebCommand DTO。故事命令单独允许 200KB，其他现有命令仍为 16KB。
- 页面以原生文本渲染模型内容；编辑使用原 revision 进行 CAS。乱序 Query 不覆盖较新结果，项目路径在页面生命期固定，跨项目导航创建新页面，旧页面请求无法改绑新项目。

## 验证与复审入口

- `python scripts/run_fake_writer_tests.py`：默认禁用真实 from_env、urllib 出口及所有非 loopback socket；测试可局部注入 Fake，真实连接仍由 socket 保护。`test_fake_validation_guard.py` 断言出口前拒绝，不依赖注入约定。
- `node --test tests/test_story_ui.js tests/test_writer_agent_ui.js tests/test_writer_lessons_ui.js tests/test_writer_sources_ui.js tests/test_writer_save_scope_ui.js`。
- `python scripts/validate_story_ui.py`：相同进程保护、临时 projects、Fake 模型、Chromium 页面外网拦截；覆盖完整闭环、刷新、桌面 1440px/手机 390px、接受工作稿和真实 messages/source offsets。报告、截图位于 `.backup/story-ui/`。
- 新专项测试覆盖两种不同 Idea/不同讨论顺序、坏包/非法工具、预算可继续、过期候选及确认 CAS、跨项目/会话、并发创建/确认、半初始化与命令回执中断恢复、运行中换设定不偷换本次输入、未确认阻断与旧项目兼容。

## 测试隔离事件

独立复审后四项恢复/只读问题的修复与新证据，见 `docs/story-review-fixes-2026-10-18.md`。Web POST 已改为只读绑定与预检在前；registry 可写装配不进行全项目恢复，只有指定中断任务的合法 retry 执行接管。

随后发现 Proposal 审阅事务缺少显式核对入口，已补严格绑定原决定的定向核对；见 `docs/proposal-review-reconcile-2026-10-19.md`。不恢复 GET 或无关 POST 的全项目写恢复。

最终证据：默认禁止真实出口的组合回归 **270 项通过**；最后增加冻结输入引用与导航断连处理后，相关故事/模型接线/架构 **75 项通过**；JS 行为 **43 项通过**；Chromium **8 次 Fake 执行**完成全链，页面无脚本错误。日志在 `.backup/story-validation/pytest.log`、`final-targeted.log`、`js.log`、`browser-final.log`。这些结果不能替代真实创作质量验收或独立复审。

早期增加 client_factory 时错误地捕获了默认 `from_env` 方法。旧测试 `test_act_keeps_selected_chapter_and_detects_concurrent_edit` 在构造 Runtime 后才 monkeypatch，可能绕过替身。会话输出记录任务 started_at 为 `2026-10-18T12:45:06.055059+00:00`（北京时间 20:45:06），任务等待超时，随后测试进程已中断。

已确认代码曾绑定真实构建方法；测试未立即返回缺配置错误，是可能进入模型调用的间接证据。没有当时的网络发送审计或远端回执，不能确认请求实际发送、远端收到或计费。旧 pytest-361 目录已在后续 pytest 自动保留策略中轮换；没有为核实发送任何真实请求，也没有读取或输出密钥。当前仅留原工作台 Python 进程，无测试残留。

修复为默认工厂延迟解析，并新增测试进程级默认禁止构建/urllib/socket 外网保护；浏览器脚本使用相同保护且页面只放行 loopback。此次事件与不确定性必须随交付保留，不能声称全程绝无真实调用。完整复审须检查保护实际生效。
