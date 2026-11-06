# LLM Writer Agent 批量压测报告

## 结论

当前项目已实际压测到：使用 DeepSeek `deepseek-v4-pro` 连续完成第 7-36 章共 30 章批量重写，并全部通过复检后晋级到正式读者稿。

正式读者稿路径：

- `projects/validation_novel/production/final_chapters/`
- `projects/validation_novel/production/drafts/final_draft_polished.md`
- `projects/validation_novel/production/final_chapters_v2/`
- `projects/validation_novel/production/drafts/final_draft_v2.md`

## 压测范围

- 第 4-6 章：小批量真实模型试跑并晋级。
- 第 7-36 章：后续章节批量压测并晋级。
- 全书正式稿：36 章，85587 个中文字符。
- 当前最大连续批量范围：第 7-36 章，30 章。

## 批次数据

| 批次 | 章节 | 耗时 | 模型尝试次数 | 结果 |
|---|---:|---:|---:|---|
| Pilot | 4-6 | 316.0s | 6 | 通过并晋级 |
| Batch 1 | 7-11 | 523.4s | 10 | 通过并晋级 |
| Batch 2 | 12-16 | 467.0s | 8 | 通过并晋级 |
| Batch 3 | 17-21 | 420.9s | 8 | 通过并晋级 |
| Batch 4 | 22-26 | 397.3s | 7 | 通过并晋级 |
| Batch 5 | 27-31 | 423.8s | 9 | 通过并晋级 |
| Batch 6 | 32-36 | 349.4s | 7 | 通过并晋级 |

第 7-36 章累计耗时 2581.8s，约 43 分 2 秒；累计 49 次模型尝试，平均 1.63 次/章。

第 4-36 章累计耗时 2897.8s，约 48 分 18 秒；累计 55 次模型尝试，平均 1.67 次/章。

## 验证结果

- `python -m pytest -q`：68 passed。
- `python -m py_compile creative_os\llm_writer.py creative_os\production.py creative_os\agents.py creative_os\validation_runtime.py scripts\run_llm_writer_pilot.py`：通过。
- 正式章节与全书稿扫描：未命中 `Scene`、`Context`、`Task`、`Compiled Knowledge`、`Knowledge Patch`、`新增事实`、`前几章`、机械时间开头加目的句等已知问题。

## 观察

- API 调用稳定，当前压测中未出现网络或鉴权失败。
- 主要失败来自事实门禁的同义表达误判，不是正文缺失。
- 5 章一批是当前较稳的运行粒度；单批最长约 8 分 43 秒。
- 质量门禁已能拦截时间词模板开头、读者不可见工作流术语、字数缩水和关键事实缺失。

## 当前上限判断

以本次真实运行计，Creative OS 当前已验证的最大稳定状态是：单项目、单模型、5 章批处理粒度下，连续完成 30 章后续正文重写并产出 8 万字级读者稿。

尚未验证的上限：

- 多本小说并行生产。
- 单批 10 章以上请求。
- 10 万字以上长篇完整首稿从零生成。
- token usage 和成本统计。
- API 限流、失败重试、断点续跑的长期稳定性。
