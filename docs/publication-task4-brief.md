# 自动发布任务4：自动检查与发布编排 HTTP

先读任务1至3报告/复审和现有 `creative_os/publication_models.py`、`publication_queue.py`、`publication_adapter.py`。只实现编排与 HTTP，不接真实番茄。

## 必须实现

- 在 `creative_os/publication_web.py` 提供编排入口，消费不可变正式稿快照和平台适配器，不直接操作浏览器。
- 自动检查门槛全部通过才允许填充/发布：source_revision连续、章节标题/字数/结构、人物和设定一致、战斗/冲突检查、敏感内容/格式、平台目标匹配、未发布、正文哈希未变化。
- 任一检查失败进入 `failed` 或 `paused`，不得调用 fill/publish。
- 提供全局、单书、单章和当前步骤的安全暂停/立即暂停/继续；普通 Writer 写作命令不受发布队列阻断。
- 发布中断/丢响应进入 `unknown`，继续前强制 query_result；已发布、unknown、版本冲突不得静默重发。
- HTTP GET 只读；控制动作使用明确 POST 和 operation_id 幂等。返回书、章、版本、哈希、步骤、状态和证据。

## TDD

先写 `tests/test_publication_http.py` 失败测试，覆盖全部门槛、失败零发布、暂停/继续、unknown核对、重复命令幂等、GET无写、普通写作兼容；运行 `python -m pytest tests/test_publication_http.py -q` 确认 RED，再最小实现 GREEN。

## 限制

仅 guard/Fake；不访问真实番茄URL、不登录、不接生产 Runtime/8877、不写真实书、不 commit/push/merge。完成后写 `docs/publication-task4-report.md`。
