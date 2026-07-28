# Creative OS V1 后续开发计划书（第一版）

> 项目阶段：V1 已完成架构开发与验收
>
> 当前目标：快速进入真实生产环境验证，同时保持 V2 持续开发。

---

# 一、当前项目状态

## 已完成

V1 已完成以下内容：

- Foundation（基础层）
- Creative Engine（创作引擎）
- Domain（Novel）
- Capability
- Context
- Workflow
- 基础运行流程

目前已经能够完成：

- Agent 工作流
- Knowledge 管理
- Context 构建
- 基础小说创作流程

V1 整体架构已通过内部验收。

## 当前问题

虽然 V1 架构已经稳定，但是目前仍然属于：

```text
Engineering Validation（工程验证）
```

而不是：

```text
Production Ready（生产可用）
```

目前存在的问题主要有：

- 没有经过长期真实项目验证
- Knowledge 规模增长后的表现未知
- Retriever 准确率没有经过大量数据验证
- Workflow 没有经历长时间运行
- Review 规则覆盖不足
- 缺少真实小说项目压力测试

因此：

V1 目前适合作为测试平台，还不能作为真正长期创作工具。

---

# 二、总体开发策略

经过评估，不采用：

```text
V1 停止开发 -> 验证 30 天 -> 再开发 V2
```

原因：

开发周期过长，大量时间会被等待浪费。

因此采用：

```text
双轨开发（Dual Track Development）
```

一边验证 V1，一边开发 V2，互不影响。

---

# 三、Git 开发策略

目标远程仓库：

```text
git@github.com:tingyu220/Create-OS.git
```

建立三个长期分支：

```text
main
│
├── release/v1
│
└── develop/v2
```

## main

作用：

稳定版本。

只保存已经完成验收的版本。

例如：

```text
v1.0.0
v1.0.1
v1.1.0
```

禁止直接开发。

## release/v1

作用：

生产验证。

允许：

- Bug 修复
- 性能优化
- 压力测试
- 日志完善
- Review 规则完善
- Retriever 优化
- Knowledge 稳定性优化

禁止：

新增 V2 功能。

## develop/v2

作用：

新功能开发。

例如：

- 新 Workflow
- 新 Capability
- 新 Domain
- Web 支持
- 自动规划
- 新 Research 能力

允许大胆尝试。

不影响 V1 稳定性。

---

# 四、V1.5（Production Validation）

V1 后续不再增加大型功能。

目标只有一个：

```text
验证 Creative OS 是否真正能够长期运行。
```

## 第一部分：压力测试

目标：

模拟真实项目，不是模拟接口。

主要验证：

### Knowledge

测试：

- 大量人物
- 大量章节
- 大量 Fact
- 大量 Relationship

观察：

- 检索速度
- 更新速度
- Compiler 效率

### Retriever

验证：

Context 是否越来越大。

是否能够准确找到真正需要的数据，而不是越来越依赖全文搜索。

### Workflow

模拟：

数百个 Task。

验证 Workflow 是否出现：

- 死循环
- 重复 Task
- 状态错误
- Task 阻塞

### Review

验证长期创作以后是否还能发现：

- 人设冲突
- 时间线冲突
- 世界观冲突
- 重复剧情

### Compiler

验证 Knowledge 持续增长以后，Compiler 是否还能稳定更新：

- Fact
- Entity
- Timeline
- Summary

## 第二部分：自动化模拟

不采用 30 天人工验证。

改为自动模拟。

例如：

```text
100 章
↓
1000 个 Task
↓
10000 条 Knowledge
↓
连续 Workflow
↓
连续 Review
↓
连续 Compiler
```

利用自动脚本快速完成真实项目模拟，缩短验证周期。

## 第三部分：Benchmark

建立官方 Benchmark。

记录：

```text
Knowledge 数量
Context 长度
Retriever 命中率
Task 数量
Workflow 耗时
Review 耗时
Compiler 耗时
```

以后每个版本必须进行 Benchmark，比较是否退化。

## 第四部分：Issue 管理

所有问题统一进入 GitHub Issues。

分类：

- Architecture
- Performance
- Retriever
- Workflow
- Compiler
- Review
- Knowledge

禁止用聊天记录管理 Bug，全部 Issue 化。

---

# 五、V2 开发策略

V2 不等待 V1，同步进行。

但是：

不能修改 Foundation。

优先开发：

## Domain 扩展能力

例如：

- Article
- Script
- Course
- Research

预留未来扩展能力。

## Capability 扩展

例如：

- Planning
- Learning
- Research
- Summarize
- Style

逐步完善 Creative 能力。

## Research Provider

建立 Knowledge Provider 接口。

支持：

- Web
- API
- PDF
- MCP
- Obsidian

以后 Knowledge 可以持续更新。

## Creative Engine 优化

例如：

- 更智能 Task 生成
- 更智能 Workflow
- 更精准 Retriever
- 更高质量 Review

---

# 六、开发原则

整个项目遵循能力开发，而不是功能开发。

每一个 Milestone 必须只完成一个能力。

例如：

```text
本周：只优化 Retriever。
下周：只优化 Compiler。
```

避免多个核心模块同时修改。

---

# 七、版本规划

## 当前

```text
V1.0
```

完成。

进入维护阶段。

## 下一阶段

```text
V1.1
```

目标：

真正支持小说长期创作。

重点：

稳定。

不是新增功能。

## 后续

```text
V2.0
```

目标：

Creative OS 能力升级。

例如：

- 多领域支持
- Research
- 更多 Capability
- 自动规划
- Web 支持

---

# 八、当前优先级

## P0（最高）

- 发布 V1.0
- 建立 GitHub
- 建立开发规范
- 建立 Issue 规范
- 建立 Benchmark

## P1

- 自动压力测试
- Retriever 验证
- Workflow 验证
- Compiler 验证

## P2

- V2 开发
- 新 Capability
- 新 Provider
- 新 Domain

---

# 九、当前阶段目标

未来阶段不追求功能越来越多，而追求系统越来越稳定。

真正的目标不是：

```text
AI 能够写小说。
```

而是：

```text
Creative OS 能够持续稳定地管理一个长期创作项目，并能够随着 Knowledge 不断增长，保持一致性、可维护性和可扩展性。
```

---

# 十、阶段验收标准

V1.1 完成标准：

- [ ] V1 完成 GitHub 发布。
- [ ] 完成自动压力测试体系。
- [ ] 完成 Benchmark 体系。
- [ ] 完成 Issue 管理体系。
- [ ] 完成真实小说项目模拟。
- [ ] Retriever 在大规模 Knowledge 下保持稳定。
- [ ] Compiler 能够持续维护 Knowledge。
- [ ] Workflow 能够长期运行无结构性问题。

达到以上目标后，V1 正式进入生产可用（Production Ready）阶段，并开始为 V2 提供稳定的基础平台。
