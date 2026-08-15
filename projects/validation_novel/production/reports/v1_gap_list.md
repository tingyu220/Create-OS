# V1 Gap List

## P0 Gaps

- Knowledge Store 通用持久化：当前生产项目通过 JSON 产物目录补足，需进入正式 Store。
- Writer Capability 模型接入：当前为生产验证运行模块生成草稿，需要接入真实 LLM Writer。
- Cross-Chapter Knowledge Dedup：需要正式去重，避免长期项目 Fact 重复。
- Conflict Detection：需要自动检测人物、时间线、世界观冲突。

## P1 Gaps

- Prompt Version Management：需要将 Writer/Reviewer/Compiler Prompt 版本入库。
- Context Source Trace UI：目前有 JSON 快照，缺少用户可读追踪界面。
- Repair Task Executor：当前已生成 Repair Task，缺少自动局部修复执行器。
- Benchmark CLI：当前由测试和报告统计，缺少独立命令。

## Accepted For V1.1

上述缺口不阻断 V1.1 验收，因为本阶段目标是验证完整生产链路；增强性能力进入 V2 候选或 V1.x 修复。
