# Review Capability

Review 负责一致性检查，不只是校对。

## 输入

- Result
- Context

## 输出

- Issue
- Fix Task

Result 要求：

```text
kind = review
issues = list[Issue]
follow_up_tasks = list[Task]
```

## 检查方向

- 设定冲突
- 时间线冲突
- 人物状态冲突
- 规则违反
- 缺失必要上下文

## M10 验收点

- 输入 Result + Context 的 Review 场景由 Context 表达。
- 输出 Issue。
- 输出可追踪 Fix Task。
- Fix Task 必须依赖当前 Review Task。
