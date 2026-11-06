# 任务2：真正的按需专家委派

设计及计划已批准。2026-10-26任务1已独立复审通过，现在执行任务2。

任务1消费裁定：root必须由现有registry/validated_project完成集合级身份检查后传入，不能绕过重复ID/别名冲突；候选来源kind为story_candidate，未读取固定历史旧规划。请求快照的嵌套字典不得修改，重试复用原冻结材料。

新增combat_agent.py、chapter_agent_tools.py；最小修改agent_runtime.py、story_architecture_agent.py及实际请求DTO/路由；新增test_combat_agent.py；严格扩展出口架构manifest及负例。不新建客户端、Runtime或队列。

消费任务1CombatRequest冻结快照；实现run_combat_expert(request, *, execute_step, read_source) -> CombatResult。工具仅read_source/finish；身份由服务器注入。实际读取集合限定evidence_refs。主Agentconsult_combat/finish工具循环，支持自主不调用；显式requested_expert="combat"保证调用，缺省null，禁止关键词路由。故事与章节会话均支持，保持普通分析及Proposal写作路径兼容。

最多专家4步/8次读取/单源12000字符/累计48000/单步输入100000/输出5000tokens；主循环6步，每轮最多1次专家，不递归。noncombat/insufficient合法；超预算明确未知，不伪造结论。所有模型调用经RuntimeRunner/CapturingModelAdapter，保存每步实际消息、来源和输出；重试沿用冻结输入不读取最新设定替代。结果存现有job及tool_trace，不能修改正文或确认候选。

TDD：Fake自主调用/不调用/显式调用、两种读取顺序、合法非战斗/材料不足、非法confirm/publish/path/递归、预算耗尽、取消错误不写候选、重试冻结。先RED再GREEN：python scripts/run_fake_writer_tests.py tests/test_combat_agent.py tests/test_writer_production_exit_architecture.py；再受影响tests/test_story_agent.py tests/test_agent_conversation.py。读取当前代码后确定最小接点，不扩充大Runtime方法，复杂逻辑置新小模块。

本任务不做候选采用/确认、章节计划过滤、UI，这些在后续任务。不得因已有story流程可提出候选而让战斗专家获得写权限。

全部测试先guard、临时根/Fake；不真实书写入/模型/生产Runtime/8877/commit/push/merge；保留共享未提交修改。动态解析pwsh.exe，apply_patch编辑。不得派子代理。报告docs/combat-task2-report.md，实际RED/GREEN、变更文件、接口偏差及限制。出现跨任务接口疑问及时上报。
