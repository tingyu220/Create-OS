# V2 Candidate Requirements

## Candidates

- LLM Writer Capability：接入真实模型、质量门禁和重试策略。
- Persistent Knowledge Store：正式知识库存储、索引、版本迁移。
- Conflict Detector：人物状态、时间线、世界观和伏笔冲突检测。
- Repair Task Runner：基于 Issue 的局部修复，不整本重写。
- Benchmark CLI：固定项目、固定问题、固定指标的版本回归工具。
- Review Dashboard：展示章节状态、Knowledge Health、Issue 和 Repair 进度。
- Prompt/Agent Version Registry：Prompt、Agent、Domain Schema 的版本管理。

## Not In V1.1

- 多用户协作。
- 多 Domain 同时生产。
- Web 发布和营销文案。
- 完全无人监督创作。

## LLM Writer 性能与工程化

- P0：新书项目创建器，项目总文件夹使用小说书名。
- P0：批量重写断点续跑，避免已通过章节重复请求模型。
- P0：记录每章耗时、尝试次数、token usage 和失败原因。
- P1：局部修复模式，降低整章重写比例。
- P1：结构化事实校验，输出 evidence 便于审查。

## Web 工作台准入条件

- 新书项目使用 `projects/<书名>/`。
- 正式发布目录使用 `releases/<书名>/`。
- 每章任务状态已落盘到 `runs/status/`。
- 控制台任务面板能展示通过、失败、耗时和失败原因。
- Web 可视化工作台在以上条件稳定后再进入实现。
