# Proposal 审阅事务的显式核对

状态：实现与定向验收已完成；等待总控再次独立复审。

## 复现与范围

registry 使用 recover=False 后，accept 在反馈追加后发生 OSError，会留下 reviewing 提案和 RESERVED 原命令；原任务已 completed，既不能重试任务，也不能再次审阅。新增 registry 重启 HTTP 反例先因缺少恢复元数据失败，实际 Writer JS 反例也确认没有入口。

本轮只恢复原审阅操作的可续办能力，不恢复 GET 写入或任意 POST 全项目扫描。未修改总览首页、CSS 或 Writer HTML。

## 最小接线

- `AgentProposalStore.public/view`：只读计算 review_recovery，覆盖 reviewing 和终态但原回执仍 RESERVED 的情况；view 基于同一个原子提案文件计算差异，不创建项目锁。中断拒绝后的旧审阅检查点仍可仅补齐其回执。
- 身份绑定：feedback_id + review_hash；指纹覆盖原 identity、actor、反馈快照及修订 job_id，不包含可续写的命令回执列表。严格同时核对 project/chapter/session/proposal 和原作者，禁止用新 action、reason 或 source 替代原决定。
- `reconcile_writer_proposal` → `POST /api/commands/reconcile-writer-proposal`：沿用既有 DTO、CommandBoundary、项目锁和预检；只查指定提案，原命令编号、反馈编号、落稿 operation_id、修订 job_id 保持不变。
- `AgentProposalCommandHandler._reconcile`：与既有启动恢复共用 `_finish`，补齐指定审阅的原 RESERVED 回执。核对请求也追加在同一个 review.commands 检查点，避免核对自身回执中断后再次失去入口；没有第二套事务存储。
- Writer 在现有提案区域动态显示“核对原审阅操作”。只允许点击后提交，使用原作者及身份，响应不明沿用原幂等编号；切章隔离旧响应。不自动重开工作稿或保存编辑器内容。

## 安全边界

- 原接受已落稿：复用 saved_operation 或 draft_version，不覆盖之后的人工稿。
- 原接受尚未落稿且基线已变：返回 proposal_base_conflict，保留人工稿并完成原拒绝回执。
- 同内容接受在 draft_version 持久化前中断：没有已提交接受的证据，后续改稿后继续拒绝；已有持久回执则仅补齐反馈。
- scope、actor、feedback_id、review_hash 或载荷字段不符：在可写装配之前拒绝，所有文件、集合及 mtime 保持不变。
- 只处理目标审阅，不恢复其它章节任务；原修订任务已经存在时不创建第二个任务或模型调用。

## 验证

新增 `tests/test_agent_proposal_reconcile_http.py`，33 项覆盖：

- 原接受在落稿前/后、落稿回执后、反馈前/后、提案终态后、命令回执前中断；各自配对后续人工改稿。
- 核对自身意图、原命令回执、核对回执中断，registry 再次重建后仍可完成。
- 原命令与核对命令的同编号/新编号重放，不重复版本、反馈或修订任务。
- 八类错误身份/载荷拒绝、同内容接受窗口、reject/cancel/revise 标识保留、无关章节文件不变。
- 经验操作在 registry 下按原编号可完成其已有检查点；故事确认按原编号复用原子 operation receipt，且不顺带恢复 Proposal。

定向组合：新专项及原 Proposal/Conversation HTTP/此前四项反例合计 80 项通过。Writer JS 两个新反例先失败后通过，覆盖入口、原身份、编号复用和迟到响应。

相关组合回归最终为 331 项通过、1 项失败。唯一失败是并行首页改版后 `test_web_workspace_routes.py` 仍断言旧根页面标题；已回传总控交首页负责人更新，不越界修改。Writer/Story 等 JS 46 项通过。此结果不能表述为共享工作区所有测试通过。

`scripts/validate_proposal_reconcile_ui.py` 使用出口保护、临时项目和 Chromium：原反馈后异常 → registry 重建 → GET 全文件快照不变 → 点击核对 → 原回执完成；后续人工稿保持、版本总数 2、反馈 1 条、零页面错误。仅 1 次原 Fake 候选生成，核对期间无新增模型调用。报告及截图在 `.backup/proposal-reconcile-ui/`。

## 其它持久命令核查

- Story 使用单聚合原子回执，registry 下按原编号重放通过，没有 reviewing 阻塞状态。
- Lesson 已有原操作文件和 RESERVED 续办路径，registry 下重放通过，候选仍可查询，未复现同样的 UI 卡死；不扩展其界面。
- 普通 Writer 工作稿命令原本不依赖 Runtime 启动恢复，本轮不重写其通用事务语义。

## 交付记录

DONE：复现、显式核对接线、原身份/回执复用、33 项新增专项、真实浏览器验证、相关回归。
CURRENT：P1 交付总控独立复审。
TODO：独立复审；首页负责人更新旧根标题断言并完成共享路由的合并验收。

路由文件已释放给总控单一负责人接首页；释放时 `web_workspace.py` SHA256 为 `D3587CDBAC0F7AC8835A3BBBD4545EBB54B2D0D9FB478F08536503A1CD28FD4A`。之后首页接线的改动不由本会话实施。

本轮所有 Python 验证均由 fake_validation_guard 默认拦截真实客户端及外网；未操作生产 Runtime、真实小说或 8877，未提交/推送/合并。前轮真实请求发送/接收/计费未知的记录继续保留，本轮成功验证不改变该不确定性。
