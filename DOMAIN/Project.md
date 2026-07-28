# Project Model

Project 表示一个长期创作项目的生命周期，不等同于文件夹。

它负责组织目标、阶段、里程碑和进度，不负责保存长期创作知识。

## 核心字段

- id
- name
- domain
- phase
- milestones
- progress

## 生命周期

```text
Idea -> Proposal -> Planning -> Drafting -> Review -> Publish -> Archived
```

允许阶段流转：

```text
Idea     -> Proposal / Archived
Proposal -> Planning / Idea / Archived
Planning -> Drafting / Proposal / Archived
Drafting -> Review / Planning / Archived
Review   -> Publish / Drafting / Archived
Publish  -> Archived
Archived -> Idea
```

禁止：

- Idea 直接进入 Drafting。
- 未经过 Review 直接 Publish。
- Project 阶段由 Capability 私自修改。

## Milestone

Milestone 是 Project 的阶段性验收点。

核心字段：

- id
- title
- status

状态：

```text
pending
active
done
blocked
```

## Progress

Progress 不手动存储，由 Milestone 自动计算。

计算规则：

```text
已完成 Milestone 数 / 总 Milestone 数
```

没有 Milestone 时，Progress 为 0。

## 与 Knowledge 的关系

- Project 组织创作目标和进度。
- Knowledge 保存项目事实和内容。
- Project 不直接承载正文、角色、世界观等长期知识。

## 边界

Project 允许保存：

- 项目名称
- 项目领域
- 当前阶段
- Milestone 列表
- 派生进度

Project 禁止保存：

- 正文
- 人物资料
- 世界观
- 章节内容
- 长期摘要
- 外部资料原文

这些内容必须进入 Knowledge。

## M2 验收点

- Project 有明确生命周期。
- Project 阶段流转受规则约束。
- Project 支持 Milestone。
- Progress 由 Milestone 派生。
- Project 不保存 Knowledge 内容。
- 小说、文章、课程都能抽象为 Project。
