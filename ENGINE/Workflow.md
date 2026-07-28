# Workflow Engine

Workflow 负责阶段流转，不依赖具体领域。

## 默认流程

```text
Idea -> Proposal -> Outline -> Draft -> Review -> Publish
```

## 规则

- 每个阶段有进入条件。
- 每个阶段有退出条件。
- Domain Package 可以扩展默认流程。
- Workflow 只决定阶段，不生成内容。
- Workflow 不知道小说、文章或课程。

## 状态流转

默认只允许按顺序进入下一阶段。

允许：

```text
Idea -> Proposal
Proposal -> Outline
Outline -> Draft
Draft -> Review
Review -> Publish
```

禁止：

```text
Idea -> Draft
Proposal -> Review
Unknown -> Any
```

## Domain 扩展

Domain Package 可以提供自己的阶段列表。

例如 Novel 可以扩展为：

```text
Idea -> Proposal -> World -> Character -> Draft
```

Engine 不修改，只加载不同 phase list。

## State 关系

Workflow 可以基于当前 `ProjectState.current_phase` 生成下一阶段 State。

Workflow 只更新：

- current_phase
- current_task_id
- current_goal

不更新 Knowledge。

## M5 验收点

- Workflow 有默认创作流程。
- Workflow 禁止跳阶段。
- Workflow 能推进 ProjectState。
- Workflow 不依赖小说领域。
- Domain Package 可以扩展阶段。
