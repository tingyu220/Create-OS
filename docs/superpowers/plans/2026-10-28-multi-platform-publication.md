# 多平台自动发布实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** 在不接官方 API 的前提下，让系统对用户已打开的番茄作品自动逐章发布正式稿，并为其他平台保留适配器接口。

**Architecture:** 发布编排器只消费正式稿快照和检查结果；平台差异封装在浏览器适配器中。队列、检查点、台账和暂停恢复与具体平台解耦，番茄首版通过用户现有登录浏览器会话运行。

**Tech Stack:** 现有 Python HTTP/Web 层、Python 持久化、Node 浏览器界面、Playwright/Fake 浏览器、现有 guard 测试体系。

## Global Constraints

- 不创建作品、不自动登录、不保存密码、不绕过验证码或风控。
- 正式发布前不等待逐章人工审批，但保留总开关、安全暂停、立即暂停、继续和状态未知锁。
- 仅临时项目、Fake 浏览器和随机端口验证；不接触真实番茄账号、真实模型、生产 Runtime 或 8877。
- 已发布、状态未知、版本冲突不得静默重发；未确认检查结果不得进入发布。
- 不 commit/push/merge，除非用户另行确认。

## 文件边界

- Create: `creative_os/publication_models.py` — 任务、检查点、台账、平台能力和状态枚举。
- Create: `creative_os/publication_queue.py` — 逐书逐章顺序、幂等和并发限制。
- Create: `creative_os/publication_adapter.py` — `PlatformAdapter` 协议与 Fake 实现。
- Create: `creative_os/tomato_browser_adapter.py` — 番茄浏览器动作和页面核对。
- Create: `creative_os/publication_web.py` — HTTP 查询、暂停、继续和控制命令。
- Create: `creative_os/web/publication-panel.js` — 队列、检查点、证据和控制界面。
- Modify: `creative_os/web/index.html`, `creative_os/web/writer.html`, `creative_os/web/writer.js` — 入口和正式稿发布状态接线。
- Create: `tests/test_publication_models.py`, `tests/test_publication_queue.py`, `tests/test_publication_http.py`, `tests/test_publication_ui.js`。
- Create: `scripts/validate_publication_ui.py` — 临时 Fake 浏览器全链验证。
- Create: `docs/publication-v1-report.md` — 验收矩阵和限制。

---

### Task 1: 状态、快照和台账模型

**Files:** `creative_os/publication_models.py`; `tests/test_publication_models.py`

- [ ] 写失败测试：覆盖 `PublicationStatus`、安全/立即暂停、状态未知、正文 SHA-256、`operation_id` 幂等键和序列化往返。
- [ ] 运行 `python -m pytest tests/test_publication_models.py -q`，确认测试先失败。
- [ ] 实现不可变章节快照、检查点、发布台账和平台能力声明；状态未知必须携带核对要求。
- [ ] 重跑同命令，确认全部通过。

### Task 2: 队列与恢复

**Files:** `creative_os/publication_queue.py`; `tests/test_publication_queue.py`

- [ ] 写失败测试：同一本书严格顺序、不同书隔离、已发布不重发、版本冲突暂停、未知状态恢复前查询。
- [ ] 运行窄测试并确认失败。
- [ ] 实现单书互斥、跨书并行、检查点恢复和幂等操作；立即暂停只在动作边界允许继续，发布中断转未知。
- [ ] 重跑队列测试并记录通过数。

### Task 3: 平台适配器协议与番茄 Fake

**Files:** `creative_os/publication_adapter.py`, `creative_os/tomato_browser_adapter.py`; `tests/test_publication_adapter.py`

- [ ] 写失败测试：已打开作品核对、章节标题/编号核对、填充、发布、查询、验证码/登录失效、丢响应。
- [ ] 运行窄测试确认失败。
- [ ] 实现平台协议和 Fake 番茄适配器；不得创建作品或保存凭据，丢响应返回未知而非失败。
- [ ] 运行适配器测试，保留页面证据接口。

### Task 4: 自动检查与发布编排 HTTP

**Files:** `creative_os/publication_web.py`; `tests/test_publication_http.py`

- [ ] 写失败测试：正式稿版本、字数/结构、设定/战斗、敏感内容、平台目标、正文哈希全部通过才允许发布；任何失败都暂停。
- [ ] 运行窄测试确认失败。
- [ ] 实现编排命令、总开关、单书/单章/步骤控制、发布核对和结果台账；普通写作命令不受阻断。
- [ ] 覆盖 GET 纯读、暂停/继续 POST、状态未知先核对和重复命令幂等。

### Task 5: 现有 Writer 界面接线

**Files:** `creative_os/web/publication-panel.js`, `creative_os/web/index.html`, `creative_os/web/writer.html`, `creative_os/web/writer.js`; `tests/test_publication_ui.js`

- [ ] 写失败 UI 测试：队列状态、检查失败、已发布/未知区分、安全暂停、立即暂停、继续、证据和错误可见且键盘可操作。
- [ ] 运行 `node --test tests/test_publication_ui.js` 确认失败。
- [ ] 接入现有 Writer 入口和正式稿选择；显示书/章/版本/哈希，不显示或保存账号密码。
- [ ] 重跑 Node UI 测试并核对 1440/390 CSS 无横向溢出。

### Task 6: 持久化浏览器工作台与全链验收

**Files:** `scripts/validate_publication_ui.py`, `docs/publication-v1-report.md`

- [ ] 实现并验证持久化浏览器会话控制器：工作台右侧固定平台窗口/标签页，保存 session/page/作品/章节/步骤/operation_id/正文哈希；不保存密码。
- [ ] 用两个临时项目和随机端口验证自动检查→填充→发布→核对→台账→下一章；覆盖安全暂停、立即暂停、继续、丢响应、验证码、登录失效、浏览器关闭后重连、版本冲突、跨书隔离和纯 GET 刷新。
- [ ] 用 1440 与 390 视口保存截图、POST/响应、正文哈希和页面证据。
- [ ] 运行全部 `test_publication_*.py`、受影响既有测试和 Node UI 测试；禁止真实平台写入。
- [ ] 记录 Fake 限制、未验证真实番茄页面质量和不阻断的证据增强建议。

## 交付门槛

每个任务必须先有失败测试、最小实现、窄回归和独立只读复审；所有任务通过后才可声称“隔离验证完成”。本计划不包含真实番茄账号首次发布或生产部署。
