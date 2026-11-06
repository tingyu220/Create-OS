# 战斗专家任务4实施报告

状态：**已完成**任务4实现与受影响 Fake 回归；主控独立复审待处理。

## DONE / CURRENT / TODO

- DONE：确认版本完整冻结、按章节选择战斗计划、真实章节消息过滤、计划来源快照、显式采用计划的确认预检、预算失败及 Proposal 回归。
- CURRENT：交主控独立复审；最新扩大验证结果见下方。
- TODO：任务5接线内部显式参数，以及后续 UI / 完整验收。本任务没有新增 UI、HTTP DTO 或生产入口。

## 文件和职责

- 新增 `creative_os/combat_context_selection.py`：`select_confirmed_combat(confirmed, chapter_number) -> tuple[dict, ...]`，只选择传入不可变确认版本 `content.combat_plans` 的适用计划，返回独立副本；没有文件读取、候选读取或 Runtime 依赖。
- 修改 `creative_os/story_context.py`：冻结完整 confirmed 记录（包含原文、结构化 content 和全部方案证据），附项目与来源身份；`chapter_story_context` 从普通故事块中剔除所有关联战斗块，再独立编译本章计划。预算按实际必需内容检查，不裁剪计划、不因异章计划占用预算。
- 最小修改 `creative_os/agent_runtime.py`：预检及锁内受理传递章节和显式采用参数；组装时注入普通设定及选中计划，分别登记实际片段与消息偏移；复用原 RuntimeRunner、CapturingModelAdapter 和 Proposal 路径。
- 新增 `tests/test_combat_writer_context.py`：通过真实原会话存储、任务3服务端结果 ID 采用和作者确认建立领域数据，Fake 仅替代外部模型；断言实际 analyze / act messages 及真实来源查询，不以 DTO / 路径代替模型输入验收。

## 接口与语义

```text
select_confirmed_combat(confirmed, chapter_number) -> tuple[dict, ...]
chapter_story_context(confirmed, chapter_number) -> (ordinary_text, selected_plans)
WriterAgentRuntime.submit(..., require_confirmed_combat=False)
WriterAgentRuntime.validate_submit(..., require_confirmed_combat=False)
```

- 范围精确匹配 `scope.chapter_numbers`；空数组只表示全书研究，不自动应用任何章节。选择器返回原关联字段及 block / text / version / hash / source_ref。版本与 hash 绑定完整确认内容，不伪装成过滤后子集的 hash。
- 原 `job.story_context.text` 保留完整版本证据，但对具有结构化 content 的任务，模型组装不再使用这份全量原文。普通块按原故事渲染兼容；所有 combat_plans 关联块先从普通文本移除，只有本章选中项独立进入模型，避免“追加选中项但仍注入全部 story.text”。
- 选中项由原领域渲染器强制标记“未来创作计划，不是已发生事实”；作者修订后仍保留原证据只关联原专家建议的说明。消息中包含实际计划内容、确认 version / hash 和 `story-confirmed:<project>:<version>:<hash>#<block_key>` 来源。
- 来源详情标签为 `已确认战斗计划`，保留实际 `content_snapshot`、消息位置、片段 hash、确认 story_hash、version、source_ref，以及 combat_plan 中的结果 ID、原结果 hash、原建议块 hash、scope、source_hashes、evidence_refs 和修订标记。读取旧来源详情不读取当前候选或正文。
- 完整确认内容在 submit 的项目锁内冻结；执行、范围选择和来源捕获只消费该快照。排队后作者再次确认不会改变当次输入。
- 必需普通设定与选中计划合计超过 48,000 字符时抛出 `required_story_context_budget_exceeded`；最终已有总消息预算超过 100,000 字符时亦明确失败。没有截断必需内容或降级为成功；超限不调用 Fake 模型、不写工作稿。
- 主控裁定：不能仅因旧项目存在未确认战斗候选就阻断普通写作；未确认候选仍绝不注入。显式 `require_confirmed_combat=True` 用于“采用确认方案”操作：无确认版报 `story_confirmation_required`；确认版中无本章适用计划报 `combat_plan_confirmation_required`。参数只接受 bool，限定章节，不按指令关键词猜测。任务5需显式接线该参数，本任务没有新增 HTTP 或 UI 字段。
- 新项目 story_mode 原有确认要求保留；旧项目没有确认故事或只有候选时，普通写作继续兼容。显式确认计划写作通过后仍只生成 Proposal；拒绝不改稿，作者接受才写工作稿。

## 实际 RED / GREEN

全部测试通过 `scripts/run_fake_writer_tests.py` 启用 `fake_validation_guard`，项目及持久文件仅在 pytest 临时根；每次命令执行前动态解析当前安装的 `pwsh.exe`。

1. 首次指定组合：`python scripts/run_fake_writer_tests.py tests/test_combat_writer_context.py tests/test_agent_proposal.py` → **10 failed, 23 passed in 5.16s**。测试夹具没有显式将来源任务 mode 设为 analyze，任务3正确拒绝；修正夹具，没有修改生产校验。
2. 同组合第二次 → **9 failed, 24 passed in 6.36s**。除功能缺失外，发现 Fake 分析 action 写成故事协议 finish_turn，以及拒绝提案未填写必需原因；修正这两处测试输入。
3. 有效功能 RED，同组合 → **8 failed, 25 passed in 7.00s**。实际消息包含异章 / 全书研究哨兵，冻结快照缺 content，缺计划独立来源，确认限制与选择接口尚缺；失败不是测试收集或外部依赖问题。
4. 最小实现后同组合 → **33 passed in 8.48s**。
5. 第一轮扩大受影响组合 → **1 failed, 185 passed in 66.31s**。唯一失败为任务3原有兼容用例：只有候选时 freeze 应返回 None。本轮同时收到主控兼容裁定，移除过宽阻断，保留该原测试。
6. 显式采用契约的补充 RED，同指定组合 → **2 failed, 32 passed in 8.24s**。失败为普通旧项目仍被错误阻断，以及显式 `require_confirmed_combat` 参数尚不存在。
7. 按裁定最小修复后同组合 → **34 passed in 6.70s**。
8. 第二轮扩大受影响组合 → **266 passed, 1 skipped in 86.81s**。覆盖故事、战斗任务1–3、HTTP、恢复、来源与两个出口架构测试。
9. 补充异章计划预算不占用本章必需预算、analyze / act 最终总消息超限后，同指定组合 → **37 passed in 11.06s**。
10. 最终扩大组合 → **269 passed, 1 skipped in 90.35s**，退出码0。包含全部14个任务4参数化用例、任务3原有兼容用例及两个出口架构测试；适用计划的 act 路径还显式传入 `require_confirmed_combat=True`，验证新接线契约的成功分支。

最终扩大命令：

```text
python scripts/run_fake_writer_tests.py tests/test_combat_writer_context.py tests/test_combat_story_candidate.py tests/test_story_architecture.py tests/test_story_agent.py tests/test_story_http.py tests/test_story_review_fixes.py tests/test_combat_agent.py tests/test_combat_context.py tests/test_agent_conversation.py tests/test_agent_conversation_http.py tests/test_agent_proposal.py tests/test_writer_context_sources.py tests/test_agent_runtime.py tests/test_writer_production_exit_architecture.py tests/test_writer_transparent_delegate_architecture.py
```

`rg` 对本任务新增选择器、修改的 story_context 和新增测试进行末尾空白扫描，无匹配。共享 agent_runtime 已含此前任务大量修改，本任务只修改上述明确位置，没有重构、回退或清理共享改动。

## 限制与范围

- 旧持久任务若只有 story_context.text、没有结构化 content，只能兼容回放原普通故事文本，选择器不推断战斗元数据、不读取最新候选补历史冻结证据。新受理任务全部保留完整 confirmed 结构；旧纯故事恢复回归保留。
- 本任务没有扩大为真实模型文学质量或模型遵循未来标签的证明；Fake 验证实际发送的输入、来源和写稿权限边界。
- 跳过项沿用 Windows 符号链接权限测试，不声称已通过。
- 未操作真实书、真实模型、生产 Runtime 或 8877；未 commit / push / merge、删除、清理共享改动或派代理。验证仅限已授权的受影响 guard 组合，没有运行超出临时根范围的不明全库脚本。

## 修复轮1（独立审查 P2）

审查报告 `docs/combat-task4-review.md` 的 P1（章节分析研究读取候选）经复核撤回：研究语义允许读取候选，本轮未收紧任务1/2权限。仅修复两项 P2：

- `retry_of + require_confirmed_combat=True`：预检现在读取原任务的 `story_context`，只接受原冻结版本中存在当前章节适用的确认计划；无快照、异章计划、旧纯文本快照均明确失败，不能从最新确认补历史。有效原冻结计划重试仍复用原快照，作者随后确认的新版本不进入重试消息。
- 章节分析协议追加后的输入预算：协议完整追加后再次检查 `MAX_INPUT_CHARS`，超限抛出 `required_story_context_budget_exceeded`，不进入工具循环、不调用模型、不产生完成结果。

### 修复轮1 TDD / 定向验证

1. 新增定向 RED：`python scripts/run_fake_writer_tests.py tests/test_combat_writer_context.py -k "explicit_retry or protocol_appended"` → **7 failed, 1 passed, 14 deselected**。失败分别复现显式重试绕过确认和协议追加后 completed；有效冻结计划重试基线已通过。
2. 实现第一处 P2 后同筛选 → **7 passed, 16 deselected**。
3. 实现第二处 P2 后同筛选 → **9 passed, 14 deselected**。
4. 必要受影响 guard 回归：`python scripts/run_fake_writer_tests.py tests/test_combat_writer_context.py tests/test_agent_conversation.py tests/test_combat_agent.py tests/test_story_review_fixes.py tests/test_agent_proposal.py` → **110 passed in 23.00s**，退出码0。

修复轮1未运行真实书、真实模型、生产 Runtime、8877 或 Git；未修改已撤回的研究候选权限语义。<br>
