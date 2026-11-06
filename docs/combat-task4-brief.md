# 任务4：确认计划实际进入章节写作

任务3已独立复审通过，现开始执行。新增combat_context_selection.py，最小修改story_context.py、agent_runtime.py及提示组装；新增test_combat_writer_context.py。

接口select_confirmed_combat(confirmed, chapter_number) -> tuple[dict,...]。只消费任务3不可变确认版本里的combat_plans，不读最新候选补冻结数据。冻结保留完整版本证据，组装过滤不适用战斗块，不能追加选中计划却仍通过story.text注入全部计划。普通故事块兼容。

范围空章集合仅全书研究，不自动应用任意章节。适用计划标记未来创作计划非既成事实，包含实际内容/version/hash/source_ref进入真实模型消息及来源详情。运行期间新确认不改变本次输入。必要内容超预算明确失败。采用方案写作要求明确确认；旧项目普通写作兼容；Proposal接受才写工作稿，拒绝不改稿。

主控裁定：仅有未确认combat候选不得阻断旧项目普通写作。明确“采用方案写作”需显式参数要求确认（供任务5接线），不得关键词推断。已确认适用方案按范围入模；候选绝不入模。

TDD测试适用章实际messages含确认内容/不含候选哨兵，不适用章不泄漏计划，全书研究不应用，未来标签，运行中确认变化，两书隔离，预算错误。先python scripts/run_fake_writer_tests.py tests/test_combat_writer_context.py tests/test_agent_proposal.py RED，再GREEN及出口架构测试。不得仅断言DTO或路径。

临时根/Fake/guard，不真实书/模型/生产Runtime/8877/Git写入，不派代理。动态pwsh.exe与apply_patch。报告docs/combat-task4-report.md含实际测试、文件、接口/限制。
