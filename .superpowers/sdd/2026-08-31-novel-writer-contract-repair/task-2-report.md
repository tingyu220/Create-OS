# Task 2 实施报告

## 状态

完成，待由主任务集成。

## 实现

- Writer 首稿与可选修复稿均通过 `RuntimeRunner.execute` 执行。
- `max_contract_repairs` 默认 1，且仅允许 0 或 1。
- 仅当首稿缺少精确 `essential_information` 时执行一次完整重写；第二稿仍缺失时直接交由 Reviewer 阻断。
- 遥测聚合全部尝试的耗时与 Token；任一尝试缺少 Token 时该聚合字段为 `None`；哈希仅对应最终正文。
- 未新增原始正文、提示词、客户端或环境信息的落盘字段。

## TDD 与验证

- 红测：`pytest -q tests/test_llm_novel_writer.py tests/test_novel_writer_validation.py`，5 项按预期失败（缺少修复调用、遥测聚合与配置限制）。
- 相关与架构测试：57 passed。
- 全量：`PYTHONDONTWRITEBYTECODE=1 pytest -q -p no:cacheprovider`，1266 passed，8 skipped。
- `git diff --check`：通过。

## 关注点

- 修复仅针对 Writer 可机械判定的必要信息缺失，不复制或放松 Reviewer 的其他规则。

## 修复轮 1：配置类型收紧

- 根因：`max_contract_repairs in (0, 1)` 使用 Python 相等性，接受 `True`、`False`、`0.0` 与 `1.0`。
- 测试：先将以上四个值加入非法配置参数化测试；红测为 4 failed、2 passed。
- 修复：仅增加 `type(max_contract_repairs) is int` 类型门槛，并保留原有 0/1 值限制。
- 验证：`pytest -q tests/test_llm_novel_writer.py tests/test_novel_writer_validation.py tests/test_novel_domain_end_to_end.py`，28 passed；`git diff --check` 通过。
