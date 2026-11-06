# 战斗专家任务2实施报告

状态：任务2实现已完成；主控独立复审待处理。

## DONE / CURRENT / TODO

- DONE：专家只读工具循环；故事/章节主 Agent 按需委派；显式请求；每步实际输入/来源/输出捕获；持久冻结重试；严格出口 manifest v4 与架构负例。
- CURRENT：交主控独立审查。
- TODO：任务3—6（候选采用、确认方案消费、UI 与完整验收）未实施。

## 文件及职责

- 新增 `creative_os/combat_agent.py`：`run_combat_expert(request, *, execute_step, read_source) -> CombatResult`。只有 `read_source` / `finish`；不持有 Runtime、客户端或写接口。
- 新增 `creative_os/chapter_agent_tools.py`：主章节分析工具循环、冻结请求、专家桥接、冻结章节分析装配及回放。预算失败留在原 job 内，委派时明确拒绝。
- 最小接入 `creative_os/agent_runtime.py`：AgentJob 增加专家选择/快照/结果/初始消息/分析装配字段；复用既有 `_execute_story_step` 单步入口；章节 Act 保持原 RuntimeRunner→Proposal 路径。
- `creative_os/story_architecture_agent.py`：加入 consult_combat / finish；保留原 read/propose/finish_turn；故事主输入与只读工具结果均使用本轮冻结状态。
- `creative_os/agent_intent.py`、`creative_os/web_workspace.py`、`creative_os/story_web.py`：实际 DTO 与两条 HTTP 意图入口接受可选 requested_expert，缺省 null；故事来源端点可精确读取专家步骤 ID。
- `tests/test_combat_agent.py`：临时书根、Fake 模型的行为与实际消息验证。
- `tests/test_writer_production_exit_architecture.py`、`tests/writer_architecture_checks.py`、新增 `tests/assets/writer_production_exits_v4.json`：原出口透明适配器限制继续保留，新增三个有界领域循环声明及负例。

## 实际 RED / GREEN

所有测试命令都使用 `scripts/run_fake_writer_tests.py`，先启用 fake_validation_guard；只使用临时目录与 Fake 客户端。每次终端执行前动态解析已安装 pwsh.exe，不写死版本路径。

1. 首轮 RED：`python scripts/run_fake_writer_tests.py tests/test_combat_agent.py tests/test_writer_production_exit_architecture.py` → **22 failed, 30 passed in 7.36s**。失败为缺少专家模块、requested_expert / combat_results、故事拒绝新工具。不是依赖或收集故障。
2. 最小接入组合 → **1 failed, 72 passed in 9.95s**。唯一失败是重启前 tuple 与 JSON 持久化 list 形状不一致；冻结存储统一为 JSON 形状。
3. 架构 RED → **4 failed, 51 passed in 2.05s**。缺少 v4 manifest 和有限循环架构检查器；补齐后未放宽透明适配器允许构造入口。
4. 普通分析兼容 RED → **1 failed, 63 passed in 7.66s**：大正文被专家来源预算提前阻断普通分析。改为冻结预算失败标记，只有实际委派失败；普通分析继续可用。
5. 两条 HTTP、来源捕获与现有故事/章节/透明出口组合 → **127 passed in 44.95s**。
6. 故事重试与专家来源详情 RED → **2 failed, 30 passed in 4.16s**：read_confirmed 重读最新设定；来源端点将 combat:0:1 转整数。改为冻结领域状态读取与步骤 ID 精确匹配。
7. 核心指定组合 → **86 passed in 11.91s**。
8. 扩大受影响回归 → **200 passed, 1 skipped in 61.12s**，见下方最终命令。跳过仍为任务1 Windows 符号链接权限。
9. 章节冻结重试补测 RED：`python scripts/run_fake_writer_tests.py tests/test_combat_agent.py -k retry_uses_original` → **1 failed, 31 deselected in 0.59s**。后来损坏的草稿被既有前置装配重读，导致旧请求失败；新增冻结分析装配并直接回放，避免重读最新正文/草稿/经验。
10. 修复后核心组合 → **87 passed in 18.63s**。
11. 冻结装配最终扩大受影响回归 → **200 passed, 1 skipped in 62.61s**。
12. 来源使用状态补测 RED：`python scripts/run_fake_writer_tests.py tests/test_combat_agent.py -k actual_read_body` → **1 failed, 31 deselected in 0.77s**。已读源元数据登记原显示 not_in_model；更正为 recorded，完整工具结果原文仍在实际完整消息中逐步捕获，目录项保持 not_in_model。

最终受影响命令：

```text
python scripts/run_fake_writer_tests.py tests/test_combat_agent.py tests/test_writer_production_exit_architecture.py tests/test_story_agent.py tests/test_agent_conversation.py tests/test_agent_conversation_http.py tests/test_story_http.py tests/test_writer_transparent_delegate_architecture.py tests/test_combat_context.py tests/test_agent_proposal.py tests/test_writer_context_sources.py tests/test_agent_runtime.py
```

最终结果：**200 passed, 1 skipped in 76.93s**，退出码0。另运行本任务涉及已跟踪文件的 `git diff --check`，退出码0，仅有 Git 的 LF/CRLF 提示。遵循任务授权的受影响验证范围，未运行无关全项目测试。

## 接口及裁定

- `requested_expert` 只接受 null / combat；显式 combat 在主 Agent 回答前执行一次专家，不能由模型忽略。限定 analyze；章节 Act 继续原 Proposal 写作，不在写作时临时采用未确认专家方案。
- 自主路径由实际模型 JSON `consult_combat` 决定；相同战斗字词的请求可自主调用或不调用，不做关键词分流。章节纯自然语言分析兼容，故事仍支持原 finish_turn。
- `execute_step(messages, *, step, sources)` 是专家模块的注入单步接口。模型参数 max_tokens=5000；所有主/专家调用均经过 RuntimeRunner + CapturingModelAdapter，透明类没有修改，也没有新增允许构造入口。
- 专家最多4步，读取上限8次（单动作/步的当前协议实际上最多4次）；单源12000、累计48000、单步总输入100000字符。预算耗尽返回 insufficient 和明确未知；必要冻结源超预算会保存明确失败，委派时提示缩小范围。
- 来源目录不含正文；只有 read_source 结果才进入专家实际消息。finish 的 evidence_refs 必须属于已读取且 usage=included 的来源集合。路径、跨源 ID、confirm/publish、递归委派、模型注入身份均拒绝。
- root 在调用任务1接口前经过 `validated_project(root.parent, project_id)` 的集合身份检查，并核对选定根。重复 ID/别名冲突在模型调用前拒绝。旧无 metadata 的传统临时会话仍能普通分析；不能获得专家读权限。
- CombatRequest 嵌套字段由消费方深拷贝，不修改任务1请求。`combat_context` 保存原冻结身份与源 ID；重试跨进程仍复用原请求，不重新冻结最新设定。结果由服务器分配 result_id，持久结果 job_id 绑定此次重试任务，不冒充失败旧任务。
- `main_input` 保存首次主 Agent 消息；章节 `analysis_state` 保存源登记偏移及决策元数据，重试直接回放，不重新读取新正文/草稿/经验。故事 read_candidate/read_confirmed 读取初始冻结状态，仅自身 propose 成功后更新本地 candidate；并发确认不会替换本次确认材料。
- `combat_results` 与 `tool_trace` 保存在原 AgentJob / 会话存储。专家步骤 ID 为 `combat:<主步>:<专家步>`，主步骤仍为整数。step_snapshots 每步含实际完整消息、已读来源 ID/版本/hash 及成功模型输出；错误保留 job.error，捕获送达状态仍只声明 adapter_call_started。
- 专家来源元数据中已读取项 usage=recorded、reason=read；只列目录项 usage=not_in_model、reason=catalog_only。实际完整工具结果含正文、版本/hash及原证据身份，保存在逐步完整消息快照；不把目录项冒称为已送入正文。
- 旧 story 主 Agent 既有 propose_revision 功能保留；专家本体没有此工具，不自动采用专家结果、确认候选或写正文。

## Ruling / 范围与限制

- Ruling：章节 Act 不接受 requested_expert — 专家结果仅在分析/讨论中产生，避免把未确认方案直接写作；后续任务3/4提供采用与确认消费。若用户未来要求写作内研究，需要独立扩展。
- Ruling：必要专家来源超预算冻结为失败标记 — 防止未选择专家的普通分析被新能力阻断；实际委派仍明确失败，不重新取材料替换。
- Ruling：沿用主控当前共享工作区、单任务 brief 与本报告作为进度记录 — 用户已明确授权串行实现并保留共享未提交成果；没有另建 worktree、提交或清理技能脚本工作区。主控负责独立复审，本代理不派代理。
- 未引入 UI、候选采用/确认、章节计划过滤、新客户端类、队列、独立 Runtime 或事实库。
- 仅验证 Fake 输出的工具协议与实际入模链路；未真实模型验证建议质量或模型工具遵循率。未执行浏览器 UI 验收。
- Windows 符号链接真实越界测试沿用任务1跳过；不将该项声称通过。
- 无真实小说写入、真实模型、生产 Runtime、8877 操作、commit/push/merge、删除或子代理。保留全部共享未提交修改。
