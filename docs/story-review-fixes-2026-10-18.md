# 前期架构首版独立复审修复记录

状态：四项问题已复现并修复，等待总控再次独立复审；不宣告总目标验收完成。

## 逐项证据

### P1：被拒绝请求提前恢复目标项目

原路径是 POST → select_project(writable=True) → 构造可写 Runtime → 全项目恢复 → 解析/校验请求体。新增反例在 book-b 存在 queued 章节任务时，发送跨项目/会话请求、错误参数及错误命令；修复前均可观察到文件变化。

现在 POST 先只读绑定，Agent 使用 validate_submit/validate_retry、Command 使用 validate_request 完成无副作用预检，随后才激活项目。registry 的可写装配使用 recover=False，本身也不恢复任何任务；领域操作仍在执行锁内复核，包括动态 CAS 和幂等结果。即使发生校验后的并发冲突，也不会恢复无关任务。

反例断言：请求返回 400/422，文件内容、集合、mtime 全部不变，且没有发生 writable=True 装配。覆盖跨项目/会话、错误 instruction、预算、Command 目标与参数（包括不可散列的 action）、错误重试会话、缺少章节 session。

### P1：章节只读恢复投影缺失

Runtime 对启动时已存在的中断任务记录集合；story 和 chapter 的 conversation 及 job 查询均输出只读恢复投影。queued/thinking 显示 failed + recovery_required + retryable；saving 显示需核对且不可重试。查询不持久化这些投影，也不发起模型调用。

显式 retry 先只读核对 project/chapter/session、可重试性、最新任务与执行参数，进入项目锁后再次核对，仅把指定中断任务标记为已接管并生成后继任务。原 frozen story_context 原样沿用，不读取后来确认的版本。其他章节的 queued 任务保持原文件和 mtime；后续仍可显式恢复。

反例/正向：queued、thinking、saving 三类状态；GET conversation 和 GET job 不落盘；HTTP retry 只接管目标章节；原冻结 text/version/hash 实际进入重试模型消息。Writer JS 断言显示重试按钮且不自动提交，saving 不显示重试。

### P2：Feedback Query 初始化文件

FeedbackStore 增加 initialize=False；list 在文件不存在时返回空。WriterLesson 查询及反馈证据预检均使用无初始化读取。默认写入构造保持兼容。

反例分别在 feedback.jsonl 缺失和已存在时比较全部文件内容、集合及 mtime，均保持不变。

### P2：创建 marker 写入窗口无法恢复

创建命令在 mkdir 后、允许创建 marker 的父目录前，先把目录的 device/inode 身份原子保存到父根创建意图。marker 缺失时，只有匹配该检查点的原目录、且内部仅包含已知 marker 目录/临时文件才可续办。陌生内容、被替换目录（含空目录）以及无检查点的非空目录均拒绝认领。

反例在 atomic_json(creation.json) 已创建 .creative_os、尚未落 marker 时注入异常。相同 key 重放成功；四类不满足归属证据的情况均安全拒绝。测试对替换目录先 rename 为备份，不删除原证据。

## 执行与隔离

先经 `scripts/run_fake_writer_tests.py tests/test_fake_validation_guard.py` 独立验证出口保护，再运行复现及修复测试。所有 Python 测试均在默认禁用真实客户端构建、urllib 和非 loopback socket 的进程中；浏览器使用同一保护且只放行 loopback 页面请求。未访问/重启 8877，未构造生产 Runtime 或写真实小说，未提交/推送/合并。

初次新增 12 个反例全部失败，确认复现原问题。后续补充请求参数、目录替换和 HTTP 恢复隔离，专项扩为 19 项。验证日志与 SHA256 清单位于 `.backup/story-review-fixes/`；原首版日志和隔离事件记录保留。

验证结果：组合 Python 回归 314 项通过；随后补充空目录替换及不可散列 action 的最新专项 19 项通过；JS 44 项通过；受保护 Chromium 主闭环 8 次 Fake 执行通过。`git diff --check` 通过。

## 限制与待处理

- 缺少目录身份检查点的旧非空半成品无法自动证明归属，继续安全拒绝；不能为了恢复而认领它。
- 显式旧 CLI/服务装配的默认 recover=True 行为保留兼容；Web registry 明确使用 recover=False，只有指定任务的合法 retry 执行接管。
- 早期默认工厂绑定事件的远端接收/计费仍未知；本次成功验证不反向证明当时没有请求。
- 等待总控独立复审，真实创作质量及生产加载仍不在本轮范围。
