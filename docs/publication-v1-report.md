# 自动发布 v1 隔离验收报告

状态：**已完成（隔离验证完成）**

任务6复审 P1 已修复：Writer 工作区现接入 `/api/publication` GET/POST；Writer 提交使用 tomato 目标并携带十二项检查；后端 `paused/version_conflict` 在面板中禁用运行；未知核对只有明确章节标识和正文哈希证据才可升级；中断状态的 `connect()` 会先核对原 session/page，不覆盖持久化引用。

本任务实现了持久化浏览器工作台控制器，并把它与任务 1—5 的 Fake 番茄适配器、队列和编排器串联。控制器持久化 `session_id`、`page_id`、平台、作品、章节、当前步骤、`operation_id`、正文 SHA-256、登录状态和暂停/重连标志；不会写入密码、Cookie 或页面凭据。工作台面板固定在右侧，390px 时改为单列，长哈希可换行。

## 实现与证据

- `creative_os/publication_browser_workbench.py`：`PersistentBrowserWorkbenchController`、`BrowserSessionState`、`FakeBrowser/FakePage`。状态文件使用临时文件 + 原子替换；浏览器关闭/崩溃进入 `browser_session_interrupted`，重连必须先核对 session/page、作品、章节和正文哈希，再允许继续。
- `creative_os/publication_web.py`：版本冲突终态不会被检查结果覆盖；未知状态核对为已发布后重新采集证据。
- `creative_os/web/writer.html`、`creative_os/web/writer.css`：Writer 右侧持久化平台浏览器面板和响应式布局。
- `scripts/validate_publication_ui.py`：使用两个临时作品、两个独立 Fake 会话、随机本地端口，输出 JSON、POST/响应记录、正文哈希、平台证据、HTML 和两种视口截图。
- `tests/test_publication_browser_workbench.py`：持久化、无密码、暂停/崩溃重连、目标/哈希核对、跨平台标签隔离。

验证产物位于 `artifacts/publication-v1-validation/`（运行脚本后生成）：

- `publication-validation.json`
- `publication-workbench.html`
- `publication-1440.png`
- `publication-390.png`

## 测试矩阵

| 场景 | 结果 | 证据 |
| --- | --- | --- |
| 正式稿快照 → 12 项检查 → 填充 → 发布 → 核对 → 证据 → 下一章 | 通过；book-a/book-b 各发布第 1、2 章 | JSON 中 `books`、`hashes`、`evidence` |
| 两个临时作品隔离 | 通过；`cross_book_isolation: true` | JSON |
| 检查失败阻断 | 通过；状态 `failed`，未填充/发布 | JSON `check_blocked` |
| 版本冲突 | 通过；状态 `paused`、原因 `version_conflict` | JSON `version_conflict` |
| 丢响应 → unknown → 先核对再继续 | 通过；先 `unknown`，核对后 `published` | JSON book-a 第 2 章事件 |
| 验证码、登录失效 | 通过；均停留 `paused` | JSON `captcha_login` |
| 安全暂停、立即暂停 | 通过；页面输入和检查点保留 | JSON `pause_modes` |
| 浏览器关闭/崩溃后重连 | 通过；错误页不能直接恢复，匹配页面先核对后继续 | JSON `pause_reconnect` |
| GET 刷新纯读 | 通过；GET 前后 operation/status 不变 | JSON `get_read_only` |
| 1440/390 视口、无横向溢出 | 通过；Playwright 断言与截图 | 两张 PNG |
| 持久化控制器窄测 | 3 passed | `python -m pytest tests/test_publication_browser_workbench.py -q` |
| Workspace 发布路由与 P1 回归 | 18 passed | `python -m pytest tests/test_publication_writer_route.py tests/test_publication_browser_workbench.py tests/test_publication_http.py -q` |
| 全部 publication Python 测试 | 301 passed, 6 skipped（含本轮新增） | `python -m pytest tests/test_publication_*.py -q`（PowerShell 枚举文件后执行） |
| 受影响 Node UI 测试 | 27 passed（含真实 tomato/check 字段及版本冲突） | `node --test tests/test_publication_ui.js tests/test_writer_save_scope_ui.js tests/test_writer_lessons_ui.js tests/test_writer_sources_ui.js tests/test_workspace_shell_assets.js` |
| Python 编译 | 通过 | `python -m py_compile creative_os/publication_browser_workbench.py scripts/validate_publication_ui.py` |

## Fake 限制与未验证项

- Fake 浏览器不执行真实 Chromium 持久化上下文、真实网络请求、真实番茄 DOM 或风控流程；端口仅用于随机隔离标识。
- 未访问真实番茄 URL、未登录真实账号、未保存密码，未接真实模型、生产 Runtime 或 8877。
- Writer 后端现有服务未提供真实番茄会话管理接口；右侧面板当前展示控制器状态，实际平台动作仍由适配器边界承接。
- 截图仍为隔离页面面板渲染，不代表真实番茄 DOM 兼容性；真实 Writer 路由已由 HTTP guard 测试覆盖。
- 真实番茄页面字段、验证码交互、登录续期和发布结果页面质量需要后续在专门的人工测试账号上验证；本报告不代表生产上线。
