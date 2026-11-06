# 战斗专家任务5实施报告

状态：**已完成**（主控独立复审待处理）。

## DONE / CURRENT / TODO

- DONE：既有 writer/story 页面增加显式战斗专家入口；请求明确发送 `requested_expert="combat"`。
- DONE：故事命令 HTTP 边界开放 `adopt_combat_candidate`，严格绑定 `result_id`、当前 `expected_revision`、story 会话和作者身份，复用既有候选编辑与确认命令。
- DONE：章节 Agent intent / decision-act 接入显式 `require_confirmed_combat`；任务持久化并在安全重试时保留该参数。普通写作默认保持兼容。
- DONE：新增 `combat-panel.js`，按项目、章节和范围过滤结果，跨书或异章迟到结果不渲染；采用失败只显示错误，不自动重复提交；采用后提示作者编辑并确认。
- DONE：按钮使用原生 `button`、状态使用 `textContent`，可键盘操作。
- TODO：主控独立审查；未操作真实书、真实模型、生产 Runtime、8877 或 Git。

## 文件

- `creative_os/web/combat-panel.js`
- `creative_os/web/writer-agent.js`、`creative_os/web/writer.html`
- `creative_os/web/story.js`、`creative_os/web/story.html`
- `creative_os/web_workspace.py`、`creative_os/web_command_dto.py`
- `creative_os/agent_runtime.py`
- `tests/test_combat_http.py`、`tests/test_combat_ui.js`

## TDD / 验证

1. Node RED：`node --test tests/test_combat_ui.js` 在新增面板前因文件不存在失败；实现后通过。
2. HTTP RED：临时回退 DTO 接线后，`python scripts/run_fake_writer_tests.py tests/test_combat_http.py` 出现 `command_not_allowed`；恢复实现后通过。
3. 定向 HTTP / 故事回归：`python scripts/run_fake_writer_tests.py tests/test_combat_http.py tests/test_story_http.py tests/test_story_architecture.py` → **23 passed**。
4. Agent / 上下文回归：`python scripts/run_fake_writer_tests.py tests/test_combat_http.py tests/test_story_http.py tests/test_combat_writer_context.py tests/test_agent_runtime.py` → **39 passed**。
5. UI 回归：`node --test tests/test_combat_ui.js tests/test_story_ui.js tests/test_writer_agent_ui.js` → **30 passed**。
6. 合并定向回归（含 Shell / DTO）：`python scripts/run_fake_writer_tests.py tests/test_combat_http.py tests/test_story_http.py tests/test_story_architecture.py tests/test_combat_writer_context.py tests/test_agent_runtime.py tests/test_writer_shell_assets.py tests/test_web_command_dto.py` → **75 passed**。

验证均通过 `scripts/run_fake_writer_tests.py` 临时 Fake 根执行；未提交、未推送、未合并。

## 独立审查修复

按 `docs/combat-task5-review.md` 修复两项 P1：结果卡片现在分别展示建议、可选方案、来源证据、未知范围与后续伏笔；采用流程将 story session/view 前置读取纳入同一错误处理，读取失败会调用 `onStatus` 且不会发出采用命令。

TDD：新增两项 Node RED 后，`node --test tests/test_combat_ui.js` → **3 passed**；受影响回归 `node --test tests/test_combat_ui.js tests/test_story_ui.js tests/test_writer_agent_ui.js` → **32 passed**，`python scripts/run_fake_writer_tests.py tests/test_combat_http.py tests/test_combat_writer_context.py tests/test_story_http.py` → **30 passed**。

## 首次空候选修复

按最新审查补充首次故事 `candidate: null` 的 RED，确认采用流程仍应以 `expected_revision: 0` 发出命令。移除对 `view.candidate` 存在性的强制要求，仅保留 HTTP 成功和 story session 必要字段校验。

验证：`node --test tests/test_combat_ui.js tests/test_story_ui.js tests/test_writer_agent_ui.js` → **33 passed**；Fake guard 窄回归 → **30 passed**。

