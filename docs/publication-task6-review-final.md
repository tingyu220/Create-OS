# 自动发布任务 6 最终定向复审

状态：**已完成（P1 定向复审通过，隔离范围）**

复审基准：最新代码与 `docs/publication-v1-report.md`。本次只读复审未修改代码，未访问真实番茄 URL、账号、模型、生产 Runtime 或 8877。

## 结论

- **P0：0**。未发现密码/Cookie/页面凭据落盘、跨书状态串写或不可逆外部写入。
- **P1：0**。旧复审列出的 5 个 P1 均已验证闭环，相关安全门槛通过。
- **P2：2**。核对后的 Fake 证据新鲜度仍有展示瑕疵；1440/390 截图仍是合成页面，只能证明合成面板布局。
- **是否通过：通过（P1 修复与隔离验收通过；不代表真实番茄或生产上线通过）。**

## 旧复审 5 个 P1

| 项目 | 结论 | 证据 |
| --- | --- | --- |
| `WorkspaceRequestHandler` 接入 `/api/publication` | 通过 | `creative_os/web_workspace.py:140-145`、`:292-297` 真实转发 GET/POST；`create_server(..., publication_orchestrator=...)` 在 `:520-553` 绑定。 |
| Writer 使用 tomato 目标及十二项 checks | 通过 | `creative_os/web/writer.js:18-31` 默认 `tomato`，带作品/章节/标题/平台目标及 12 项检查；Node 测试逐项断言字段。 |
| `paused + pause_reason=version_conflict` 禁用运行 | 通过 | `creative_os/web/publication-panel.js:40-48` 同时识别状态和暂停原因，显示“版本冲突”并禁用运行；Node 回归通过。 |
| unknown 无明确章节 ID + 正文哈希不得升级 published | 通过 | `creative_os/publication_web.py:157-166` 只有非空 `platform_chapter_id` 且 `content_sha256` 等于快照哈希才升级；仅 `{status: unknown}` 或含 mismatch 仍保持 unknown/抛出核对错误。 |
| `connect()` 不覆盖持久化 session/page，先核对再恢复 | 通过 | `creative_os/publication_browser_workbench.py:202-214` 在已有引用时先比对 session/page，再进入 `reconcile_page()`；错 session、错页、错作品或哈希均拒绝，原 `browser`/检查点不被替换。 |

## 额外核对

### 真实 Writer 路由测试

`tests/test_publication_writer_route.py` 通过 `create_server(WorkspaceWebAdapter(...), publication_orchestrator=...)` 启动工作区服务器，并向 `/api/publication` 发起 GET/POST，不是只调用独立 `create_publication_server()`。结果：**2 项通过**；与浏览器工作台和 HTTP 回归合计 **18 passed**。

### 跨书证据标签

`scripts/validate_publication_ui.py:177-183` 已使用每个事件自身的 `book_id`，不再把乙书 POST 证据硬编码成甲书。最新产物中 `book-a` 响应的 `work_id` 均为 `book-a`，`book-b` 均为 `book-b`；`cross_book_isolation: true`。平台证据带 `platform: tomato`、`work_id`、`operation_id` 和章节 ID。

### 1440/390 是否为合成页

是。`scripts/validate_publication_ui.py:70-103` 直接拼接最小 HTML，只渲染“写作工作台”占位内容与持久化面板，再用 Playwright 截图；未加载 `writer.html`、`writer.js`，也未走 Workspace 页面导航。因此只能证明合成面板在 1440/390 下无横向溢出，不能证明真实 Writer 页面布局或浏览器端到端行为。该限制已在 v1 报告中明确，列为 P2。

## P2

### P2-1：核对后的证据对象仍带旧 unknown 标记

`PublicationOrchestrator.reconcile()` 在有明确章节 ID 与正文哈希时将任务置为 `published`，随后调用 `capture_evidence()`（`creative_os/publication_web.py:167-170`）。Fake 适配器保存的原始响应仍是 `status: unknown, pause_reason: response_lost`，所以最终状态会出现：任务 `published`，但嵌套 `evidence.chapter.status=unknown`、`evidence_available=false`。这不影响“无证据不得升级”的门槛，也不造成跨书泄漏，但会让审计查看者误以为已发布没有有效证据。建议后续让核对成功后的证据对象使用核对返回的 published 状态或重新生成明确的已核对证据。

### P2-2：视口截图不是实际 Writer 页面

1440/390 产物是隔离 Fake 面板的合成页，真实番茄 DOM、真实 Writer 三栏布局、真实路由与键盘交互均未验证。保留为隔离验收证据，不应外推为生产 UI 通过。

## 回归命令

- `python -m pytest tests/test_publication_writer_route.py tests/test_publication_browser_workbench.py tests/test_publication_http.py -q` → **18 passed**。
- `python -m pytest tests/test_publication_*.py -q` → **301 passed, 6 skipped**。
- `node --test tests/test_publication_ui.js tests/test_writer_save_scope_ui.js tests/test_writer_lessons_ui.js tests/test_writer_sources_ui.js tests/test_workspace_shell_assets.js` → **27 passed**。

## 最终判定

**P1 定向复审通过，任务在 Fake/隔离边界内通过。** P2-1/P2-2 不阻断本轮安全修复，但在接入真实页面或对外宣称生产可用前应处理/补证据。
