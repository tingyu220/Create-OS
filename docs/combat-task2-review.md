# 战斗专家任务2独立审查

状态：**已完成**。规范审查通过；代码质量审查通过。本轮未发现需要阻塞任务2交付的问题。

审查依据为 `combat-task2-brief.md`、实施报告及 `combat-task2-review-package.txt`。共享差异包含历史改动，本次仅审查报告所述战斗接入；没有重新审计旧故事、Proposal 等功能。为核对具名疑点，额外读取了结果类型校验、冻结来源身份校验和实际消息捕获实现。

## 阻塞清单

无。

## 规范核查

- 真实调用闭环成立：章节 DTO 和 HTTP 入口传递可选 `requested_expert`（`creative_os/web_workspace.py:424`、`:429`）；故事入口同样传递（`creative_os/story_web.py:105`）。缺省为 null；显式调用在主 Agent 回答前执行（`creative_os/chapter_agent_tools.py:85`、`creative_os/story_architecture_agent.py:58`）。自主路径消费模型工具动作，允许直接结束，没有关键词路由。现有测试覆盖两种会话的自主、显式及不调用。
- 模型调用继续经过 `WriterAgentRuntime._execute_story_step` → `RuntimeRunner.execute` → `CapturingModelAdapter`（`creative_os/agent_runtime.py:473`）。新增领域模块没有客户端、Runner 或适配器构造。v4 manifest 声明三个有界循环；原透明类整体 AST 约束保留，新增负例覆盖无界 while、直接 complete、直接 Runner 和适配器别名绕出口（`tests/test_writer_production_exit_architecture.py:157`）。
- 每步实际消息在透明适配器调用前捕获，成功输出随后补入步骤快照（`creative_os/agent_runtime.py:481`、`:484`）；专家目录与已读引用分别登记，来源版本/hash及原证据 ID 保留（`creative_os/chapter_agent_tools.py:61`）。目录没有正文，工具读取后的正文才进入下一次专家消息；故事来源端点按完整专家步骤 ID 精确检索（`creative_os/story_web.py:42`）。
- 专家请求从任务受理时冻结；重试直接深拷贝原请求（`creative_os/chapter_agent_tools.py:23`）。章节已有装配直接回放（`:130`），故事主输入与 read_candidate/read_confirmed 复用冻结状态（`creative_os/story_architecture_agent.py:46`、`:78`）。未见以最新设定替换已冻结材料的接点。
- 首次冻结前经过集合级 `validated_project` 并核对根目录（`creative_os/chapter_agent_tools.py:30`）；结果 ID、项目/任务/范围来自服务器持有的请求，模型不能添加身份字段。重试结果绑定本次 job（`:69`），原证据引用继续保留原冻结身份。
- 专家仅有 read_source/finish，动作字段严格校验；路径、身份、确认、发布及递归动作均拒绝（`creative_os/combat_agent.py:31`）。读取结果须等于冻结源，结论引用须已读（`:71`、`:83`）。4步、8读、单源12000、累计48000、输入100000及输出5000tokens有对应约束；超预算明确返回未知。主循环6步，已有专家结果后拒绝重复委派（`creative_os/chapter_agent_tools.py:47`）。
- 结果写入现有 job 和 tool_trace，专家没有候选/正文写接口。章节 Act 继续既有 Proposal 路径；显式专家仅限 analyze 是报告列明的接口裁定，符合本轮只读范围。旧故事主 Agent 的 propose_revision 权限没有转交专家。

## 质量与非阻塞限制

- 新专家循环、桥接和章节工具逻辑分置小模块，Runtime 复用既有单步入口；职责边界清楚，未引入第二套 Runtime、客户端或队列。
- 当前单动作协议每步只能读一个源；需要模型主动 finish 时，4步预算最多先读3次。8次读取为额外上限，并不表示当前可以读取8个来源；实现报告已披露这一约束。
- 静态架构检查是对声明结构及已列负例的回归约束，不是任意 Python 动态绕过的安全证明。当前代码中未发现实际绕出口调用。
- Fake 验证能证明协议、权限及输入链路；不能证明真实模型的建议质量或工具遵循率。没有进行真实模型、浏览器 UI 或生产运行验证。
- Windows 符号链接越界用例仍因权限跳过，不能记为通过。任务3—6的候选采用、确认消费、章节过滤及 UI 未实施，均不列为本轮缺陷。

## 验证与操作记录

实施报告记录最终受影响回归为 **200 passed、1 skipped**。本轮独立追踪接口、循环、捕获及重试代码和对应断言；没有新发现需要动态复现的具体疑点，因此遵照审查要求未重复整套或已通过的定向测试，不将报告结果冒称为独立重跑。

只新增本审查文档；未修改生产代码或测试，未派代理，未调用真实模型、生产 Runtime 或8877，未操作真实书内容，未执行 Git 写入。
