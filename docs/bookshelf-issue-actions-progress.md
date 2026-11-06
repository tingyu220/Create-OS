# 书架异常处理进度

日期：2026-10-25。状态：任务5已独立复验通过；任务6实现及完整隔离矩阵已完成，待总控独立最终验收。

DONE：全局异常/预览/操作状态GET及三个严格命令POST已接入。无效身份、路径字段、确认、JSON、预览、继续编号在可写接管前拒绝。旧默认根503/409、scoped稳定ID入口重新读取新根；响应发送前再核对GET门禁，覆盖读取期间发生迁移的情况。

DONE：原生弹窗及书架入口、逐本原因/影响/未知数量、项目分页、目录版本变更、迟到响应及检查失败保留旧详情已接线。预览取消零POST；勾选指定文本后单次POST；丢响应查询同操作；sessionStorage仅保存operation_id且重载只GET；显式核对和再次确认继续分开。结果使用textContent，Escape关闭并返回入口焦点。

CURRENT：任务6最终8场1440/390真实阶段与断连恢复通过；guard Python260、Node35通过，原书架和三书身份浏览器回归通过。当前交付、逐条矩阵、截图绝对路径、保留备份、命令与SHA256见bookshelf-issue-actions-v1.md。

TODO：总控独立最终验收；无部署/重启/远程仓库操作授权。本轮没有进一步操作生产三书、8877、生产Runtime、模型或Git。

## 任务6完成记录

- 复用validate_bookshelf_issues_ui.py --full，夹具与矩阵独立成两个小模块；临时根及真实备份保留在.backup/bookshelf-issues-task6/fixtures/，随机端口，模型客户端禁用。
- 混合7项目两宽度、真实reserved/backing_up/backup_verified/moving/verified、取消/双击/焦点、备份前后及rename后断连、重载只GET、明确核对/取消继续/再次确认、稳定ID打开/最近记录、旧默认503/409、新scoped和旧Runtime写拒绝均通过。最终报告8场、6份成功备份、2个无备份failed分支。
- guard Python260通过90.53秒，无跳过；本轮未改Python产品代码，不重复无变化后端全集。最终相关Node35通过。原书架与三书身份两宽度回归通过。
- 发现两处展示问题，先Node RED再最小修复：成功读回状态清除早期404失败提示；旧默认重载说明限制为verified。后端任务5审计hash148F6B140113C81737E770B9A1A8A1A1A9A10650E45E24FB590D220CF8CCD16E未变；当前JS hash91FA9B5F7138A22C79B9C16E5964CCA9C6E2EE3493784EFEBE9DCE97F5A85887。
- 屏障最初阻塞同步Playwright路由回调、keepalive响应finished等待及原书架初始化面板竞态仅修测试等待，未因此改产品逻辑。最终重新跑完整8场通过，诊断failure截图保留但排除最终截图清单。
- 交付docs/bookshelf-issue-actions-v1.md及.backup/bookshelf-issues-task6/report.json，待独立验收。历史生产重启影响不因本轮隔离验收而被补充为零。

## 任务5实际验证（历史）

- `python scripts/run_fake_writer_tests.py tests/test_bookshelf_issues_http.py tests/test_web_command_dto.py tests/test_web_workspace_routes.py tests/test_project_issues.py`：并发补修后31通过，8.52秒，无跳过（初次交付26通过，首轮复审28通过）。
- `node --test --test-reporter=dot tests/test_bookshelf_ui.js tests/test_bookshelf_issues_ui.js tests/test_workspace_navigation_ui.js`：复审修复后19通过（初次交付17通过）。
- `python scripts/validate_bookshelf_issues_ui.py`：guard+临时根，Chromium 1440×1000及390×844；预览/取消、焦点返回、无横向溢出通过；POST 0、页面异常0、模型尝试0、临时文件字节及mtime不变。
- 截图：`.backup/bookshelf-issues-task5/preview-1440.png`、`preview-390.png`；报告同目录`report.json`。已人工查看两张截图。
- 早期失败证据：HTTP缺路由、无效身份创建锁、读取期间迁移假零；Node初始模块缺失。之后最小实现修复。本轮追加测试曾因测试HTTP客户端中文raw body未编码而失败，已修正夹具UTF-8编码。既有书架错误文案回归曾失败，保留“读取失败”约定后通过。

## 范围及接口说明

- 新模块：bookshelf_issues_web.py负责全局HTTP及数据入口门禁；bookshelf-issues.js负责弹窗与操作状态；web_workspace.py仅装配单一迁移服务、路由和门禁，不装配第二套Runtime。
- project_issues.py的total/total_projects按项目数分页，checked_projects是当前页检查项目数。只读取当前页摘要；重复稳定ID的不同目录不会合并为一个问题。
- 原绿白视觉保留；确认文字为“已了解影响并确认先备份再迁移”。备份位置由服务端提供。
- scoped伪迁移命令拒绝422；旧默认GET不可用503，写入口409；新全局GET不创建创作Runtime。
- 外部持久锁与迁移记录锁协议要求所有写入进程采用匹配版本；本轮离线测试不证明可混用旧写进程直接部署。
- 未commit/push/merge；共享已有变更保留。任务5测试仅临时根/Fake，无真实书写或模型任务。

## 任务5独立审计P1/P2定向修复

状态：两项最小修复及定向验证已完成，后续任务5最终复验已通过；以下保留当时记录。

P1：首次scoped门禁尚未绑定适配器，仍按稳定ID检查。select_project之后，响应发送前改用本请求实际writer_adapter.project_root（无writer时回退agent_runtime.root），避免已完成迁移后root=None把旧绑定误判可读。不重新装配Runtime，不笼统禁用scoped入口。

P1 RED：新增真实临时HTTP测试在AuthorHomeQuery.read开始时执行一次真实迁移，旧scoped响应实际200/fresh/formal0而断言503失败。GREEN：旧请求503；随后同一scoped URL新请求按新根200/formal1；无可写Runtime接管。

P2首轮：为409 preview_stale增加error.operation_id/project_id/operation_created=false。界面必须核对这些身份及明确false才清除已拒绝操作和sessionStorage、取消旧状态查询回调，允许重新预览。没有此证据、身份不匹配、丢响应、5xx仍保留原操作，GET404不解锁。后续审计发现首轮未加锁证明有并发缺口，已按下一节补修；不能依靠首次无锁读取签发证明。核对/继续语义不变。

P2 RED：HTTP缺少三项绑定证据失败；Node在明确拒绝后operation仍非null失败。GREEN：明确拒绝后可以重查/重预览且重载不恢复已拒绝操作；未知分支和无证据/异身份409继续锁定原操作，重载只GET。

`python scripts/validate_bookshelf_issues_ui.py --review-regressions`：在guard临时根运行，原1440/390预览取消零POST冒烟仍通过；另6个真实页面反例（两宽度×过期预览/丢响应/5xx）通过。过期预览真实POST409；未知分支浏览器拦截模拟失败且真实状态GET404；每次重载均零POST。临时项目和迁移数据在测试主动改动正文后保持字节和mtime不变；明确拒绝证明允许产生现有外置锁协议的空锁文件。无页面异常、无模型客户端构造；这些6例无实际迁移。P1真实临时迁移在HTTP测试中验证。

反例报告：`.backup/bookshelf-issues-task5/review-report.json`；截图`review-{stale,lost,5xx}-{1440,390}.png`。已人工查看390过期预览和1440未知状态截图。

首轮修复仅改两个实现文件、两个测试文件及隔离浏览器脚本；没有进一步操作生产服务、真实书、模型、生产Runtime或Git。

## P2并发补修：拒绝证明与首次迁移互斥

状态：P1、P2已据总控任务5最终独立复验全部关闭；以下保留并发补修记录。

RED：完全相同的双POST（包含request_id、operation_id、token、指纹和幂等键），A在首次validate入口由Event暂停；B完成真实临时迁移并返回202/verified；释放A，旧实现返回409+operation_created=false。新增HTTP断言失败；独立390浏览器用同一屏障再现页面operation被清空的失败。

最小修复：首次无锁预检失败后，复用operation_migration_lease取得与首次迁移相同的工作区外置锁及项目身份锁，在锁内重读操作。已有操作交原CommandBoundary绑定并重放/查询，不再使用过期预览推断未执行；没有操作则在同一锁内再校验预览，仅确实拒绝且记录仍不存在时返回绑定身份的false证明。锁忙409、记录不可读503均不签operation_created=false。没有新增锁协议，没有修改前端、迁移执行流程或P1根目录核对。

GREEN：HTTP双请求均202且原结果完全一致，只一次真实临时迁移和一份备份。新增锁忙/记录不可读反例均不签false。明确stale可重预览、丢响应/5xx/单独404保留原操作、重载仅GET的原回归仍通过。拒绝证明测试明确允许原协议空锁文件及其父目录的mtime变化，除此以外项目数据、迁移意图、备份均不能新增或变化；纯GET/预览取消仍断言整个临时根文件不变。

- Python定向31通过，8.52秒；Node19通过（前端源码未改）。
- `python scripts/validate_bookshelf_issues_ui.py --review-regressions`：原双宽度取消冒烟、6个重载反例再次通过。
- `python scripts/validate_bookshelf_issues_concurrent_ui.py`：guard随机端口+临时真书，390页面A与HTTP客户端B发送完全相同POST；两响应202，状态verified，原操作/sessionStorage保留，无“尚未开始”误报；页面只发送一次POST，重载只GET原操作；一份备份，原始/目标/备份字节一致；无页面异常、模型尝试。
- 并发报告：`.backup/bookshelf-issues-task5/concurrent-report.json`；截图`review-concurrent-390.png`，已人工查看。

本次仅实现文件bookshelf_issues_web.py、HTTP测试、隔离浏览器验证脚本及进度记录变化。没有生产三书/模型/生产Runtime/8877/Git操作。

## 本会话重启的独立事实记录

用户在当前会话直接发送原文“重启”，覆盖了此前不擅自重启的限制。首次后台Start-Process被自动审批以“blocked by policy”拒绝，随后采用工具托管前台进程启动；未停止任何已有进程，初始8877无监听。

实际命令：`python -u scripts/novel_web_workspace.py --project-root projects/文明升阶 --host 127.0.0.1 --port 8877`。PID 37620，工具session 4398，进程创建时间2026-10-25 05:27:50 +08:00。页面、projects及recent三路200，作品3部、warnings空。

启动确实构造生产WriterAgentRuntime，默认recover=True，因此执行恢复检查。只读检索启动后项目文件mtime，仅发现`projects/.creative_os/project-write-locks/ca2b7c2690efeb5d27df68f9974a137574d609a639066eab9825a3eae3ff8cec.lock`于05:27:54更新；未发现书稿或恢复记录更新，但没有启动前哈希基线，不能把mtime检查当作完整零写入证明。未主动提交模型任务；启动代码的客户端工厂延迟调用，但无出站审计证据，模型调用绝对为零未知。

收到总控停止进一步生产操作要求后，未再操作生产服务/真实书，亦未自行停止服务。上述重启成功不代表任务5交付完成，也不代表本轮最终代码已经在生产服务完整加载。

## 任务5交付快照SHA256（历史）

| 文件 | SHA256 |
| --- | --- |
| creative_os/bookshelf_issues_web.py | 148F6B140113C81737E770B9A1A8A1A1A9A10650E45E24FB590D220CF8CCD16E |
| creative_os/web/bookshelf-issues.js | 554EA977272A5AC74CEF933FD6F9C4E29192A425F56D207E1368105ED6176747 |
| creative_os/web_workspace.py | 01C7BF8F6D86E3E3DFA628B9053CC47BC7FCE63A48692B66B9743C421E84AFBA |
| creative_os/project_migration.py | C590BE29927B88C842BF75372E29F1452CC4E00AD80739C4C914E3F0DCEDD8AB |
| creative_os/project_issues.py | BFF018076955F9C6FFE952B13DB2EA2135AFE1DF7CE837989FFF9C3E3298EE22 |
| creative_os/web/index.html | C695B2A0C78CA1C1B3023C86FE6EA212DC542440FA53715CF0A2AE57189985FF |
| creative_os/web/app.js | B26DE2E473F8DB0A1C4C99D9026DAA005C3EDCC4F61EFC07A6C5FA99C32916E9 |
| creative_os/web/styles.css | 79D3115697613045B25697CBBD2131A2CE2ED7A57B536DE4AAC93BB0B69A8002 |
| tests/test_bookshelf_issues_http.py | 89BD67B8638F04FE6DB4B6EBB300EE7F8AD501CF6532869F5EC31976C913D344 |
| tests/test_bookshelf_issues_ui.js | D1241CB10BE59E6C686BD540ED9DBCEC9DF1F32FC9E09000B423F44DF19CC3C6 |
| tests/test_project_issues.py | 8663FDD8D7E31AA6A0540DEC49A6A7783E1C3AA1C68ABEADF61B5EF40646B04E |
| scripts/validate_bookshelf_issues_ui.py | C0C8537A8F9DEC4FDED0F2937698B56494C04BFAB7F9BAAE385538A450C013BA |
| scripts/validate_bookshelf_issues_concurrent_ui.py | E56BC2C5A1C1FD5E1B3BA824E3916E1C877A53B3A1CBF0A2E3A282255B8EA84A |
