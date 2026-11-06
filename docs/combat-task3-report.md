# 战斗专家任务3实施报告

状态：**已完成**任务3实现与受影响回归；主控独立审查待处理。

## DONE / CURRENT / TODO

- DONE：服务端结果 ID 采用、现有故事聚合中的结构化来源关联、候选合并、作者修订/删块、显式作者确认、旧记录与旧幂等回执兼容。
- CURRENT：最终受影响回归已通过，交主控独立审查。
- TODO：任务4章节范围过滤与实际写作消费、后续 UI 及完整验收。本任务没有实现这些边界之外的内容。

## 文件和职责

- 新增 `creative_os/combat_story_candidate.py`：从原 `AgentConversationStore` 只读加载持久任务，校验结果与冻结来源身份；构造未来建议内容块及结构化关联；在原故事聚合中原子提交候选。
- 最小修改 `creative_os/story_architecture_store.py`：内容支持可选 `combat_plans`，参与原候选内容 hash、完整性检查和确认快照；编辑保留来源关联、标注作者修订，删块同步删除关联；提取共用原子候选追加；确认限制为作者。
- 最小修改 `creative_os/story_architecture_command.py`：新增 `adopt_combat_candidate`，仅接受结果 ID 与预期候选版本；作者编辑/确认沿用现有命令边界。
- 新增 `tests/test_combat_story_candidate.py`：现有真实领域存储上的临时根测试。任务夹具使用完整 `AgentJob` / `CombatResult` / 冻结来源结构，经原会话存储 JSON 持久化，无模型请求。

## 接口与语义

```text
stage_combat_candidate(store, result, *, expected_revision, actor, operation_id) -> dict
```

- `result` 明确为结果 ID 字符串。主控已认可此形状及命令名称；不支持客户端提交完整结果，不增加不必要的多形态兼容。
- 命令 `adopt_combat_candidate` 的 target 沿用 `{project_id, scope: story, session_id}`；payload 严格仅 `{result_id, expected_revision}`。成功回执沿用 `story-candidate:<revision>:<hash>`。
- 返回现有故事 candidate dict，包括 revision/hash/content/text/actor/created_at；采用不确认，不修改小说正文或工作稿。
- 结果从原会话任务的 `combat_results` 重读。校验项目集合身份及选定根、结果 ID 唯一性、任务 project_id/mode/job_id、冻结请求 project_id/session_id/scope、证据 source_id/归属/usage/hash。没有构造 Runtime，读取不触发恢复写。
- 重试结果必须绑定本次任务 job_id；冻结证据可绑定原任务，但该任务必须处于同项目、同会话的真实 retry_of 祖先链。不能把旧任务身份冒充新结果。
- 块 key 为 `combat-plan:<result_id>`；块仍严格只有 key/title/text。同结果重新采用只替换目标块，其他块、其他方案来源关联和未决问题保留。
- `content.combat_plans` 的每项字段：`block_key/result_id/project_id/scope/evidence_refs/source_hashes/result_hash/original_block_hash/author_revised/evidence_basis`。scope 保留 `{chapter_numbers, purpose}`，空 chapter_numbers 仍表示全书研究，没有自动适用任何章节的语义。
- `source_hashes` 是 evidence_ref 到原冻结正文 hash 的映射；`result_hash` 绑定服务器原始完整结果；`original_block_hash` 绑定最初建议块。`evidence_basis` 固定为 `expert_original`，证据只关联原专家建议。
- 机器元数据存放于结构化内容，不能由可编辑正文注入。作者改标题/正文后仍保留来源关联，hash 改变、author_revised 标记为 true；领域渲染明确说明修订文字不由原证据背书。即使作者删去可编辑正文中的未来标签，渲染仍补充未来计划语义。
- 模型之后修订同块时，渲染也会依据 original_block_hash 标注“修订建议”及不背书说明；不会将机器修订误标为作者修订。
- 候选内容、关联和 operation receipt 在原 architecture.json 中一次原子提交；CAS 及幂等仍由原项目锁与原聚合承担。确认绑定当前 revision/hash/expected_confirmed_version，保存不可变完整关联快照。
- 作者命令与底层 confirm 仅接受现有应用角色标记 `作者`；聊天认可不调用 confirm，未确认候选不成为正式来源。未引入新的账号认证系统。
- 旧记录没有 combat_plans 时按空关联处理，保留原 content/hash/text 形状；普通无战斗关联的新修订也不强行添加空字段，避免破坏旧 operation 指纹。删除最后一个已关联块后显式保留 `combat_plans: []`。
- 没有候选时以现有 confirmed 为基线；两者皆无时只创建建议候选，并新增“其他正式设定尚缺，需作者补充并明确确认”的未决问题。

## 实际 RED / GREEN

测试全部通过 `scripts/run_fake_writer_tests.py` 启用 fake_validation_guard；所有项目和持久化文件均位于 pytest 临时根。每次终端执行前动态解析已安装 pwsh.exe，无写死版本目录。

1. 要求的首轮 RED：`python scripts/run_fake_writer_tests.py tests/test_combat_story_candidate.py tests/test_story_architecture.py` → **14 failed, 16 passed in 1.69s**。失败为候选模块尚不存在及命令未允许，不是依赖收集失败。
2. 最小实现后同命令 → **30 passed in 1.20s**。
3. 旧聚合操作回执兼容补测 RED：`python scripts/run_fake_writer_tests.py tests/test_combat_story_candidate.py -k legacy_operation` → **1 failed, 14 deselected in 0.68s**。为普通旧内容强加空 combat_plans 导致原操作指纹不一致，报 idempotency_conflict。改成可选元数据后保留旧指纹。
4. 核心故事/战斗/HTTP/恢复组合 → **110 passed, 1 skipped in 17.79s**。
5. 补充同方案替换、原子保存失败不提交、元数据完整性及确认快照测试后的扩大组合 → **1 failed, 252 passed, 1 skipped in 72.09s**。唯一失败是新增测试夹具在内存 tuple 上调用 append；按实际 JSON 数组持久化形状修正为新列表，无生产代码修订。
6. 最终扩大组合 → **253 passed, 1 skipped in 70.88s**，退出码0。任务3新增用例、旧操作回执补测及其余受影响测试全部通过。

最终扩大命令：

```text
python scripts/run_fake_writer_tests.py tests/test_combat_story_candidate.py tests/test_story_architecture.py tests/test_combat_agent.py tests/test_combat_context.py tests/test_story_agent.py tests/test_story_http.py tests/test_story_review_fixes.py tests/test_agent_conversation.py tests/test_agent_conversation_http.py tests/test_agent_proposal.py tests/test_writer_context_sources.py tests/test_agent_runtime.py tests/test_writer_production_exit_architecture.py tests/test_writer_transparent_delegate_architecture.py
```

该组合覆盖任务3全部新增用例、故事领域、战斗任务1/2、实际 Fake 主/专家工具消息、HTTP、恢复、章节 Proposal 与透明出口架构。跳过项沿用任务1的 Windows 符号链接权限测试，不声称通过。

对四个代码/测试文件执行末尾空白扫描，无匹配；另执行限定文件的 git diff --check 为退出码0，但这些文件当前为共享未跟踪文件，故不把该命令作为未跟踪文件内容已检查的证据。

## Ruling / 范围与限制

- Ruling：依主控批准，内部 result 参数固定为 ID，命令为 adopt_combat_candidate；不新增结果仓库或 Runtime 取数依赖。
- Ruling：本任务以现有故事命令服务为接入边界，不注册新 HTTP 路由/DTO，不修改 UI；后续任务接线应调用此命令，不能接受客户端完整结果。
- Ruling：严格保持任务3范围，只验证受影响组合，不运行可能超出临时项目范围的无关全库测试。TDD/完成前验证技能用于失败证据和最终检查，不扩大任务到真实项目。
- 章节范围选择、冻结完整 combat_plans 并过滤实际模型消息由任务4处理；现有章节故事文本装配没有在本任务改写，不将任务3声称为端到端写作消费已完成。
- 本任务只核验任务2服务器持久结果与冻结来源；专家建议的文学质量不在 Fake 测试证明范围。
- 未操作真实书、真实模型、生产 Runtime、8877；没有 commit/push/merge、删除、清理共享改动或派子代理。

## 独立审查 P2 修复轮1（恢复后完成，待独立复审）

- 状态：**已完成**本轮定向修复与必要回归；任务3放行仍待主控独立复审。
- 恢复检查发现前一轮中断前已有未报告改动：`creative_os/combat_story_candidate.py` 已在构造关联时按首次出现顺序去重，`tests/test_combat_story_candidate.py` 已补真实专家链路用例。本轮保留这些改动，没有回退或清理其他共享文件；仅为验证回归测试暂时恢复缺陷行，取得 RED 后立即还原去重。
- 修复文件：`creative_os/combat_story_candidate.py` 仅对关联的 `evidence_refs` 使用 `list(dict.fromkeys(...))`。`_load_result` 仍逐项检查原结果引用，原始持久结果不修改，`result_hash` 和操作指纹仍绑定完整原结果。
- 测试文件：`tests/test_combat_story_candidate.py` 的 `test_real_expert_duplicate_refs_adopt_in_first_seen_order_without_changing_result` 使用真实 `run_combat_expert`，Fake 只提供工具动作，读取真实冻结来源；经原 `AgentConversationStore` 写入并重读后采用。覆盖两来源交错重复时的首次顺序、来源 hash、完整原结果 hash 未改变、持久结果未修改及重启后的幂等重放。本轮另补重复非法来源的拒绝参数，确保去重不会放宽来源校验。
- 实际 RED：暂时恢复直接采用原引用数组，执行 `python scripts/run_fake_writer_tests.py tests/test_combat_story_candidate.py -k real_expert_duplicate_refs` → **1 failed, 19 deselected in 0.84s**，退出码1；失败在真实专家结果持久化后的 stage，明确报 `combat_plans_invalid`。
- 实际 GREEN：还原关联去重，执行 `python scripts/run_fake_writer_tests.py tests/test_combat_story_candidate.py tests/test_story_architecture.py` → **36 passed in 1.19s**，退出码0。覆盖本轮真实生产/消费边界、非法来源拒绝及故事聚合必要回归，没有重跑253组合。
- 全部测试仍经 `fake_validation_guard`，项目仅位于 pytest 临时根；每次终端执行前动态解析 `pwsh.exe`。未操作真实书、真实模型、生产 Runtime、8877 或 Git；未派代理。没有改动任务2生产契约、故事存储/命令或任务4范围。
