# 文明升阶

这是《文明升阶》的单项目数据根目录。请按下面的权威边界使用文件，避免把运行产物误当成正文。

## 权威内容位置

- 正式正文（已发布章节）：`production/final_chapters/chapter_001.md` 至当前最新章节
- 当前工作稿（Agent/作者编辑中的草稿）：`.creative_os/writer/drafts/chapter_<编号>.jsonl`
- Agent 分析决策：`.creative_os/agent/decisions/`
- 章节版本与编辑记录：`.creative_os/writer/`

正式正文和工作稿必须分开查看：工作稿未经过作者确认和发布流程，不会自动覆盖正式正文。

## 系统数据位置

- `production/contracts/`：生产合同与章节元数据
- `production/reports/`：质量和生产报告
- `production/runs/`：生产运行状态
- `.creative_os/projection/`：只读投影快照
- `.creative_os/runtime/`：事件、任务、反馈和诊断日志
- `.creative_os/memory/`：项目权威、合同和长期记忆
- `.creative_os/contexts/`、`.creative_os/reviews/`、`.creative_os/state/`：章节上下文、审阅和状态证据
- `.creative_os/publication_migration/`：出版迁移与版本材料，不能当正式正文

## 清理规则

- 不删除 `production/final_chapters/`、`.creative_os/writer/` 或任何带来源引用的运行/审阅数据。
- 临时锁文件可在停止服务后重新生成；清理备份位于 `D:\田雨\Creative OS-backups\文明升阶-cleanup-20260927`。
- 需要归档或删除历史材料时，先确认其不再被代码、测试或恢复流程引用。
