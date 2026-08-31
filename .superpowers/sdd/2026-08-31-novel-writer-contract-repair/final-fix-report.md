# 小说 Writer 合同最终修复报告

## 状态

通过。只开放统一只读可视化数据投影层设计，完整 Web UI 继续关闭。

## 修复范围

- `NovelWritingRequest` 同时绑定章节身份、合同身份、权威合同哈希和可复算的章节合同哈希；准入令牌必须匹配合同身份与哈希。
- Writer 最终正文先去除首尾空白再计算哈希；所有生成与一次合同修复均经 `RuntimeRunner`。
- 验收提供方由客户端真实类型与可调用能力识别；Fake 与 Live 模式不能互相冒充。
- CLI 在审查或编译门禁未通过时返回非零退出码；修复重试保持最多一次，Reviewer 标准未放宽。

## Live 门禁

- 受控会话 `57892` 持续轮询至明确 `exit_code=0`。
- 最新脱敏报告：`live`、`openai_compatible`、`compile_candidate_ready`、审查通过、阻断码为空、Canon/State 候选为 1/3。
- Token 审计：prompt 1812、completion 9149、total 10961。未记录正文、Prompt、密钥、Header 或客户端对象。

## 验证与关注点

- 相关回归、架构守卫与最终全量无缓存测试均通过；报告和通用源码审计未发现秘密字段或作品专名硬编码。
- 模型输出具有随机性；若后续 Live 门禁失败，CLI 会以非零退出并关闭投影准入。
