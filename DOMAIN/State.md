# State Model

State 只保存当前工作状态，必须保持小。

State 是仪表盘，不是知识库。

## 允许保存

- current_phase
- current_task_id
- current_goal
- active_domain
- risks

其中 `risks` 最多 10 条。

## 禁止保存

- 人物资料
- 世界观
- 正文
- 长期事实
- 大段摘要
- 外部资料原文
- 任意未定义字段

## 原则

- State 只描述现在。
- State 不保存历史知识。
- State 不保存创作正文。
- State 更新必须显式生成新状态。
- Capability 不能直接修改 State。

## 更新规则

允许通过 `advance()` 更新：

- current_phase
- current_task_id
- current_goal
- risks

不允许通过 State 更新：

- active_domain
- Knowledge 内容
- Project Milestone
- Task 依赖

## M4 验收点

- State 只允许当前工作字段。
- State 拒绝长期内容字段。
- State 风险列表保持小。
- State 可以输出 compact 运行视图。
- State 更新是显式的，不原地修改旧状态。
