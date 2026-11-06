# 自动发布任务3复审

结论：**通过（无剩余 P0/P1/P2）**

本次为针对上一版复审三个发现的定向复审。实现已补齐正式稿/平台章节核对、能力检查和准备阶段章节号检查，未发现新的阻断问题。

复审范围：

- `docs/publication-task3-brief.md`
- `docs/publication-task3-report.md`
- `docs/publication-task1-report.md`
- `docs/publication-task2-report.md`
- `docs/publication-task2-review.md`
- `creative_os/publication_adapter.py`
- `creative_os/tomato_browser_adapter.py`
- `tests/test_publication_adapter.py`

## 已通过项

- `PlatformAdapter` 已声明 `connect`、`verify_target`、`prepare_chapter`、`fill_chapter`、`publish`、`query_result`、`capture_evidence` 七个协议方法。
- Fake 只接收已有页面对象；不创建作品、不自动登录、不保存凭据，也未访问真实番茄。
- 目标核对包含平台、作品 ID、书名，以及已存在页面章节的编号/标题一致性；缺少填充或发布能力时会拒绝。
- `ChapterSnapshot` 为不可变正式稿，`fill_chapter` 会重新计算正文 SHA-256，并拒绝同一 `operation_id` 的正文哈希变化。
- 已发布和 `unknown` 状态的重复 `publish` 返回原结果，不重复执行发布；验证码与登录失效返回明确 `paused` 原因；丢响应返回 `unknown`。
- `capture_evidence` 返回平台、作品、操作号及章节结果的结构化字典。

## 定向修复核对

- **正式稿哈希与平台章节号：通过。** `query_result` 现在校验页面章节是否存在、`platform_chapter_id` 是否为目标章节标识、`content_sha256` 是否等于保存的 `ChapterSnapshot` 哈希；缺失或不一致均返回 `unknown` 和明确 `mismatch`，`capture_evidence` 同时标记 `evidence_available: false`。
- **目标平台能力：通过。** `verify_target` 现在要求 `fill_chapter`、`publish`、`query_result`、`capture_evidence` 四项能力全部存在。
- **准备/验证章节号：通过。** `verify_target` 在提供快照时比较 `snapshot.chapter_number` 与 `target.chapter_number`；`prepare_chapter` 因此会拒绝正式稿与目标章节号不一致的调用。

## 验证

只读运行窄测：

```text
python -m pytest tests/test_publication_adapter.py -q
7 passed in 0.06s
```

未修改实现与测试，未访问真实番茄、未登录真实账号、未启动生产 Runtime/8877。
