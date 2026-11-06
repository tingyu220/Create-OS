# 自动发布任务2复审

结论：**通过（无 P0/P1/P2）**

复审范围：
- `docs/publication-task2-brief.md`
- `docs/publication-task2-report.md`
- `docs/publication-task1-brief.md`
- `docs/publication-task1-report.md`
- `docs/publication-task1-review.md`
- `creative_os/publication_models.py`
- `creative_os/publication_queue.py`
- `tests/test_publication_queue.py`

核对结果：

- **同书顺序与跨书隔离：通过。** `next_ready(book_id)` 只收集目标书任务并按 `chapter_number` 排序；首个未发布任务必须处于 `ready_to_publish` 才返回，暂停、未知、版本冲突会阻塞该书后续章节；其他书可独立推进。
- **平台范围与版本冲突：通过。** 幂等键包含平台、作品、章节、`source_revision` 和 `content_sha256`；版本冲突扫描同时限定 `book_id`、章节、平台和作品，不会把不同平台或不同作品的版本误判为冲突。
- **幂等入队与已发布防重发：通过。** 相同快照经 `_by_key` 复用原 `operation_id`；已发布任务重复入队仍返回原任务，`start()` 拒绝已发布状态。
- **安全暂停与立即暂停：通过。** 安全暂停只记录请求，直到显式 `checkpoint()` 才转为暂停；立即暂停立即生成 `interrupted` 检查点并转为暂停。
- **unknown 恢复门槛：通过。** `mark_unknown()` 创建带 `resume_prerequisite="reconcile"` 的未知检查点；`resume()` 在核对前抛出 `UnknownStatusError`，`reconcile()` 拒绝仍为 `unknown` 的结果并记录已核对状态。
- **JSON 快照恢复：通过。** 任务、快照、检查点、枚举值可稳定 JSON 往返；恢复后重建 `_tasks` 与 `_by_key`，重复入队仍复用原操作号。

验证：

```text
python -m pytest tests/test_publication_queue.py tests/test_publication_models.py -q
11 passed in 0.10s
```

全量报告中的 3 个失败已逐项复现，均属范围外既有问题：

1. `test_author_home_query.py::test_http_route_uses_selected_project_and_does_not_mutate_projects` 在 `creative_os/web_workspace.py:create_server` 读取测试替身 `ReadOnlyRegistry.root` 时失败，属于工作区 HTTP 项目注册，不触及发布队列。
2. `test_production_mainline_integration.py::test_readiness_points_to_next_chapter_after_current_completion` 读取生产就绪报告时章节号未更新，属于生产资料断言，不触及发布队列。
3. `test_project_catalog.py::test_confirmed_story_without_manuscript_has_explicit_writer_entry` 因故事确认调用者权限校验失败，属于故事架构权限，不触及发布队列。

限制仍与任务报告一致：仅纯内存队列和 guard 测试，未接触真实平台、账号、浏览器、生产 Runtime 或 8877。
