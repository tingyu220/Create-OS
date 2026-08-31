# Deferred Minor 清理报告

## 范围

关闭 Task 1 与 Task 3 最终审查遗留的两项 Minor，不改变消息协议或组合入口行为。

## 改动

- 删除 `creative_os/domains/novel_writer_prompt.py` 中未使用的局部变量 `info`。
- 在 `tests/test_novel_domain_composition.py` 增加环境工厂契约测试，验证自定义 `env_file` 原样透传，并验证 `OpenAICompatibleClient.from_env` 只调用一次且返回客户端被 Writer 采用。

## 验证

- 定向回归：`pytest -q tests/test_novel_domain_composition.py tests/test_novel_writer_prompt.py` → `10 passed`。
- Task 6 基线：提交 `2a0eea7`，独立审查 clean，`1254 passed/8 skipped`；live 状态为 `blocked_missing_configuration`。
- `git diff --check`：通过。

## 状态

两项 deferred minor 已关闭。未推送远程仓库。
