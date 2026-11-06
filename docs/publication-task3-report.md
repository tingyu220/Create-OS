# 自动发布任务3报告

状态：已完成

实现文件：
- `creative_os/publication_adapter.py`
- `creative_os/tomato_browser_adapter.py`
- `tests/test_publication_adapter.py`

实现内容：
- 定义 `PlatformAdapter` 协议，统一连接、目标核对、章节准备/填充、发布、结果查询和证据采集接口。
- 提供仅内存的 `FakeTomatoPage` 与 `TomatoBrowserAdapter`，要求使用用户已打开的作品；禁止自动登录、创建作品和保存凭据。
- 目标核对覆盖平台能力、作品标识、书名、章节编号与标题；正式稿只接受不可变 `ChapterSnapshot`，并校验正文哈希与目标一致。
- 发布按 `operation_id` 幂等；验证码、登录失效返回明确暂停原因；丢响应进入 `unknown`；查询可核对平台章节标识与正文哈希；证据为结构化字典。

TDD 验证：

```text
python -m pytest tests/test_publication_adapter.py -q
5 passed
```

先写失败测试运行时因适配器文件不存在而 RED；完成最小实现后 GREEN。

限制：仅 Fake/guard，未访问真实番茄 URL、未登录真实账号、未接生产 Runtime 或 8877；未 commit、push 或 merge。

## 复审修复

针对复审 P1/P2 已补充：
- `query_result` 同时核对 Fake 页面平台章节标识与正式稿快照 `content_sha256`；缺章、错章或正文篡改均返回 `unknown` 和期望/实际值。
- `capture_evidence` 对核对失败标记 `evidence_available: false`，不可作为已发布证据。
- `verify_target` 要求查询与证据能力，并在传入快照时校验章节编号。
- 新增页面篡改、能力缺失和准备阶段错章测试。

复审修复后验证：

```text
python -m pytest tests/test_publication_adapter.py tests/test_publication_queue.py tests/test_publication_models.py -q
18 passed
```
