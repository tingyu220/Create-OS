# 任务3：建议进入现有候选与确认机制

任务2规范及质量独立审查已通过，主控批准立即执行。工作目录D:/田雨/Creative OS。

新增combat_story_candidate.py；最小修改story_architecture_store.py、story_architecture_command.py；新增test_combat_story_candidate.py。接口stage_combat_candidate(store, result, *, expected_revision, actor, operation_id) -> dict。消费现有job持久化的CombatResult；客户端只给结果ID，不信任完整结果。必要接入以现有命令服务为边界，不创建第二存储。

战斗块key为combat-plan:<result_id>，保留key/title/text。故事修订新增可选combat_plans关联（旧记录缺省空），含block_key/result_id/project_id/scope/evidence_refs和来源hash，同一原子聚合、纳入候选hash和确认快照。正文明确未来创作计划非已发生事实；机器元数据不可隐藏在可编辑文本中。

TDD覆盖：合并保留所有非目标块与未决问题；CAS旧revision拒绝；重复operation幂等；跨项目/伪结果身份拒绝；作者编辑hash变化并标作者修订；确认绑定版本与hash；聊天认可不能确认；未确认不作正式来源。先运行python scripts/run_fake_writer_tests.py tests/test_combat_story_candidate.py tests/test_story_architecture.py确认RED，再最小实现GREEN。

旧项目无candidate以已有confirmed为基线；两者皆无只创建建议候选，明确缺其他正式设定。作者改文保留来源关联但不能宣称新文字由原证据证明，删除块同步去关联。确认权限只属作者；采用不等于确认，不改小说正文。scope空表示全书研究，不自动适用章节。所有ID和来源从服务端任务数据校验，注意重试结果本次job身份。

所有测试guard临时根/Fake，不真实书/模型/生产Runtime/8877/commit/push/merge。保留共享改动，动态解析pwsh.exe，apply_patch编辑，不派代理。报告docs/combat-task3-report.md含实际RED/GREEN/文件/限制；接口歧义及时报告。
