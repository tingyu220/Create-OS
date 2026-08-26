# Novel Production Roadmap

## P0

- 新书项目创建器：使用书名创建 `projects/<书名>/`。
- 批量重写断点续跑：失败后只跑未通过章节。
- 耗时与 token 统计：每章记录 elapsed_seconds、attempts、usage。

## P1

- 局部修复模式：针对开头模板、术语泄露、重复句做小范围修复。
- 事实校验结构化升级：输出 supported/evidence，减少人工判断成本。
- 控制台任务面板：展示通过、失败、耗时和失败原因。

## Web 工作台准入条件

只有满足以下条件后才进入 Web 可视化工作台：

- 新书项目使用 `projects/<书名>/`。
- 正式发布目录使用 `releases/<书名>/`。
- 每章任务状态已落盘到 `runs/status/`。
- 控制台任务面板能展示通过、失败、耗时和失败原因。

## Reports

- Stress Report: `projects/validation_novel/production/reports/llm_writer_stress_report.md`
- V2 Backlog: `projects/validation_novel/production/reports/v2_backlog.md`
# Phase E 状态

- E-A Reader Engagement Foundation：已完成并通过离线 Gate。
- E-B 逐章生产编排：已完成离线 Gate，并与场景、技术、POV 门禁整合。
- E-C 真实生产校准：第7–26章已完成；第7–23章为 Scene/Technology 历史合同，第24–26章为完整多视角实验合同。
- 当前生产边界：第27章正文不存在；必须先审批 POV 输入事实、系统候选和完整 Chapter Contract。
- 下一阶段：验证 POVStrategyPlanner 在真实第26章状态上给出可解释建议，再逐章生产第27章。
