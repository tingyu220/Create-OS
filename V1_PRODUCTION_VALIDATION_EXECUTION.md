# Creative OS V1 Production Validation 执行清单

## 当前目标

使用一部中短篇小说《雾城回声》验证 Creative OS V1 是否能稳定完成小说生产闭环。

## 已落地

- M1 Project Brief / Project State / Novel Metadata / Version Baseline / Production Log 数据模型。
- M1 ProjectWorkspace 持久化与恢复。
- M2 Director / Planner / Architect / Writer / Reviewer / Compiler 六类 Agent 契约。
- M3 Project Proposal / Story Bible / Character Bible / Plot Outline / 36 章大纲 / 前 10 章 Scene Plan。
- M3 Design Review，通过正式开写第一章条件。
- M4 第一章三个 Scene 的 Task、Context、Draft、Review、Compiled Knowledge 和运行记录。
- M5 第 2、3 章连续生产。
- M5 第 3 章最小连续性 Review。
- M5 第 4、5 章连续生产。
- M5 第 5 章人物与世界观一致性 Review。
- M5 第 6-10 章连续生产。
- M5 第 10 章剧情方向与长上下文稳定性 Review。
- M6 第 11-36 章全书初稿生产。
- M6 每 5 章项目级 Review。
- M6 初稿完成 Review。
- M7 Structure / Character / World / Timeline / Text 五层 Review。
- M7 Issue Report / Repair Task / Regression Review / Final Compile。
- M8 Production Report / Benchmark Report / V1 Gap List / V2 Backlog / V1.1 Acceptance Report。
- Chapter Composition Repair：保留原始 Scene 产物，新增读者版最终章节。
- Final Chapter Writer V2：新增读者版最终稿，去除重复转场、模板句和明显 AI 工作流痕迹。
- Final Chapter Writer V2.1：第 4 章后改为基于 SceneSpec 合成连续读者正文，并同步覆盖常用最终稿路径。
- LLM Writer Agent Pilot：新增 OpenAI-compatible 模型调用边界、章节重写输入包、质量门禁和第 4-6 章试跑脚本；无 API Key 时可用 Fake Client 完成离线回归测试。
- LLM Writer Agent Pilot 实跑：使用 DeepSeek `deepseek-v4-pro` 重写第 4-6 章，产物通过读者禁词、章节开头、字数和关键事实门禁。
- LLM Writer Agent Pilot 晋级：第 4-6 章 DeepSeek 重写稿已同步覆盖 `production/final_chapters/`、`production/final_chapters_v2/`、`production/drafts/final_draft_polished.md` 和 `production/drafts/final_draft_v2.md`；旧默认稿备份在 `production/backups/canonical_before_llm_writer_pilot_promotion/`。
- LLM Writer Agent 批量压测：第 7-36 章已分 6 个批次完成 DeepSeek `deepseek-v4-pro` 重写、复检和晋级，正式读者稿全书 36 章共 85587 个中文字符。

## 当前里程碑状态

- M1 项目立项：Done
- M2 Agent 体系：Done
- M3 前期设计：Done
- M4 第一章闭环：Done
- M5 前十章连续创作：Done
- M6 初稿完成：Done
- M7 全书 Review：Done
- M8 V1.1 验收：Done

## 下一步

1. V1.1 Production Ready 已完成。
2. 后续进入 V2 候选需求评审或 V1.x 缺口修复。
3. 原始生产版本保留在 `production/drafts/full_draft.md` 和各章 `drafts/`。
4. 修复后的读者版章节位于 `production/final_chapters/`。
5. 修复后的全书读者版位于 `production/drafts/final_draft_polished.md`。
6. V2 读者最终章节位于 `production/final_chapters_v2/`。
7. V2 全书最终稿位于 `production/drafts/final_draft_v2.md`。
8. LLM Writer Agent 试跑、批量重写、复检和晋级记录位于 `production/llm_writer_pilot/`。
9. 将 `.env.example` 复制为 `.env`，配置 `CREATIVE_OS_LLM_BASE_URL`、`CREATIVE_OS_LLM_API_KEY`、`CREATIVE_OS_LLM_MODEL` 后，可运行 `python scripts\run_llm_writer_pilot.py --project-root projects\validation_novel\production --chapters 7-36` 生成真实模型重写稿。
10. 批量压测报告位于 `production/reports/llm_writer_stress_report.md`。

## 当前 V1 缺口

- Knowledge Store 仍是内存模型，生产项目依赖 JSON 产物目录作为持久化补充。
- Writer 产物已有 LLM Pilot 接入边界；真实第 4-36 章已完成模型重写和晋级。
- Review 已有逐 Scene 规则检查，但还不是强 Schema 校验器。
- Compiler 已能输出 Summary、Timeline、Fact、Draft，但缺少跨章去重和冲突检测。
- 当前生产验证阶段无未完成项。

## 执行约束

- 正文必须由 Scene Task 驱动。
- Capability 不直接读取 Knowledge。
- Result 必须经过 Review 和 Compiler。
- 任何人工干预必须写入 Production Log。
- 影响当前小说完成的问题进入 V1，增强性需求进入 V2 Backlog。
