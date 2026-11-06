# 任务1：证据输入与专家结果契约

工作目录 D:/田雨/Creative OS。设计和计划已获作者批准。本次只实现任务1，不推进其他任务，不派子代理。

新增 creative_os/combat_model.py、creative_os/combat_context.py、tests/test_combat_context.py。必要时最小适配creative_context.py、writer_context_sources.py，先理解现有实现，不重构无关代码。

## 公共契约

- CombatScope(chapter_numbers: tuple[int,...], purpose: str)
- CombatRequest(project_id, session_id, job_id, instruction, scope, confirmed_story, sources)
- CombatResult(result_id, project_id, job_id, verdict, reply, alternatives, foreshadowing, evidence_refs, unknowns, scope)
- verdict严格为combat/setup/noncombat/insufficient；正文自由。使用dataclass/TypedDict，不引入框架。
- build_combat_context(root, project_id, scope, *, task_id, session_id, instruction) -> CombatRequest
- read_combat_source(snapshot, source_id) -> dict：仅访问已冻结来源，不重新读取实时文件。
- sources含source_id/kind/chapter_number/version或hash/text/完整或截断范围。来源身份绑定本书；目标工作稿与正式稿分开，优先工作稿，邻章不能冒充目标章。正式设定、已写正文、工作稿、旧规划分kind。缺失和未读不得假装已读。
- scope空章节集合为全书研究建议，不自动应用所有章。不要因此无界读取全部小说。
- 每来源12000字符、累计源内容48000字符；必要正文或设定超预算明确要求缩小范围，不能静默截断。来源路径遵循现有项目身份/根约束；无持久副作用。

## TDD与验收

先写test_target_draft_precedes_formal_and_adjacent、test_missing_target_is_not_inferred、test_cross_book_source_rejected、test_query_does_not_write（文件/目录/mtime）、test_required_context_over_budget。经python scripts/run_fake_writer_tests.py tests/test_combat_context.py记录实际RED（不是环境错误），最小实现后GREEN；补必要边界测试。先检查guard确保只用临时根/Fake。

保留所有共享改动；不commit/push/merge、不真实模型、不真实书写入、不生产Runtime、不服务8877操作。Windows使用动态解析pwsh.exe；编辑用apply_patch。中文注释与记录。不得启动额外子代理或审计，主控安排独立审查。

报告写docs/combat-task1-report.md，含文件、实际RED/GREEN命令与结果、自审、限制及接口偏差。回复DONE/DONE_WITH_CONCERNS/BLOCKED/NEEDS_CONTEXT和报告路径。有架构歧义及时向主控报告，不自行扩展。
