# 自动发布任务5：Writer 界面接线

先读任务4报告/复审及现有 `creative_os/web/writer.js`、`writer.html`、`index.html`。只做界面接线，不访问真实番茄。

## 必须实现

- 新增 `creative_os/web/publication-panel.js`，展示作品/章节/正式稿版本/正文哈希、检查状态、当前步骤、发布状态、证据和错误。
- 接入现有 Writer 入口与任务4 HTTP：队列状态 GET、控制 POST、暂停/继续、状态未知核对。
- 安全暂停与立即暂停分开显示；全局/单书/单章/步骤范围明确；未知状态显示“需核对”，不得显示为失败或成功。
- 已发布和版本冲突显示不可重发；检查失败显示阻断原因；普通写作入口保持可用。
- 所有动作使用原生 button、可键盘聚焦；错误和状态使用 textContent，不注入不可信 HTML；不展示或保存账号密码。
- 1440 与 390 视口无横向溢出，跨书切换后不得残留上一书发布结果。

## TDD

先写 `tests/test_publication_ui.js` 失败测试，覆盖状态卡片、暂停/立即暂停/继续、unknown、错误、键盘和跨书清理；运行 `node --test tests/test_publication_ui.js` 确认 RED，再最小实现 GREEN。

## 限制

仅 Fake/guard；不接真实番茄 URL、账号、Runtime、8877，不 commit/push/merge。完成后写 `docs/publication-task5-report.md`。
