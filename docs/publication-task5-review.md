# 自动发布任务5独立复审（最终轮）

结论：**通过**。

已核对剩余 P1 修复：`publication-panel.js` 现在在无 operation_id 的 `run` 请求中先完成 `submit`，保存返回的 operation_id 后再构造 run 请求体；新增测试明确断言第二个 POST 的 `operation_id === "created-op"`，不再携带 null。

本轮验证：

```text
node --test tests/test_publication_ui.js tests/test_writer_save_scope_ui.js tests/test_writer_lessons_ui.js tests/test_writer_sources_ui.js
结果：25 passed
```

已覆盖并确认：

- 深链 operation_id 在首次 setScope 后保留并可 GET 查询；跨书/跨章/epoch 切换会清理旧结果。
- 无 operation_id 时 submit → run 顺序正确，run 携带 submit 返回的 operation_id。
- 全局、单书、单章、步骤暂停/继续范围可由 UI 明确表达；安全暂停与立即暂停分开。
- unknown 显示“需核对”，不会伪装成失败或成功；已发布、版本冲突、检查失败禁止重发。
- 作品、章节、版本、正文哈希、步骤、证据和错误使用安全文本输出；原生 button 可键盘操作。
- 证据区域在 390px 下使用 `overflow-wrap:anywhere`、`word-break:break-word`，长无空格内容可换行。
- 任务仍限定 Fake/guard，未连接真实番茄、Runtime 或 8877；Writer 服务端未提供 `/api/publication` 路由的限制已在报告中保留并收窄表述。

状态：**已完成 / 通过**。
