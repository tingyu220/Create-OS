# Knowledge Compiler

Compiler 是 Result 回写 Knowledge 的唯一入口。

## 输入

- Result
- Context
- Domain Package

## 输出

- Entity
- Fact
- Event
- Relationship
- Summary
- Issue

## 原则

- Result 不能绕过 Compiler。
- 冲突和重复必须显式标记。
- Compiler 更新索引、时间线和摘要树。

## Result 编译规则

Writing / Review 结果支持结构化行：

```text
Entity: 名称 | 类型 | 描述
Fact: 事实内容
Relationship: 主体 -> 客体 | 关系
Summary: 摘要内容
```

Compiler 会生成：

- entity
- fact
- relationship
- summary

如果没有结构化行，Compiler 至少生成 summary。

## Research 编译规则

Research Capability 只能输出 Knowledge Draft。

Compiler 将 Knowledge Draft 编译为：

```text
category = external
kind = research_draft
status = draft
```

Research 结果不能直接写入 Active Knowledge。

## M8 验收点

- Result 必须经过 Compiler。
- Compiler 能产出 Entity / Fact / Relationship / Summary。
- Research Draft 编译为 External Draft Knowledge。
- Issue 会进入 CompiledKnowledge.issues。
