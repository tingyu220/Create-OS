# Task 3 配置修正与 Live 独立验收报告

## 状态

通过。仅开放统一只读可视化数据投影层设计；完整 Web UI 准入保持关闭。

## 配置与 Fake

- 已仅修正主项目 `.env` 的 `CREATIVE_OS_LLM_BASE_URL` 值，并以 `OpenAICompatibleClient.from_env()` 的 `base_url` 断言验证；未复制、展示或提交环境文件。
- Fake 验收退出成功，报告为 `compile_candidate_ready`，且审查通过。

## Live

- 修复轮 1 的静态追踪确认：CLI 仅在 `run_independent_writer_validation()` 正常返回后才原子写入报告；模型运行异常会由 Writer 映射为 `novel_writer_model_failed`，CLI 再以 `writer_validation_failed` 和退出码 1 结束。因此上轮“进程结束、报告不变”是异常路径与未捕获 stderr/退出码共同造成的不可复核状态，不是原子写入故障。
- 本轮只追加一次真实 Live CLI。控制器在 30 秒观察窗内确认进程仍在运行、无可分类 stderr；随后确认进程结束，报告于 `2026-08-31T09:40:58Z` 刷新。该工具会话在分离时未回传终态退出码，不能伪造为外部捕获值；但根据 CLI 成功写入后的唯一控制流，退出状态为 0。未保存 stderr 原文、正文、Prompt、密钥或 Header。
- 新报告元数据：模型 `deepseek-v4-pro`；阶段 `compile_candidate_ready`；审查通过；阻断码为空；Canon/State 候选数为 1/3。
- Token 统计为 prompt 533、completion 2094、total 2627；报告只含允许的标量审计字段。

## 审计与关注点

- 通用源码专名审计通过。
- 脱敏关键字扫描唯一命中 `prompt_tokens` 指标名；其为固定 Token 统计字段，不是原始 Prompt 或秘密，报告没有 `api_key`、`authorization`、`bearer`、`raw_response` 或 `messages` 字段。
- 已取得可落盘的 `compile_candidate_ready` 且审查通过的 Live 证据，下一阶段仅可设计统一只读投影层；完整 Web UI 继续关闭。

## 修复轮验证

- `pytest -q tests/test_validate_novel_real_writer_script.py tests/test_llm_novel_writer.py tests/test_novel_writer_validation.py`：27 passed。
- Live 报告脱敏扫描只命中固定 `prompt_tokens` 指标名；通用源码专名扫描无命中。
