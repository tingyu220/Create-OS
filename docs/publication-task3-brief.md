# 自动发布任务3：平台适配器协议与番茄 Fake

先读任务1/2报告与复审：`docs/publication-task1-report.md`、`docs/publication-task2-report.md`、`docs/publication-task2-review.md`。仅实现平台边界和 Fake，不接真实番茄。

## 必须实现

- 在 `creative_os/publication_adapter.py` 定义 `PlatformAdapter` 协议：`connect`、`verify_target`、`prepare_chapter`、`fill_chapter`、`publish`、`query_result`、`capture_evidence`。
- 在 `creative_os/tomato_browser_adapter.py` 实现 Fake 番茄适配器，模拟用户已打开作品；不得创建作品、自动登录或保存凭据。
- `verify_target` 必须核对作品标识、书名、章节编号/标题和目标平台能力。
- `fill_chapter` 只接受不可变正式稿快照；正文哈希变化或目标不匹配必须拒绝。
- `publish` 使用 operation_id 幂等；重复调用返回相同结果，不重复发布。
- 模拟验证码/登录失效返回明确暂停原因；模拟丢响应进入 unknown，不能当失败或成功。
- `query_result` 能从 Fake 页面核对平台章节标识和正文哈希；`capture_evidence` 输出结构化页面证据。

## TDD

先写 `tests/test_publication_adapter.py` 的失败测试，覆盖已打开作品核对、章节核对、填充、发布、查询、证据、验证码/登录失效、丢响应和重复发布；运行窄测确认 RED，再最小实现 GREEN。

## 限制

仅 guard/Fake；不打开或操作真实番茄 URL、不接真实账号、不启动生产 Runtime/8877、不 commit/push/merge。完成后写 `docs/publication-task3-report.md`。
