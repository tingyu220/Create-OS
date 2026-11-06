# 自动发布任务2：逐书逐章队列与恢复

先读 `docs/publication-task1-brief.md`、`docs/publication-task1-report.md`、`docs/publication-task1-review.md` 和 `creative_os/publication_models.py`。仅实现队列，不接真实平台。

## 必须实现

- 在 `creative_os/publication_queue.py` 提供按 book_id 隔离的队列；同一本书严格按 chapter_number 顺序，不同书可独立推进。
- 入队使用 `ChapterSnapshot` 和任务1的幂等键；同一快照重复入队复用 operation_id，不重复生成任务。
- 已发布章节不可重发；source_revision 或 content_sha256 冲突时进入版本冲突暂停。
- 安全暂停等待当前动作到安全检查点；立即暂停可中断当前动作并生成 checkpoint。
- 发布动作中断、响应丢失或结果不确定时进入 `unknown`，继续前必须先执行 reconcile 查询，不能直接重发。
- 提供纯内存实现和可序列化队列快照，供后续 HTTP 与 Fake 适配器使用。

## TDD

先在 `tests/test_publication_queue.py` 写失败测试，覆盖同书顺序、跨书隔离、已发布防重发、版本冲突、unknown 恢复核对、安全/立即暂停、幂等入队；先运行 `python -m pytest tests/test_publication_queue.py -q` 确认 RED，再最小实现 GREEN。

## 限制

仅 guard 测试；不接番茄、不启动 Runtime、不操作 8877、不写真实书、不 commit/push/merge。完成后写 `docs/publication-task2-report.md`。
