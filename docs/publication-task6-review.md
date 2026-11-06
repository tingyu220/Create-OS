# 自动发布任务6独立复审

状态：**部分完成（暂不通过任务6全链验收）**

复审范围：docs/publication-task6-brief.md、docs/publication-v1-report.md、持久化浏览器工作台、发布编排/HTTP 边界、Writer 页面与样式、发布面板、验证脚本及相关测试。复审为只读；未修改实现，未连接真实番茄 URL、账号、模型、生产 Runtime 或 8877。

## 结论摘要

隔离 Fake 层的持久化、正文哈希、未知状态核对、两本临时作品隔离、暂停/重连窄测和 GET 纯读均有证据；但实际 Writer 页面没有接入发布 HTTP 路由，且 Writer 的提交快照使用 platform: "fake"、不携带十二项检查结果。即使把路由接上，当前提交也会因缺少检查证据和平台不匹配而失败。版本冲突在后端保留为 paused/version_conflict，但前端只按不存在的 status: "version_conflict" 禁止运行，真实后端响应会把“运行发布”按钮留为可用。

## 验证记录

- python -m pytest tests/test_publication_browser_workbench.py -q：**3 passed**。
- python -m pytest 加载 tests/test_publication_*.py：**297 passed, 6 skipped**。
- node --test tests/test_publication_ui.js tests/test_writer_save_scope_ui.js tests/test_writer_lessons_ui.js tests/test_writer_sources_ui.js tests/test_workspace_shell_assets.js：**25 passed**。
- python -m py_compile creative_os/publication_browser_workbench.py creative_os/publication_web.py scripts/validate_publication_ui.py：通过。
- python scripts/validate_publication_ui.py --output artifacts/publication-task6-review-validation：isolated_validation_complete；两本 Fake 作品、随机本地端口、正文 SHA、unknown→reconcile、验证码/登录失效暂停及 1440/390 合成面板截图均生成。
- 该脚本的 post_responses 对所有事件硬编码 book_id: "book-a"，因此乙书 POST 证据标签不可信；evidence 列表同时保留丢响应时的旧 unknown 证据，未替换为核对后的最新证据。

## 通过项

- BrowserSessionState.to_dict() 只序列化白名单字段，持久化 session_id、page_id、平台、作品、章节、当前步骤、operation_id、正文 SHA、登录/暂停/重连状态；未发现密码、Cookie 或页面凭据落盘。
- 状态文件采用临时文件、fsync 和原子替换；控制器面板声明右侧固定标识，长哈希可换行。
- 正常 reconnect() 会核对 session、page、work、chapter 和正文 SHA；不匹配会抛出 ReconnectionMismatch，恢复前不能直接 resume()。
- Fake 编排器能保留 unknown 并要求先 query_result；核对成功后再转 published，不会直接重发。
- 两本临时作品使用独立 Fake 页面/会话；隔离脚本的 cross_book_isolation 为 true。GET 查询前后 operation/status 不变。
- 安全暂停、立即暂停、验证码、登录失效和响应丢失路径在 Fake/guard 中有状态证据；相关 UI 按钮可聚焦，Node 行为测试通过。

## P1

### P1-1：Writer 页面未接入发布 HTTP 路由，实际全链无法从 Writer 运行

creative_os/web/writer.js:18-20 和 creative_os/web/publication-panel.js:7 会向 /api/publication 发起提交/控制/GET 请求；但 creative_os/web_workspace.py:129-320 的 WorkspaceRequestHandler 没有 /api/publication 的 GET/POST 分支，静态路由也没有该 API。发布服务器只存在于独立的 create_publication_server()，没有接入 Writer 工作台服务。

影响：真实 Writer 页面刷新、提交、暂停、核对都会得到工作区服务的 404，任务简报要求的“正式稿快照→检查→填充→发布→查询→台账→下一章”不能在产品页面完成。

### P1-2：Writer 提交参数不能通过十二项检查，也没有正确的番茄平台目标

creative_os/web/writer.js:18 的 getSnapshot() 固定发送 target.platform: "fake"，且没有发送 checks。creative_os/publication_web.py:38-45 会把缺失检查初始化为全 false；publication_web.py:63-68 因此把无检查证据的提交置为 failed。同一提交在 publication_web.py:74-78 还会进入适配器目标核对，Fake 番茄适配器要求平台为 tomato，而 Writer 发的是 fake。

影响：即使补上 API 路由，Writer 的“运行发布”仍会安全失败，无法进入填充/发布步骤。现有 Node 测试用 stub 响应绕过了这一实际边界，不能证明页面到后端的全链。

### P1-3：版本冲突的后端状态与前端禁用条件不一致

creative_os/publication_queue.py:67-75 和 publication_web.py:59-62 将新版本冲突保存为 status: paused、pause_reason: version_conflict，这是后端隔离验证中实际返回的形态。creative_os/web/publication-panel.js:46-47 只在 status 为 published 或字面量 version_conflict 时禁用运行；它没有把 pause_reason === version_conflict 视为终态。

影响：真实后端响应会显示普通“已暂停”，运行按钮保持可用。后端当前 run() 仍返回暂停，不会立即再次发布，但 UI 没有满足“版本冲突不可静默重发”的安全边界，后续接入恢复/重试时存在误操作窗口。

### P1-4：核对结果仍为 unknown 时被错误升级为 published

creative_os/publication_web.py:154-165 对 adapter.query_result() 返回的任何无 mismatch 的 unknown 都直接改成 published；只有结果字典包含字符串 mismatch 才抛出 UnknownStatusError。只读探针把丢响应后的 query_result 替换为 {status: "unknown"}，reconcile() 仍返回 published，且 evidence_available 为 false。

影响：平台无法确认结果时，系统可能记录“已发布”并允许后续章节继续，造成台账与平台实际状态不一致。核对后仍未知应继续保持 unknown、要求人工处理或再次核对，不能凭缺少 mismatch 字段宣称成功。

### P1-5：中断后的 connect() 可先覆盖持久化引用，违反先核对并破坏恢复

creative_os/publication_browser_workbench.py:198-212 的 connect() 在已有 resume_required 时仍会直接替换 session_id、page_id 和当前 page；它只把 reconnect_verified 设为 false，没有先核对原 session/page/作品/章节/正文 SHA。只读探针可用不同 session 和另一部作品调用 connect() 成功，随后原会话标识已被覆盖，不能再按旧检查点重连。

影响：关闭/崩溃后的错误页面可能进入工作台状态，恢复流程不再保持“先核对再恢复”的不可绕过性。当前测试只覆盖 reconnect() 错页拒绝，未覆盖 connect() 覆盖检查点。

## P2

### P2-1：复审脚本证据标签和证据新鲜度不准确

validate_publication_ui.py:177-183 将乙书 POST 响应标成甲书；run_chain() 在核对后仍保留丢响应阶段的旧 evidence 事件，导致最终 JSON 的 evidence 同时出现 status: unknown 和核对成功状态。它不影响 Fake 编排器状态，但降低审计产物对“哪本书、哪次核对证据”的可信度。

### P2-2：1440/390 截图是合成面板，不是实际 Writer 页面

validate_publication_ui.py:70-103 构造临时 HTML，只渲染一个合成的工作台 aside；未加载 writer.html、writer.js、Workspace 路由，也未验证真实页面脚本错误、发布 API 404、键盘操作或实际三栏布局。视口无横向溢出结论只能适用于该合成页面。

### P2-3：重连核对未比较作品标题、当前步骤和 operation_id

reconcile_page() 核对 session/page、work_id、chapter_number、正文 SHA，但没有比较持久化的 work_title、current_step 或 operation_id。任务规格最低要求页面和正文先核对，故归为增强项；若真实平台存在同作品多标签/章节标题漂移，建议补充这些字段的绑定检查。

## P0

无。当前未发现密码/Cookie 落盘、跨书数据泄漏或不可逆写入证据；所有复审动作均在 Fake/临时目录内。

## 最终判定

**部分完成。** 隔离 Fake 验收链和控制器窄测基本成立，但 P1-1/P1-2 使实际 Writer 页面无法完成自动发布，P1-3/P1-4/P1-5 使版本冲突、未知核对和中断恢复的安全边界不完整。修复并补充真实 Writer HTTP/浏览器证据前，不能将任务6标为“已完成”或“隔离全链验收通过”；既有 v1 报告应保留“Fake 隔离限制”，不能外推为生产上线。

