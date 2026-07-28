# Creative OS V1 执行计划（Execution Plan）

> 目标：在保证架构稳定的前提下，以最小可运行单元（Minimum Capability Unit）逐步构建 Creative OS。

## 当前执行状态

```text
M1 Knowledge  Done
M2 Project    Done
M3 Task       Done
M4 State      Done
M5 Workflow   Done
M6 Context    Done
M7 Retriever  Done
M8 Compiler   Done
M9 Writing    Done
M10 Review    Done
M11 Research  Done
M12 Novel Schema Done
M13 Novel Rule   Done
M14 Novel Template Done
M15 Novel Workflow Done
```

---

# 总体原则

## 原则一：能力优先

不是开发功能，而是开发一种能力。

例如：

```text
错误：人物管理
正确：Knowledge 管理能力
```

## 原则二：每个阶段只能新增一个核心概念

例如：

第一阶段只有 Knowledge。

第二阶段新增 Task。

不要同时开发：

```text
Task + Workflow + Planner
```

否则很难验证设计是否合理。

## 原则三：任何能力必须可独立验证

例如：

Retriever 完成以后，即使整个系统什么都没有，Retriever 也必须能够单独运行。

## 原则四：每个阶段结束必须冻结

完成 M1 后：

```text
Review -> 修正文档 -> 冻结 -> 进入 M2
```

禁止 M1 开发到一半开始 M2。

---

# 第一阶段：Foundation

目标：

建立整个系统的数据模型，不是写 AI，不是写 Agent，而是定义整个系统的数据。

## M1：Knowledge

预计：2~3 天

输出：Knowledge Model

需要完成：

- Knowledge 定义
- Knowledge 分类
- 生命周期
- 更新规则
- 删除规则
- 引用规则

最终输出：

```text
DOMAIN/Knowledge.md
```

完成标准：

Knowledge 可以独立描述整个项目。

## M2：Project

预计：1 天

建立：Project 生命周期。

需要完成：

- Project
- Phase
- Milestone
- Progress

输出：

```text
DOMAIN/Project.md
```

完成标准：

任何创作项目都可以抽象成 Project。

## M3：Task

预计：2 天

建立：Task 模型。

需要完成：

Task 状态：

```text
Pending
Doing
Done
Blocked
```

Task 之间：

- Dependency
- Priority
- Owner

输出：

```text
DOMAIN/Task.md
```

完成标准：

整个系统可以只靠 Task 运行。

## M4：State

预计：1 天

建立：Project State。

明确：

- 什么允许进入 State
- 什么禁止进入 State

输出：

```text
DOMAIN/State.md
```

完成标准：

State 始终保持极小。

完成以后：

Foundation 冻结，以后不能轻易修改。

---

# 第二阶段：Creative Engine

目标：

让 Foundation 真正流动起来。

## M5：Workflow

预计：2 天

建立：状态流转。

例如：

```text
Idea
↓
Proposal
↓
Outline
↓
Draft
↓
Review
↓
Publish
```

完成标准：

Workflow 不依赖小说。

## M6：Context

预计：2 天

建立：Context Builder。

定义：

- Context 组成
- Context 大小
- Context 生命周期

输出：

```text
ENGINE/Context.md
```

## M7：Retriever

预计：3 天

目标：

输入：Task。

输出：最小 Context。

完成标准：

Retriever 绝不能扫描整个 Knowledge。

## M8：Compiler

预计：4 天

建立：Knowledge Compiler。

负责：

```text
Markdown
↓
Fact
↓
Entity
↓
Relationship
↓
Summary
```

完成标准：

Knowledge 开始拥有编译能力。

完成以后：

Creative Engine 冻结。

---

# 第三阶段：Capability

目标：

开始让 AI 真正工作。

注意：

这里只有一个 Capability。

## M9：Writing

预计：3 天

完成：Writing Capability。

输入：Context。

输出：Result。

禁止：

直接访问 Knowledge。

## M10：Review

预计：2 天

建立：Review Capability。

输入：Result。

输出：

- Issue
- Task

## M11：Research

预计：3 天

建立：Research Capability。

负责：

- 联网
- 资料
- 引用
- 知识草稿

禁止：

直接写 Knowledge。

必须：

经过 Compiler。

Capability 完成以后：

AI 第一次真正参与系统。

---

# 第四阶段：Novel Domain

注意：

现在才开始写小说。

不是第一天。

## M12：Novel Schema

建立：

- Character
- World
- Chapter
- Scene
- Timeline
- Relationship

输出：

```text
DOMAINS/Novel/Schema.md
```

## M13：Novel Rule

建立小说规则。

例如：

- 人物
- 世界观
- 章节
- Review 规则
- Workflow 规则

## M14：Novel Template

建立模板。

例如：

- 角色模板
- 章节模板
- 世界观模板

## M15：Novel Workflow

建立小说创作流程。

例如：

```text
Idea
↓
Proposal
↓
人物
↓
世界观
↓
大纲
↓
章节
↓
Scene
↓
正文
↓
Review
```

完成以后：

Creative OS 第一次真正支持小说创作。

当前状态：

```text
Done
```

---

# 第五阶段（暂不开发）

全部预留接口。

包括：

- Article
- Course
- Script
- Research

---

# 当前版本目标（V1）

不是：

- 写小说
- Agent
- 联网

而是证明下面这条流水线成立：

```text
Knowledge
↓
Retriever
↓
Context
↓
Capability
↓
Result
↓
Compiler
↓
Knowledge
```

只要这条流水线稳定，以后任何 Domain 都只是增加一个 Package。

---

# 开发纪律

整个项目禁止违反以下原则。

## 第一

任何 LLM 不能直接操作 Knowledge。

## 第二

任何 Capability 不能自己读取文件。

必须经过 Retriever。

## 第三

任何 Result 必须经过 Compiler，才能更新 Knowledge。

## 第四

Knowledge 永远是真实来源。

Prompt 不是。

聊天不是。

Memory 不是。

---

# 每周节奏建议

建议每周只完成一个 Milestone。

例如：

```text
周一：设计
周二：实现
周三：测试
周四：Review
周五：冻结
```

然后进入下一个 Milestone。

禁止同时开发多个 Milestone。

---

# V1 验收标准

当系统满足下面四点，V1 结束。

- [x] 能够维护一个 Knowledge。
- [x] 能够根据 Task 自动组织 Context。
- [x] Capability 能够只依赖 Context 完成工作。
- [x] Result 能够重新进入 Knowledge 形成闭环。

达到以上四项后，Creative OS V1 正式完成。

验收报告：

```text
ACCEPTANCE_REPORT.md
```
