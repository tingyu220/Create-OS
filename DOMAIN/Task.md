# Task Model

Task 是 Creative OS 的执行单元。

系统由 Task 推进，不由聊天记录推进。

## 状态

```text
Pending -> Doing -> Done
Pending -> Blocked
Doing   -> Blocked
Blocked -> Pending
```

禁止：

- Pending 直接 Done。
- Done 再次变更状态。
- Capability 私自创建不受管理的任务链。

## 核心字段

- id
- title
- kind
- status
- priority
- owner
- domain
- goal
- tags
- dependencies

## Priority

优先级用于选择下一个可执行任务。

```text
HIGH
NORMAL
LOW
```

排序规则：

```text
priority desc -> id asc
```

## Owner

Owner 表示任务负责人或执行主体。

允许为空。

示例：

```text
system
human
writing
review
research
```

Owner 只描述责任归属，不代表 Capability 可以绕过 Context 或 Compiler。

## Dependency

Task 可以依赖其他 Task。

规则：

- 依赖目标必须存在。
- 只有所有依赖 Task 都是 Done，当前 Task 才 runnable。
- Blocked 和 Doing 不能被视为完成。
- TaskStore 负责判断 runnable，不由 Capability 自己判断。

## TaskStore

TaskStore 是 M3 的最小任务容器。

职责：

- 保存 Task。
- 校验依赖存在。
- 更新 Task。
- 选择 runnable Task。

不负责：

- Workflow 阶段流转。
- Planner 智能调度。
- Capability 执行。

## 原则

- 系统由 Task 推进，不由聊天记录推进。
- Planner 本质是 Task Scheduler。
- Capability 只处理当前 Task，不自行扩展任务范围。

## M3 验收点

- Task 有明确状态机。
- Task 支持 Dependency。
- Task 支持 Priority。
- Task 支持 Owner。
- TaskStore 能选择 runnable Task。
- 系统可以只靠 Task 推进基本执行顺序。
