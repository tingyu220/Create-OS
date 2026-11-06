# 自动发布任务5报告

状态：**已完成**

实现文件：
- `creative_os/web/publication-panel.js`
- `creative_os/web/writer.js`
- `creative_os/web/writer.html`
- `tests/test_publication_ui.js`

实现内容：
- 新增 Writer 自动发布面板，使用原生 `button`，展示作品、章节、正式稿版本（source revision）、正文哈希、当前步骤、状态、证据、检查阻断原因和错误。
- 接入任务4 HTTP 约定：GET `/api/publication?operation_id=...` 查询队列状态，POST `/api/publication` 发送 `run`、安全暂停、立即暂停、`continue` 与 `reconcile` 控制。
- `unknown` 统一显示“需核对”；安全暂停与立即暂停分别显示；已发布、版本冲突、检查失败禁止再次运行。
- Writer 切章时按作品、章节、epoch 清理面板状态；跨书切换不会残留上一书结果。所有服务响应均通过 `textContent` 或纯文本 `pre` 展示，不处理账号密码。
- 任务5仍只使用 Fake/guard；未访问真实番茄、未连接 Runtime/8877。

TDD 验证：

```text
先运行：node --test tests/test_publication_ui.js
结果：4 failed（RED，publication-panel.js 尚不存在）

实现后：node --test tests/test_publication_ui.js tests/test_writer_save_scope_ui.js tests/test_writer_lessons_ui.js tests/test_writer_sources_ui.js
结果：21 passed
```

限制：Writer 现有服务端尚未提供 `/api/publication` 路由或自动提交 operation_id；面板会在查询失败时显示“发布状态暂不可用”，不影响普通写作入口。未 commit、push 或 merge。

## 复审修复（追加）

复审指出的 P1/P2 已修复：

- 深链 `publication_operation_id` 在首次 `setScope()` 时保留，首次选章会继续 GET 查询，切换到新作品/章节才清除旧 operation。
- “运行发布”无 operation_id 时先用 Writer 当前快照发送 `submit`，保存返回的 operation_id 后再发送 `run`；已有 operation_id 仍直接运行。
- 面板新增暂停范围选择：全局、当前作品、当前章节、当前步骤；步骤选择明确传递 `step`，安全暂停、立即暂停和继续均携带范围语义。
- 证据 `pre` 增加 `overflow-wrap:anywhere`、`word-break:break-word`，覆盖 390px 长无空格内容。
- 报告中的安全输出表述限定为“发布面板输出使用 textContent/纯文本 pre”；Writer 既有版本列表的 `innerHTML` 未在本任务扩大范围修复。

修复后验证：

```text
node --test tests/test_publication_ui.js tests/test_writer_save_scope_ui.js tests/test_writer_lessons_ui.js tests/test_writer_sources_ui.js
结果：24 passed
```

状态：**已完成**（仍仅 Fake/guard，未接真实平台、Runtime/8877，未 commit）。

## P1 最终修复（追加）

修复 `control()` 的请求构造顺序：无 operation_id 时先提交快照，保存返回的 operation_id，再重新构造并发送 `run` 请求，避免第二个请求携带 `operation_id: null`。新增回归断言覆盖该请求字段。

验证：

```text
先运行新增断言：1 failed（run 请求仍为 null，RED）
修复后相关 Node 回归：25 passed
```
