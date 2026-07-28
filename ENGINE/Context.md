# Context Builder

Context 是一次 Capability 调用的运行时数据包。

## 默认组成

- User Input
- Current Task
- Project State
- Retrieved Knowledge
- Domain Rules

## 生命周期

Context 只在本次调用中存在，不作为长期知识保存。

每次 build 都会生成新的运行时 Context。

## 边界

- Capability 只能读取 Context。
- Capability 不能自己搜索文件。
- Capability 不能直接修改 State 或 Knowledge。
- Context 必须匹配当前 Task。
- Context 必须匹配当前 State。
- Context 必须匹配当前 Domain Package。

## 大小控制

Context Builder 必须控制：

- 最大 Knowledge 条目数
- 最大字符估算量

默认：

```text
max_items = 8
max_chars = 12000
```

超过限制时拒绝构建 Context。

## 校验规则

构建 Context 时必须检查：

- `task.domain == state.active_domain`
- `task.domain == domain.name`
- `task.id == state.current_task_id`

## M6 验收点

- Context 包含 User Input、Task、State、Retrieved Knowledge、Domain Rules。
- Context 有生命周期字段。
- Context 有大小估算。
- Context Builder 能限制 Knowledge 条数。
- Context Builder 能拒绝跨领域或跨任务数据。
