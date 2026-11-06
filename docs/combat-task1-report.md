# 战斗专家任务 1 实施报告

状态：已完成任务 1 实现、隔离回归与独立审查轮 1 最小修复，DONE_WITH_CONCERNS；待主控复审。

## DONE / CURRENT / TODO

- DONE：范围、请求、结果 dataclass；严格 verdict；按书冻结有限来源；只读来源查询；核心 RED→GREEN；受影响 Fake 回归。
- CURRENT：独立审查轮 1 修复交接主控复审。
- TODO：固定历史规划尚无入口；在支持符号链接的环境补跑链接越界测试。任务 2—6 未实施。

## 文件与职责

- `creative_os/combat_model.py`：CombatScope、CombatRequest、CombatResult 公共契约；scope 正整数去重约束、四种 verdict 校验。
- `creative_os/combat_context.py`：build_combat_context、read_combat_source；身份和路径约束、来源预算、正文与设定冻结。
- `tests/test_combat_context.py`：临时目录测试；不创建 Runtime，不访问模型。
- 本报告。未修改 creative_context.py、writer_context_sources.py 或其他既有模块。

## 实际 RED / GREEN

先检查 `scripts/run_fake_writer_tests.py`、`scripts/fake_validation_guard.py`：runner 开启真实模型客户端与外网防护。新增测试全部使用 tmp_path，仅对测试临时书根设置 fixture。

1. RED：`python scripts/run_fake_writer_tests.py tests/test_combat_context.py` → **6 failed**，五个指定用例均触发缺少战斗上下文公共接口的显式失败（预算用例有两个参数），退出码 1。不是缺少依赖、测试收集或环境错误。
2. 最小实现 GREEN：同命令 → **6 passed**，退出码 0。
3. 补边界后：同命令 → **15 passed, 1 skipped**。
4. 严格 verdict 非字符串补测 RED：同命令 → **1 failed, 14 passed, 1 skipped**，`test_verdict_is_strict_but_reply_is_free_text` 捕获 list 导致 TypeError；加类型校验后统一 ValueError。
5. 最终 GREEN：`python scripts/run_fake_writer_tests.py tests/test_combat_context.py tests/test_story_architecture.py tests/test_writer_context_sources.py tests/test_project_directory_identity.py` → **73 passed, 1 skipped in 6.72s**，退出码 0。

跳过项：`test_linked_source_cannot_escape_root`，当前 Windows 账号无法创建符号链接。实现会校验每个固定来源路径 resolve 与 absolute 相等，拒绝链接目录或文件；这条实际链接测试未验证，不将其计为通过。

遵循任务计划的验证边界，没有扩展运行无关全项目测试。

## 接口裁定与消费说明

- root 是已选小说的书根，而非 projects 集合根，须由 registry / validated_project 选定。本函数只复用 read_project_metadata(root.parent, root) 验证具名根元数据身份，不重复扫描项目集合或判断全局身份冲突；project_id 必须严格等于 project.json.id，不能用目录别名代替书 ID。任务 2 集成入口由主控确保此边界。
- task_id 映射请求 job_id。来源 source_id 绑定 project_id/session_id/job_id 和快照位置。read_combat_source 的 snapshot 参数是 CombatRequest；返回匹配来源的深拷贝，不重新读取实时文件，不把 source_id 当路径。
- sources 为 tuple[dict, ...]。已纳入正文的来源含 text/hash/version、original_chars、excerpt_start/end、truncated=False。缺失条目 usage=missing，不提供虚构正文；可选来源因预算无法纳入时 usage=not_read、reason=budget_exceeded，未冻结正文。
- kind 分别为 confirmed_story、working_draft、written_chapter、story_candidate。目标稿 role=target；相邻正文 role=adjacent。目标章先列工作稿、再列正式稿，即使有工作稿，也保留正式稿独立身份。
- 正式设定从 StoryArchitectureStore.view() 的 confirmed 冻结，保留 content/version/hash 等完整确认信息；不调用写入或确认方法。
- **轮 1 修正：当前未确认故事候选标 story_candidate，不能冒充 legacy_plan。** 候选继续附“未确认规划，不是已发生事实或正式设定”。固定历史规划尚无入口，不猜测路径、不扫描历史文件。旧版报告将当前候选解释为旧规划的裁定已撤销。
- 不隐式枚举全书章节。指定目标全部按章读取；相邻来源最多两个固定相邻章。空章节范围只读取可用故事设定/未确认规划，不读取章节、不代表自动适用全书。
- 必要正式设定或目标正文超过单源 12000 / 累计 48000 字符，抛出 required_combat_context_budget_exceeded，明确提示缩小范围；不静默截断。相邻正文与未确认故事候选属于可选来源，超预算明确不纳入。来源 text 的累计长度计预算，confirmed_story 复用同一设定的完整证据对象，不重复累计。

## 独立审查轮 1 修复（2026-10-26）

- P2：当前 architecture 候选来源 kind 从 legacy_plan 更正为 story_candidate；测试同时断言不存在 legacy_plan 冒名来源。
- build_combat_context 公开 docstring 明确 registry / validated_project 选根前置条件及本函数仅校验具名根元数据的边界；没有新增全目录扫描。
- RED：先改测试断言，再运行 `python scripts/run_fake_writer_tests.py tests/test_combat_context.py` → **1 failed, 14 passed, 1 skipped in 1.06s**，退出码 1；`test_confirmed_story_and_story_candidate_stay_separate` 因找不到 story_candidate 触发 StopIteration。
- GREEN：更正来源 kind 后运行同命令 → **15 passed, 1 skipped in 0.30s**，退出码 0。跳过项仍为 Windows 符号链接权限。
- 文件内容快照及“消费方不得修改嵌套字段”的已知限制保留；未扩大范围，未调用真实模型、生产 Runtime 或 8877，未操作 Git，未启动子代理。修复后交主控复审。

## 自审与限制

- 已覆盖目标工作稿优先、缺章不借邻章冒充、跨书 source_id 与根身份拒绝、目录/文件/mtime 无写入、必要内容单项及累计预算、实时文件变化不改冻结正文、返回来源深拷贝、空范围不读正文、确认与候选分离、四 verdict 及非法值、非法章范围。
- dataclass frozen 限制顶层字段赋值，嵌套 dict 仍是 Python 普通数据结构；消费方应把请求视为冻结输入，禁止自行修改 sources 或 confirmed_story。来源读取返回深拷贝。
- 没有模型调用、8877 操作、生产 Runtime、真实小说写入、commit/push/merge、删除、子代理或审计启动。
- 没有覆盖或清理共享未提交改动。独立审查与后续集成由主控负责。
