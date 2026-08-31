# Task 1 实施报告

## 状态

完成。

## 实现

- 新增 `build_novel_writer_repair_messages` 纯函数。
- 修复消息复用 `build_novel_writer_messages(request, system_instruction)` 的完整合同用户消息。
- 修复提示要求完整重写、逐字写入缺失信息，并保持可发布正文输出边界。
- 拒绝空初稿、空缺失集合及空白缺失项。
- 新增无作品硬编码、完整合同保留和输入边界测试。

## 验证

- `pytest -q tests/test_novel_writer_repair_prompt.py tests/test_novel_writer_prompt.py`：9 passed。
- `python -m compileall -q creative_os/domains/novel_writer_repair_prompt.py tests/test_novel_writer_repair_prompt.py`：通过。
- `git diff --check`：通过。

## 关注点

修复消息包含完整原合同用户消息，确保完整重写不会丢失剧情、边界或禁止项；未引入客户端、环境配置或具体作品依赖。

## 审查修复轮 1

- 修复：测试直接调用 `build_novel_writer_messages(writing_request, system_instruction)`，断言其完整用户消息作为连续子串存在于修复消息中。
- 命令：`pytest -q tests/test_novel_writer_repair_prompt.py tests/test_novel_writer_prompt.py`
- 输出：`9 passed in 0.15s`
