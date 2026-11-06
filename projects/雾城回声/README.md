# 验证小说项目：雾城回声

该目录是 Creative OS V1 Production Validation 的第一部真实验证小说项目。

当前验收目标：

- M1：项目立项、状态、元数据、版本基线、生产日志可持久化。
- M2：六类 Agent 契约固定，不出现万能 Agent。
- M3：进入 Project Proposal、Story Bible、Character Bible、Plot Outline、前十章 Scene Plan。

运行时项目文件由 `ProjectWorkspace` 写入：

```text
project.json
state.json
brief.json
metadata.json
baseline.json
production_log.jsonl
```
