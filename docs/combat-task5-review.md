# 战斗专家任务5独立审查报告

状态：**已通过**

审查范围：`docs/combat-task5-brief.md`、`docs/combat-task5-report.md`、`docs/combat-agent-progress.md`，以及任务5相关未提交实现与测试。未连接真实书、真实模型、生产 Runtime、8877；未修改实现。

## 验证结果

- `python scripts/run_fake_writer_tests.py tests/test_combat_http.py tests/test_combat_writer_context.py`：**25 passed**。
- `node --test tests/test_combat_ui.js`：**1 passed**。
- 未重跑无关大回归。

## 已核对通过项

- `writer-agent.js` 与 `story.js` 的显式入口都发送 `requested_expert: "combat"`，服务端也限制该值只能为 `combat`，没有用关键词替代显式选择。
- 采用命令只从客户端接收 `result_id` 和 `expected_revision`；DTO、`StoryCommandHandler`、`stage_combat_candidate` 会校验 story 目标、当前项目/会话、作者 actor、候选版本，并从服务端任务记录重读结果及来源。采用只追加故事候选，不调用确认接口；确认仍由既有 `confirm_story_candidate` 完成。
- `require_confirmed_combat` 已进入 `AgentJob` 持久化结构，重试和从决策执行的路径均沿用原值；显式 act 会校验冻结故事中的本章已确认战斗计划。普通写作默认值为 `false`，保持兼容。
- 结果渲染按 `project_id` 和 `scope.chapter_numbers` 过滤，因此跨书、跨章迟到结果不会进入当前面板。
- 采用失败路径没有自动再次提交；请求缓存使用固定幂等键，后续重试需作者再次操作。按钮是原生 `button`，文本使用 `textContent`。

## 本轮复审结果

前一轮提出的两项 P1 已有实现和 guard 覆盖：卡片现在展示建议、可选方案、来源证据、未知范围与后续伏笔；`adopt()` 已将 session/view 读取放入统一 `try/catch`，读取失败会调用 `onStatus`，且不会发出 POST。新增 UI guard 与定向回归均通过。

## 发现

### P1（已修复）：战斗结果面板没有呈现建议、来源和未知范围

已在 `card()` 中以 `textContent` 分别呈现 `alternatives`、`evidence_refs`、`unknowns`、`foreshadowing`，并新增测试覆盖。

### P1（已修复）：采用前置读取失败不会显示到状态区

已将 session/view 读取与采用 POST 放入同一 `try/catch`，并新增测试确认读取失败可见且不会发出 POST。

### P1（已修复）：初始故事没有 candidate 时，前端错误阻止首次采用

已移除对 `view.candidate` 存在性的强制要求，仅校验 story 查询成功；候选缺失时通过 `view.candidate?.revision || 0` 发送 `expected_revision=0`，并新增 RED/GREEN 测试覆盖首次采用。

## 结论

没有发现 P0/P1/P2。HTTP/持久化/版本与权限边界、跨书跨章过滤、采用与确认分离、普通写作兼容性及三项 UI P1 修复均有实现和窄测试证据，任务5通过独立复审。

本轮验证：`node --test tests/test_combat_ui.js` → **4 passed**；`python scripts/run_fake_writer_tests.py tests/test_combat_http.py tests/test_combat_writer_context.py tests/test_story_http.py` → **30 passed**。
