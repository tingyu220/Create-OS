# 自动发布任务4复审

结论：**通过（无 P0/P1/P2）**。实现仍限于 Fake/guard，未访问真实番茄、未登录、未接 Runtime/8877。

复审范围：`docs/publication-task4-brief.md`、`docs/publication-task4-report.md`、任务1—3报告/复审、`creative_os/publication_web.py`、`tests/test_publication_http.py`，并运行任务1—4窄回归。

## 已通过项

- 编排入口消费 `ChapterSnapshot`、`PublicationQueue` 和适配器；Fake 边界未直接操作浏览器。
- 失败门槛会把任务置为 `failed`，`run()` 对 failed/paused/published 不调用 fill/publish；全门槛 false 的零发布测试通过。
- unknown 通过队列检查点阻止直接 `resume()`；Fake 丢响应场景经 `query_result` 核对后可完成；发布成功返回证据、书/章/版本/哈希/步骤/状态/检查结果。
- GET 路径本身只读；POST 使用显式 action；相同 operation_id 的重复 run 在已发布后返回既有状态，不重复调用 Fake 发布。
- 全局、书、章暂停以及 safe/immediate 基础路径已有实现；未引入 Writer 写作模块依赖，现有 Writer 窄测未受该模块导入影响。
- 默认缺少门槛证据时现在 fail-closed；重复提交已存在 operation_id 时只读返回，不再覆盖终态。
- prepare/fill 异常现在会落到带步骤名的 failed checkpoint；全局/单书 clear_pause 接口和 continue 路由已加入，并只恢复对应 `pause_reason` 的任务。

## 发现的问题

### 已修复：自动检查默认放行

`_checks()` 现将十二项初始化为 `False`，只有显式提供完整的 true checks 才能进入发布；新增测试已验证缺少证据时失败且零填充/发布。后续仍需接入真实 guard 数据源，但本轮的默认放行 P1 已关闭。

### 已修复：重复提交篡改终态

`submit()` 现在在队列复用 operation_id 时立即只读返回；新增测试验证已发布任务重复提交仍为 `published`。本轮 P1 已关闭。

### 已修复：clear_pause/continue 的范围恢复

- 任务要求覆盖“当前步骤”暂停；HTTP `pause` 仅解析 global/book/operation_id 和 mode，没有步骤字段或步骤级状态控制（`publication_web.py:91-113`, `156`）。当前实现最多是章节级暂停，不能表达/返回独立步骤暂停。
`clear_pause(scope="global")` 现在清除全局标志，并仅将 `pause_reason == "global_pause"` 的暂停任务恢复为 `READY_TO_PUBLISH`；单书范围同理只匹配 `book_pause`。步骤暂停、unknown、version_conflict 不会被误恢复。新增范围测试已覆盖全局与单书路径。

### 已修复：步骤 checkpoint 与异常 checkpoint

运行过程记录 prepare/fill/publishing/published 步骤；prepare/fill 异常会生成对应 failed checkpoint，发布异常进入 publishing/unknown checkpoint。定向测试验证 `current_step` 和 checkpoint 均可返回。

### 已修复：控制 POST 与只读查询

GET 未知 operation_id 返回结构化 404；控制 POST 使用显式 action，带 operation_id 的控制结果缓存后重复请求返回同一结果；普通 Writer 路径未被发布队列阻断。

### P2：GET 查询未知 operation_id 未按 HTTP 边界返回结构化错误

`do_GET()` 直接调用 `state(op)`（`publication_web.py:146-148`），不存在的 operation_id 会抛出 `KeyError`，由 `BaseHTTPRequestHandler` 产生连接级错误而不是 JSON 错误响应。控制面应返回稳定的 4xx 和错误证据，避免只读查询反而打断客户端。

### P2：异常后的状态/检查点仍不完整

`publish()` 异常现在会进入带 `publishing` checkpoint 的 `unknown`；但 `prepare_chapter()`/`fill_chapter()` 异常仅标记 `failed` 并没有 checkpoint/current_step，无法返回失败发生步骤。应为准备/填充异常记录步骤 checkpoint 或明确的失败证据。

## 验证

```text
python -m pytest tests/test_publication_models.py tests/test_publication_queue.py tests/test_publication_adapter.py tests/test_publication_http.py -q
29 passed in 1.71s
```

另对重复提交、默认检查和错误目标做只读定向探针：两项原 P1 已验证修复；错误目标会失败且未填充。未修改实现与测试，未接真实番茄。

状态：**已完成**。本轮未发现剩余 P0/P1/P2。
