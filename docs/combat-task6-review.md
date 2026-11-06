# 战斗专家任务6最终独立只读复核

状态：**已通过（P0/P1 为 0；保留 1 项不阻断的 P2 证据增强建议）**。

## 复核范围与限制

已阅读 `docs/combat-task6-brief.md`、`docs/combat-task6-report.md`、`docs/combat-agent-progress.md`、`docs/research/文明升阶-战斗与伏笔候选.md` 和 `scripts/validate_combat_agent_ui.py`，并检查任务6验证产物、战斗 UI 过滤实现及相关测试。全程未连接真实书、真实模型、生产 Runtime、8877 或 Git；未修改代码。新增的复跑产物位于 `.backup/combat-task6-review-run-20261027/`。

## 独立验证

- `python scripts/validate_combat_agent_ui.py --output-dir .backup/combat-task6-review-run-20261027`：`status=passed`，随机端口 `51734`，临时项目为“任务6甲书/任务6乙书”，实际 POST 数为 **13**，浏览器错误为空。
- `node --test tests/test_combat_ui.js`：**4 passed**。覆盖显式 `requested_expert`、跨书结果过滤、采用前置读取失败、空候选 revision 0。
- `python scripts/run_fake_writer_tests.py tests/test_combat_agent.py tests/test_combat_context.py tests/test_combat_story_candidate.py tests/test_combat_http.py tests/test_combat_writer_context.py`：**92 passed, 1 skipped**；跳过项为既有符号链接权限限制。
- `python -m py_compile scripts/validate_combat_agent_ui.py`：通过。
- 复跑 `posts.json` 的 13 条记录，UTF-8 字节数与 SHA-256 全部重算匹配，响应状态为 202/422；GET 刷新不增加 POST。
- 复跑截图文件尺寸为 `combat-1440.png` **1440×1000**、`combat-390.png` **390×847**。后者是 390×844 视口的 full-page 截图，宽度与无横向溢出断言一致；报告中的 390×844 指视口尺寸。
- 研究文档表格有 **81** 行，当前正式章节文件有 **81** 个；逐文件 SHA-256 重算 **0** 个不匹配。

## 必核对项

- **双临时书与隔离**：脚本在随机临时根创建两本书；甲书结果为 `combat`，乙书缺正文结果为 `insufficient`，未知项保留“目标章节正文未提供”。复核 `messages.json`、结果 ID、项目 ID 和最终工作稿，没有发现甲书候选或消息进入乙书。`CombatPanel.render()` 同时按 `project_id` 与 `scope.chapter_numbers` 过滤，UI 单测验证跨书迟到结果不渲染。
- **全链路**：讨论、未请求专家的普通分析、显式 `requested_expert=combat`、来源读取、候选采用、作者编辑、确认 v1、确认计划进入第2章真实写作消息、Proposal 差异和接受工作稿均有脚本断言。最终消息含“未来创作计划，不是已发生事实”、版本/hash/source_ref 与作者编辑文本。
- **未确认阻断与普通写作兼容**：`require_confirmed_combat=True` 在未确认计划时返回 `story_confirmation_required`；默认普通写作仍生成 Proposal。
- **revision 冲突**：确认后以旧 `expected_revision=0` 重复采用，HTTP 返回 422（允许实现返回 409/422），确认版本仍为 v1，未产生第二版本。
- **失败重试**：乙书 Fake 首次调用返回 `fake_retry_once`，HTTP retry 成功。复核临时运行时持久记录，重试任务与原任务 instruction、`main_input` 数量和 `combat_context` 哈希一致，且通过 `retry_of` 关联，证明沿用冻结输入。
- **按需而非关键词路由**：自主普通分析未设置 `requested_expert` 且 `combat_results=[]`；显式入口才产生专家结果。采用命令只提交 `result_id`/revision，确认仍由作者命令完成。
- **研究边界**：研究文档明确列出读取范围、已知事实、未知事项和推断；候选声明不等于 `combat-plan`，不能自动写入正文。81 章标题与哈希和当前文件一致，没有把未知身份、战斗规模或武器参数推断成事实。

## 分级发现

### P0

无。

### P1

无。核心隔离、确认权限、版本冲突、重试冻结输入、消息证据、两种视口和只读研究边界均有通过证据。

### P2（不阻断）

任务6 E2E 流程中，`FakeCombatClient` 虽定义了 `noncombat` 返回分支，但 `_run_book()` 的乙书路径使用“缺正文”，实际命中的是 `insufficient`，因此该分支没有在本脚本的临时书链路中执行。相关 verdict 合法性和专家拒绝/证据不足约束由 92 项 Combat 单测覆盖；建议后续补一条临时书非战斗冲突 E2E，以使 brief 中的“拒绝”路径在同一脚本中有直接产物。另，E2E 没有专门构造跨章晚到结果，跨章过滤目前由 `CombatPanel.render()` 的章节条件和上下文单测支撑，建议补一条 UI 异章样例。

## 最终结论

**通过**：没有 P0 或 P1，任务6可交主控汇总并进入后续授权决策。P2 仅是验证覆盖的增强建议，不影响本轮隔离全链验收、UI 宽度验收、版本/重试边界或《文明升阶》只读研究的结论。
