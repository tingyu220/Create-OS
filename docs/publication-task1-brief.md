# 自动发布任务1：状态、快照和台账模型

阅读规格 `docs/superpowers/specs/2026-10-27-multi-platform-publication-design.md` 与计划对应任务。只创建模型和测试，不接真实平台。

## 必须实现

- `PublicationStatus`：writing、checking、ready_to_fill、filling、ready_to_publish、publishing、verifying、published、failed、unknown、paused。
- 安全暂停与立即暂停的模式枚举。
- 正式稿不可变章节快照，至少包含 book_id、chapter_number、source_revision、content、content_sha256。
- 检查点，包含当前步骤、operation_id、正文哈希、暂停模式和恢复前置条件。
- 发布台账，包含平台名、平台作品标识、平台章节标识、状态、发布时间、证据引用、operation_id。
- 状态未知必须标记需要先核对，不能序列化为普通失败。
- 幂等键由平台、作品、章节、source_revision、content_sha256 组成；同键重复提交返回同一 operation_id。
- 所有结构支持稳定 JSON 序列化和反序列化，字段命名保持英文，中文注释可选。

## TDD

先在 `tests/test_publication_models.py` 写失败测试，覆盖状态/暂停/快照哈希/幂等/unknown 核对门槛/序列化往返；运行 `python -m pytest tests/test_publication_models.py -q` 确认 RED，再做最小实现并运行 GREEN。

## 限制

仅 guard 测试；不写真实书、模型、生产 Runtime、8877；不 commit/push/merge。完成后写 `docs/publication-task1-report.md`，报告命令、通过数、未验证限制和实际文件。
