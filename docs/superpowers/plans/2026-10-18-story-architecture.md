# Idea 到小说前期架构首版实施计划

> 按 superpowers:executing-plans 在当前会话执行；总控已批准直接实施，独立复审由总控安排。

**目标：** 安全创建新书，Agent 自主讨论，作者编辑并明确确认候选；已确认正文冻结后实际进入第一章 Writer，生成 Proposal 并接受为工作稿。

**架构：** 复用 WriterAgentRuntime 的单队列、任务持久化与 RuntimeRunner。新增故事领域原子聚合存储，候选修订与不可变确认记录、current 指针在同一个原子事务中提交。仅显式作者命令可确认；模型只有读取、建议修订、结束本轮工具。

**技术：** Python 标准库、现有 CommandBoundary、原生 HTML/CSS/JS、pytest、Fake 模型。

## 约束及设计

- 保留全部共享未提交修改；不切分支、不提交推送、不启动生产 Runtime、不重启 8877、不调用真实模型。
- 新书创建由父根锁及持久化创建意图管理；拒绝危险名称与大小写碰撞，排他占用，不覆盖已有项目，半初始化可恢复。
- 领域存储唯一权威：候选 revisions、confirmed versions、唯一 current；哈希覆盖规范化内容块和未决问题，确认绑定 project/session/revision/hash/expected confirmed version。
- story scope 明确使用空 chapter_number，不借用章节 0；旧章任务兼容。
- 模型逐步 JSON 工具协议，有步数和输入预算；坏包不写候选，确认/发布无工具入口；每步通过单次透明 capture → RuntimeRunner。
- 第一章受理时冻结正式设定 text/version/hash/source_ref。新书无确认不得执行；运行期间新确认不会改变冻结输入。必需内容超预算明确失败。
- Web 项目 registry 惰性装配；项目路由与所有故事对象均绑定 project/scope/session；读取故事不写文件。
- UI 沿用 Writer 排版和颜色：左侧对话、右侧可编辑候选及正式设定，窄屏堆叠。只提供新书入口、故事讨论及第一章跳转，不重整首页、不增加投影卡片。确认显示指定版本，保存编辑后才可确认；后续讨论保留已确认版。

## 验收重点

路径保留名/点路径/尾点空格/清洗碰撞/并发；确认旧 revision/跨项目会话/同键异载荷；中断后恢复；坏包与非法工具；未确认阻断；五类设定正文真实入模、精确 included 快照；晚到响应隔离；旧 Writer 回归。

## 任务

- [x] S1 领域与安全创建：新增 `story_architecture_store.py`、`story_architecture_command.py`、`novel_project_command.py`；修改 `novel_project.py`。测试 `test_story_architecture.py` 验证版本/CAS/幂等/恢复，`test_novel_project.py` 回归创建。
- [x] S2 Runtime：扩 `agent_conversation_store.py`/`agent_runtime.py`，新增 `story_architecture_agent.py`/`story_context.py`。测试两种 Fake Idea 自主顺序、坏包/非法工具/预算与重试，冻结正式版注入第一章。
- [x] S3 HTTP/UI：新增 `story_web.py`/`project_registry.py` 和 `web/story.*`；最小修改 Web 路由与脚本、Writer 项目请求前缀。测试完整 HTTP 链及浏览器 Fake 临时根链。
- [x] S4 架构与回归：版本化透明委派 manifest，精确允许新增单步入口并增加正反例；运行故事、Writer 相关 pytest/JS，记录实际结果和限制后回传总控。

## 工作记录

DONE：S1–S4 实现与隔离验收；270 项组合 Python 回归、最新接线/架构专项 75 项、43 项 JS 行为、受保护 Chromium 完整链通过，详见 `.backup/story-validation/`。
CURRENT：首版实现交付总控。
TODO：总控独立复审与目标验收；不自标总目标完成。

独立复审修复：P1 请求校验前恢复、P1 章节恢复投影、P2 Feedback Query touch、P2 marker 中断窗口均已复现并修复。组合回归314项、最新专项19项、JS44项、受保护Chromium主链通过；细节见 `docs/story-review-fixes-2026-10-18.md`。当前等待总控再次复审，不自标验收。

Ruling：保留当前 checkout 和全部共享未提交改动，不建分支、不提交 — 遵循总控明确授权范围。
Ruling：单文件原子聚合承载候选/不可变确认/current/操作回执 — 同时消除确认与指针中断窗口，简化首版恢复。
Ruling：独立复审交由总控已有审查会话 — 不重叠写入，不额外派开发子代理。
事件：早期默认工厂绑定过早导致一项旧测试可能触达真实客户端；已中断且修复，远端接收/计费不确定。详见 `docs/story-architecture-v1.md` 测试隔离事件，不得在交付中省略。
