# 任务5：现有对话界面的作者操作

任务1—4已独立通过，现接入既有对话界面，不新建战斗工作台。

最小修改 web/writer-agent.js、web/story.js 及现有页面；新增小型 web/combat-panel.js（若现有组件可容纳则复用）；新增 tests/test_combat_ui.js、tests/test_combat_http.py。

显式专家入口传 requested_expert；采用候选只传服务端 result_id、当前revision和原命令身份；确认继续使用既有故事确认接口。显式采用章节计划写作传 require_confirmed_combat=true，不能关键词判断；普通写作兼容。

先写HTTP/Node失败测试：明确入口、进度、建议/来源/未知范围、采用但不确认、版本冲突保留输入、跨书迟到结果不显示、失败恢复不重复提交、编辑及确认后进入目标章；使用textContent与键盘可用。运行python scripts/run_fake_writer_tests.py tests/test_combat_http.py及node --test tests/test_combat_ui.js记录RED，再最小实现GREEN。

只用现有HTTP/命令边界，不让前端控制权限；未确认不入正式写作，失败/未知状态可见且不重复提交。全书研究结果必须先指定章节或保持研究用途。不要改真实书、模型、生产Runtime、8877或Git；测试guard临时根/Fake，动态pwsh.exe，apply_patch。报告docs/combat-task5-report.md，完成后独立审查。
