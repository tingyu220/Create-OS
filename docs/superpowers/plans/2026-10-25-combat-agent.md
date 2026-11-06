# 战斗编排专家 V1 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL：使用 superpowers:subagent-driven-development 或 superpowers:executing-plans 逐任务实施。沿用用户选择的开发与独立审查协作方式；本计划待确认，不自行启动实现。

**Goal:** 在现有对话中按需调用战斗专家，形成有来源的候选方案，经作者明确确认后实际用于章节写作，并可在不同小说独立复用。

**Architecture:** 一个 Runtime 队列与 RuntimeRunner，独立专家工具循环；建议保存在既有任务记录，采用方案通过现有故事候选及确认机制。章节冻结确认版本，沿用 Proposal 接受正文，不建立第二套事实库、审批或模型客户端。

**Tech Stack:** Python、原生 JavaScript/HTML、pytest、Node、Chromium；不增加依赖。

**Spec:** `docs/superpowers/specs/2026-10-25-combat-agent-design.md`，作者已于2026-10-25批准。

## Global Constraints

- 全部自动测试先启用 fake_validation_guard，只用临时根与 Fake 模型；不真实模型、不生产 Runtime、不重启8877。
- 不修改真实书稿、设定或历史；《文明升阶》仅只读研究，结论写到项目外的开发文档。
- 不commit/push/merge；保留共享未提交改动。开发串行，审计只读，避免重叠修改。
- 专家为必备能力而非每章必调；不能关键词路由冒充自主决策；明确调用通过显式工具选择字段表达。
- 计划不是已发生事实；未确认不入正式写作，确认方案不等于接受正文；不自动发布。
- 方法可复用，小说事实与经验默认按书隔离，不自动跨书检索。
- 每任务先运行失败用例再最小实现，记录实际 RED/GREEN、偏差和 DONE/CURRENT/TODO；不以代码存在代替验收。

## 文件职责与公共契约

以下为新接口的确定名称；新模块置于 creative_os，测试置于 tests。类型用标准 dataclass/TypedDict，不引入通用框架。

| 模块 | 职责与接口 |
| --- | --- |
| `combat_model.py` | `CombatScope(chapter_numbers: tuple[int,...], purpose: str)`；`CombatRequest(project_id, session_id, job_id, instruction, scope, confirmed_story, sources)`；`CombatResult(result_id, project_id, job_id, verdict, reply, alternatives, foreshadowing, evidence_refs, unknowns, scope)`。verdict严格为combat/setup/noncombat/insufficient；正文段落自由，不强制固定节拍 |
| `combat_context.py` | `build_combat_context(root, project_id, scope, *, task_id, session_id, instruction) -> CombatRequest`，禁止隐式读全局会话。`read_combat_source(snapshot, source_id) -> dict`只读已列入快照的来源，返回正文/哈希/读取范围 |
| `combat_agent.py` | `run_combat_expert(request, *, execute_step, read_source) -> CombatResult`，仅read_source/finish工具，无确认/写入/再委派权限 |
| `chapter_agent_tools.py` | 主 Agent 的有限工具决策循环，支持consult_combat及finish；保留既有普通分析输出，写作仍进入原Proposal路径 |
| `combat_story_candidate.py` | `stage_combat_candidate(store, result, *, expected_revision, actor, operation_id) -> dict`；只在当前版本基础合并指定战斗块，复用store.propose，不自行确认 |
| `combat_context_selection.py` | 从冻结的正式故事版本选择适用计划，`select_confirmed_combat(confirmed, chapter_number) -> tuple[dict,...]`；不得读取最新候选补充冻结数据 |

`build_combat_context`最终签名固定为 `(root, project_id, scope, *, task_id, session_id, instruction) -> CombatRequest`。sources每项含source_id、kind、chapter_number、version/hash、text、完整/截断范围；引用必须属于实际读取集合。result_id由服务端生成并绑定任务，不由模型决定身份。

预算：专家最多4个模型步骤、最多8次来源读取、每来源最多12000字符、累计源内容48000字符、单步总输入100000字符、输出上限5000 tokens。主 Agent 一轮最多委派一次，不递归；普通主循环最多6步。必要正文或设定超预算明确要求缩小范围，不能静默截断。预算可配置但首版不新增设置页面。

## Review Focus

1. 故事工具目前完整替换候选：添加战斗块必须保留作者其他内容，基线变化拒绝，不能靠模型记住全部原文（任务3）。
2. 当前章节没有正文但前文存在：输出证据不足，不能编造当前章节缺陷；跨书同编号不串来源（任务1/2）。
3. 未来计划被写成既成战果，或不适用章节消费全量计划：冻结来源与语义标识必须同时正确（任务4）。
4. 重试、迟到专家结果和作者编辑交错：旧结果不能覆盖新候选，执行中不能重新读取新设定冒充冻结输入（任务2/3/4）。
5. 新模型调用绕过Runtime或只在UI显示来源但实际消息缺失：严格架构出口与捕获断言（任务2/4/6）。

### 任务1：证据输入与专家结果契约

**Files:** 新增combat_model.py、combat_context.py；复用creative_context.py、writer_context_sources.py，只做必要适配；新增test_combat_context.py。
**Interfaces:** 产出上表CombatRequest/CombatResult与只读来源函数；无持久化副作用。

- [ ] 写失败测试：`test_target_draft_precedes_formal_and_adjacent`断言目标工作稿、正式稿分开标识；`test_missing_target_is_not_inferred`断言目标不存在；`test_cross_book_source_rejected`断言同编号另一书不可读；`test_query_does_not_write`比较文件/目录/mtime；`test_required_context_over_budget`断言明确预算错误。
- [ ] 运行 `python scripts/run_fake_writer_tests.py tests/test_combat_context.py`，记录缺接口或断言失败，不把环境错误当RED。
- [ ] 实现只读来源索引及冻结正文。正式设定、已写正文、工作稿、旧规划分别标kind；未知、未读取与截断范围明确返回。路径必须受现有项目身份与根约束。
- [ ] 同命令全绿；记录接口与覆盖证据，待独立审查，不提交。

### 任务2：真正的按需专家委派

**Files:** 新增combat_agent.py、chapter_agent_tools.py；最小修改agent_runtime.py、story_architecture_agent.py及实际请求DTO/路由；新增test_combat_agent.py；扩展test_writer_production_exit_architecture.py及现有出口manifest，不粗放白名单。
**Interfaces:** 消费任务1快照；产生CombatResult，存入现有job记录及tool_trace。Runtime仅加小型单步执行委派，模型调用仍经RuntimeRunner和CapturingModelAdapter。

- [ ] 写失败测试：Fake主Agent选择consult_combat/不调用两路径；显式`requested_expert="combat"`保证调用，缺省null；两种专家读取顺序得到不同建议；noncombat/insufficient合法；禁止confirm/publish、任意路径及再次委派；步数耗尽明确返回未知。
- [ ] 运行 `python scripts/run_fake_writer_tests.py tests/test_combat_agent.py tests/test_writer_production_exit_architecture.py`，确认RED。
- [ ] 实现主Agent有限工具循环和专家模块；显式请求字段只控制作者指定专家，不把中文关键词当确定路由。故事与章节会话均支持，旧请求字段缺省保持兼容。工具执行身份从任务注入，模型不能改project/session/job。
- [ ] 实际消息捕获每步输入、工具来源和输出，保持重试快照；不可因失败重新取最新上下文替换原输入。测试取消/错误不会修改候选或书稿。
- [ ] 上述测试及 `tests/test_story_agent.py tests/test_agent_conversation.py`全绿；核对新调用链和manifest负例。

### 任务3：建议进入现有候选与确认机制

**Files:** 新增combat_story_candidate.py；最小修改story_architecture_store.py、story_architecture_command.py；新增test_combat_story_candidate.py。
**Interfaces:** 消费任务2结果；通过现有story propose/confirm产生不可变版本，不新建审批存储。

战斗块key为`combat-plan:<result_id>`；保留key/title/text既有形状。在故事修订内增加可选受校验`combat_plans`关联字段（旧记录缺省空），记录block_key、result_id、project_id、scope、evidence_refs及来源hash。该字段纳入候选hash和确认快照，不将机器元数据塞进可编辑正文。同一原子聚合保存内容及关联；渲染明确“未来创作计划，非已发生事实”。关联字段不能授予模型确认权限。

- [ ] 写失败测试：并入方案保留全部非目标块与未决问题；CAS旧revision拒绝；重复operation幂等；跨项目/伪结果身份拒绝；作者编辑后hash变化；确认绑定版本及hash；聊天认可不确认；未确认结果不可作正式来源。
- [ ] 运行 `python scripts/run_fake_writer_tests.py tests/test_combat_story_candidate.py tests/test_story_architecture.py`，确认RED。
- [ ] 实现受控合并与兼容解码；结果从本任务持久记录读取，不能信任客户端完整结果。旧项目无候选时采用已存在确认版本为基线，否则新建只含建议的候选并明确尚无其他正式设定，不假装完成全书设定。
- [ ] 作者修改战斗正文可保留来源关联但标“作者修订”，不得宣称修改文字由原证据直接证明；删除块同步移除关联。全绿并验证操作中断遵循现有原子聚合语义。

### 任务4：确认计划实际进入章节写作

**Files:** 新增combat_context_selection.py；最小修改story_context.py、agent_runtime.py及需要的提示组装；新增test_combat_writer_context.py。
**Interfaces:** 消费任务3确认快照；输出适用计划内容/版本/hash/source_ref给既有写作消息和来源详情。

- [ ] 写失败测试：适用章节包含确认计划且候选哨兵不出现；不适用章节不含计划文本；未来计划有非事实标签；运行中更新确认不改变当前消息；两书同result标题不串书；必要内容超预算明确拒绝。
- [ ] 运行 `python scripts/run_fake_writer_tests.py tests/test_combat_writer_context.py tests/test_agent_proposal.py`，确认RED。
- [ ] 冻结时保留完整版本证据，组装时过滤战斗块，不能只追加选中计划而仍把所有战斗块通过原story.text重复注入。普通故事块保持原行为。scope空章节集合表示全书研究建议，不自动应用任一章节；具体章节采用前由作者明确范围。
- [ ] “采用方案写作”要求明确确认；普通旧项目写作保持兼容。正文仍为Proposal，接受才改工作稿，拒绝不改正式稿或工作稿。
- [ ] 运行本任务、Proposal及出口架构测试全绿，捕获Fake实际messages断言内容，而非只检查DTO/路径。

### 任务5：现有对话界面的作者操作

**Files:** 最小修改web/writer-agent.js、web/story.js及其页面；新增小型web/combat-panel.js（若现有组件可容纳则复用）；新增test_combat_ui.js、test_combat_http.py。
**Interfaces:** 显式专家入口传requested_expert；候选采用请求只传服务端结果ID、当前revision及原命令身份。确认继续使用原故事确认接口。

- [ ] 先写HTTP/Node失败测试：明确入口、进度、可读建议/来源/未知范围、采用到候选不确认、版本冲突保留输入、跨书迟到结果不显示、失败恢复不重复提交、编辑及确认后进入目标章。
- [ ] `python scripts/run_fake_writer_tests.py tests/test_combat_http.py`与`node --test tests/test_combat_ui.js`确认RED。
- [ ] 实现中文轻量入口与建议详情，复用右侧详情/现有对话，不增加独立战斗工作台。显示采用范围；全书研究结果需作者指定章节或保持研究用途。用textContent，键盘可用。
- [ ] 成功重载、拒绝、未知结果沿用现有命令规则；不能仅前端按钮控制权限。两测试及现有story/agent页面回归全绿。

### 任务6：完整验收及《文明升阶》只读研究

**Files:** 新增scripts/validate_combat_agent_ui.py、docs/combat-agent-v1.md、docs/combat-agent-progress.md、docs/research/文明升阶-战斗与伏笔候选.md。
**Interfaces:** 消费任务1—5全部能力；交付隔离验收证据和只读研究，不部署。

- [ ] 构造两本不同设定临时小说，1440/390实测讨论→自主/明确调用→建议来源→作者编辑→确认→目标章实际入模→Proposal差异→接受；另测非战斗建议、缺正文、拒绝、跨书迟到、旧版本冲突和失败重试。
- [ ] 执行 `python scripts/validate_combat_agent_ui.py`，预期零真实模型、零跨书来源污染、无重复版本、无横向溢出；保存截图、messages快照、实际POST及字节断言。
- [ ] 执行全部新增 `test_combat_*.py`（PowerShell展开文件数组传guard），`node --test tests/test_combat_ui.js`及受影响story/proposal/出口测试；记录真实通过/跳过/限制，不扩成无关全项目重跑。
- [ ] 只读检索《文明升阶》已写正文与规划，建立已读章节及哈希清单；写技术能力/限制、冲突证据、后续方案与前文伏笔候选。研究文档明确已读范围、假设、未知与非事实建议，不修改小说文件、不调用真实付费模型；不把未读全书概括为没有战斗。
- [ ] 独立审查完整方案、消息捕获及浏览器证据；阻塞修复再验，真正完成才收口。正式服务加载及真实写作另行授权。

## 自审与交接

覆盖：只读双向研究与事实边界→任务1/6；自主委派与可复用能力→任务2；候选编辑及确认→任务3；适用范围、冻结与实际入模→任务4；现有界面→任务5；跨书/端到端→任务6。

接口串联为CombatRequest→CombatResult→story修订内combat_plans关联→确认快照→适用章节消息→既有Proposal。唯一新持久数据属于现有job和story聚合，没有第二权威。预算、范围空值、关联元数据和兼容策略为本计划提出的实现决策，待作者确认计划后执行。

计划不含自动提交步骤：用户规则要求单独确认。沿用已选子会话/代理协作方式，执行前冻结当前任务边界，不沿用旧重启指令。每个可独立验收任务完成后审查；不以反复基础设施扩展替代战斗创作闭环。
