# 项目状态验收

## 2026-08-20 章节合同与叙事回放基础

基线：`codex/legacy-novel-continuation`，包含既有 3-30 章生产验证能力。本阶段扩展现有 Novel Domain，没有建立第二套 Director 或生产合同模型。

### 已实现

- `narrative_decision.ChapterContract` 继续作为已审批生产合同。
- `ReplayedChapterContract` 作为只读审计投影，允许证据不足的字段为 `unknown`。
- 生产 Artifact 读取器按稳定顺序读取正式正文、Context、Review、Knowledge 和 Task。
- 回放器只映射结构化字段，不从正文关键词推测人物心理或读者认知。
- Reviewer 覆盖五项门禁：人物选择缺失、选择代价缺失、Reader State 未知、近期章节功能重复、结尾变化未知。
- CLI 稳定生成 JSON 和 Markdown 报告，Reviewer 不修改正文、Knowledge 或 Project State。

### 正式回放

项目：`projects/validation_novel`

```text
chapter range: 1-6
chapter_count: 6
issue_count: 12
unknown_field_count: 36
traceable: true
canonical chapter hashes unchanged: true
```

报告：

- `projects/validation_novel/production/reports/narrative_replay_001_006.json`
- `projects/validation_novel/production/reports/narrative_replay_001_006.md`

旧生产 Artifact 能明确证明各章 Scene Goal 和最终 Outcome，因此章节功能与结尾变化可追溯。它们没有显式保存戏剧问题、人物选择、Reader State 和压力曲线，所以相关字段保持 `unknown`；这属于可靠性保护，不是自动补全失败。

### 验收结果

- 完整测试：`235 passed`。
- 第 1-6 章各有且仅有一个回放合同。
- 所有确定性结论均带项目相对路径和证据摘录。
- 五项 Reviewer 门禁均有自动化测试，且只返回 Issue。
- 两种报告可重复生成，内容稳定。
- 回放前后六章正式正文 SHA-256 一致。
- 未新增自动改纲、正文生成、自动修复、数据库、前端或外部模型依赖。

下一阶段门禁：人工抽查回放证据，确认没有错误映射后，再规划回放基础与现有 Narrative Director、Chapter Contract Approval 的正式接入；当前报告不宣称该下一阶段已经完成。
