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
# Novel Domain V1 当前状态

小说正文进度不再代表领域能力完成度。《文明升阶》仅作为真实回归样本。

历史校准基线：Phase E 已完成并通过离线 Gate；第7–26章已完成。第27章正文不存在，后续生产仍须基于 POV 输入事实和 Chapter Contract。

已完成：

- Novel Domain 能力目录与统一 `NovelDomainService` 入口；
- Scene 的叙事目的、必要故事信息、情绪变化和戏剧闭合契约；
- Chapter Boundary 与碎章、对话截断、戏剧单元未闭合准入；
- 统一 Novel Reviewer；
- 通过稿到 Canon/State 候选的 Novel Compiler；
- Draft、Issue、Repair、Final 因果链的 Lesson Candidate；
- 规划—准入—写作—审查—编译的单章组合闭环。

当前验证边界：

- 所有 Canon/State 结果仍是候选，继续由现有审批服务决定是否写入；
- 旧 Narrative Contract 可读取，新 Novel Domain 运行必须满足增强 Scene 语义；
- 《文明升阶》的碎章、对话截断和戏剧单元未闭合问题已匿名化为回归夹具。

## 真实 Writer 独立验收（Task 6）

- Fake 验收：已通过。证据为 `projects/novel_domain_validation/production/reports/fake_writer_validation.json`，阶段为 `compile_candidate_ready`，审查通过。
- 通用源码专名审计：已通过。`creative_os/` 未检出既有作品或独立验证样本的专名硬编码。
- Live 验收：`live_validation=blocked_missing_configuration`。当前未检测到 `CREATIVE_OS_LLM_API_KEY`、`CREATIVE_OS_LLM_MODEL`，且项目根不存在 `.env`；未执行真实模型调用，也未生成真实验收报告。
- 可视化数据投影层：准入保持关闭，须待 Live 验收达到 `compile_candidate_ready` 且审查通过后才可开始设计。

下一阶段：

- 配置真实模型所需环境后，运行 Live 独立验收并核验脱敏报告；
- 仅在 Live 验收通过后，开始可视化数据投影层设计。
