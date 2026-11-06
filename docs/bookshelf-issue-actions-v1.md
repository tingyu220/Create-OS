# 书架异常处理：任务6交付

日期：2026-10-25。状态：**已完成实现及隔离验收，待总控独立最终验收**。未部署、未重启正式服务。

## 结果与本轮范围

书架可逐项查看异常、预览同根目录整理、明确确认执行，并按原操作查询、核对和再次确认继续。稳定ID、书稿和历史保持不变。任务5的HTTP及互斥实现已通过独立复审，本轮后端源码保持审计哈希不变。

任务6复用`validate_bookshelf_issues_ui.py`增加`--full`入口；夹具和矩阵分别放在`bookshelf_issues_fixture.py`、`bookshelf_issues_acceptance.py`，避免把不同职责堆进主脚本。夹具位于`.backup/bookshelf-issues-task6/fixtures/`，使用随机端口及禁止模型的临时Runtime，最终成功证据保留，不接触正式三书。

截图核对发现并最小修复两处前端文案：成功读回状态后清除先前404留下的失败提示；仅verified且后端声明需要重载时显示旧默认入口重载说明。两项均先补Node失败测试再修复，各是一处显示更新，不改迁移、确认或幂等语义。

## 实际命令与结果

所有执行经动态解析的当前PowerShell 7路径运行。

| 命令 | 实际结果 |
| --- | --- |
| `python -u scripts/validate_bookshelf_issues_ui.py --full` | 最终8场全部通过：1440/390各4场，零页面异常，模型尝试为空 |
| `python -u scripts/validate_bookshelf_ui.py --output-dir .backup/bookshelf-issues-task6/bookshelf-regression` | 只读GET、两宽度书架循环、异常/空态全部通过，零模型 |
| `python scripts/validate_project_directory_identity_ui.py --output-dir .backup/bookshelf-issues-task6/identity-regression` | 两宽度、三稳定ID、正文/最近记录/无横向溢出通过，项目内容/目录/mtime不变 |
| `node --test --test-reporter=dot tests/test_bookshelf_ui.js tests/test_bookshelf_issues_ui.js tests/test_workspace_navigation_ui.js tests/test_writer_initial_source_ui.js tests/test_story_ui.js` | 最终35通过，无跳过 |
| 下列guard Python集合 | 260通过，90.53秒，无跳过；之后只改前端显示及验证脚本，未重复运行无变化的后端全集 |

Python集合实际通过PowerShell数组展开，没有把通配符原样传给pytest：

```powershell
$tests = @(Get-ChildItem tests/test_project_migration*.py | ForEach-Object FullName)
$tests += @("tests/test_migration_atomic_evidence.py", "tests/test_project_issues.py",
  "tests/test_bookshelf_issues_http.py", "tests/test_web_command_dto.py",
  "tests/test_web_workspace_routes.py", "tests/test_project_authority_transaction.py",
  "tests/test_writer_draft_store.py", "tests/test_story_review_fixes.py",
  "tests/test_agent_proposal_reconcile_http.py", "tests/test_project_directory_identity.py",
  "tests/test_project_catalog_http.py")
python scripts/run_fake_writer_tests.py @tests
```

## 浏览器逐场矩阵

全部状态来自实际HTTP状态GET及持久记录。阶段屏障只暂停临时服务执行，不伪造前端阶段。

| 场景（两宽度均运行） | 注入/执行 | 必须满足的结果 | 迁移/核对/继续POST数 |
| --- | --- | --- | --- |
| 混合书架完整成功 | 7项目：正常书、英文技术目录、中文简称、坏metadata、重复ID两目录、坏摘要 | 正常书可打开；重复/损坏逐项保留；正式稿已知1、候选未知；仅英文目录有整理动作 | 1 / 0 / 0 |
| 真实五阶段 | after_intent、after_backing_up、after_backup_verified、after_moving、after_verified屏障 | reserved→backing_up→backup_verified→moving→verified分别与后端记录相同，逐阶段截图 | 不新增执行POST |
| 备份前断连 | after_command_reserve抛SystemExit，仅退出临时请求线程，形成真实无响应 | reserved等待核对；重载仅GET；明确核对后failed；原根/稿件保持，备份不存在，不显示成功/重载提示 | 1 / 1 / 0 |
| 备份校验后断连 | after_backup_verified退出临时请求线程 | 核对后backup_verified；取消继续预览零POST；再次勾选明确继续才移动；同operation、单份已验证备份 | 1 / 1 / 1 |
| 移动后断连 | after_rename退出临时请求线程，持久阶段moving | 不自动补写；明确核对后verified；目标inode保持，无第二次搬运，补齐原回执 | 1 / 1 / 0 |

每个成功打开作品的场景另有一次`/api/projects/recent`；混合成功场景先打开正常书，因此另有两次最近记录POST。最终报告逐条保存实际POST路径和请求体。

## 按规格验收

| 要求 | 证据与边界 |
| --- | --- |
| 中文原因、影响、未知数，不吞正常作品 | 混合书架两宽度：检查7/7、6项问题；4个安全作品仍列出；坏回执的候选未知由原书架两宽度回归另行实测 |
| 中文简称不提供迁移 | 混合书架中简称目录已中文，仍保持全名metadata，仅技术目录有一个整理按钮 |
| GET/预览/取消纯读 | 完整临时根文件字节与mtime快照相等；取消无迁移POST；重新预览产生新UUID但不落盘 |
| 原生确认、键盘与焦点 | Enter打开详情；取消回预览按钮；Escape关闭回书架入口；固定确认文字；双击仅一次迁移POST |
| 实际阶段与执行期防重复 | 两宽度各观察五个持久阶段，状态刷新只GET；POST进行中核对按钮禁用 |
| 丢响应不新建操作 | 三类真实执行线程中断，原operation/sessionStorage保留；页面重载前后临时根快照不变、POST数不增加 |
| 核对、继续分开 | 备份后场景明确核对一次，再次预览取消不执行，勾选后独立continue一次 |
| 默认旧根与scoped | 每个非终态默认及scoped读503、默认写409；其他书scoped200；verified后旧默认仍503/409，新scoped返回formal1 |
| 旧写实例拒绝 | 临时旧Runtime的store.save及_write_decision均在旧根mkdir前拒绝；旧源不重建，目标快照不变 |
| 成功打开稳定ID与最近记录 | 六个成功场景打开`/p/stable-book/writer`，读到原工作稿；选择器/最近记录均为stable-book，未按中文目录名替换ID |
| 全量备份及不串书 | 成功场景原始/目标/备份build_inventory完全相等，含metadata、隐藏二进制、空目录；各一份备份；其他书快照不变 |
| 目标竞争、链接、活动任务、坏证据、16阶段中断 | guard Python集合覆盖；此部分为领域/HTTP/真实进程测试，未声称全部在浏览器逐项重演 |
| P1/P2并发审计修复 | 后端保持任务5独立复验哈希；当前Node仍覆盖明确拒绝与未知分支。任务5双请求真实HTTP/390证据见进度文档，不将旧报告冒充本轮新执行 |
| 不覆盖/删除/自动回滚 | 浏览器各分支核对实际根和清单；双存/双失/备份冲突等保留证据的分支由guard Python参数矩阵验证 |

## 证据路径

主报告（8场实际operation、绝对工作区、备份路径、POST、状态和截图清单）：

[report.json](</D:/田雨/Creative OS/.backup/bookshelf-issues-task6/report.json>)

代表截图，已人工查看桌面和手机的混合详情、成功、失败与断连状态：

- [390混合异常](</D:/田雨/Creative OS/.backup/bookshelf-issues-task6/mixed-390.png>)
- [1440真实备份阶段](</D:/田雨/Creative OS/.backup/bookshelf-issues-task6/stage-backup_verified-1440.png>)
- [390成功结果](</D:/田雨/Creative OS/.backup/bookshelf-issues-task6/success-390.png>)
- [390备份前失败](</D:/田雨/Creative OS/.backup/bookshelf-issues-task6/reconciled-before-backup-390.png>)
- [1440移动后待核对](</D:/田雨/Creative OS/.backup/bookshelf-issues-task6/interrupted-after-rename-1440.png>)
- [390稳定ID写作页](</D:/田雨/Creative OS/.backup/bookshelf-issues-task6/opened-390.png>)

保留的真实临时备份示例：

`D:/田雨/Creative OS/.backup/bookshelf-issues-task6/fixtures/success-390-tzzrqvlj/.backup/project-directory-migrations/a23e7884-02aa-4783-a19c-e4766dabbcac/project`

全部6份成功备份的绝对路径见主报告各case.backup；两个备份前失败场景backup为null，不能声称它们已有备份。原书架及身份回归报告分别位于同目录`bookshelf-regression/report.json`、`identity-regression/report.json`。早期`failure-*`截图作为诊断保留，已从最终报告截图清单排除。

## 失败记录与最小修复

1. 首次阶段等待阻塞了同步Playwright的路由回调：改为泵送浏览器事件直到真实服务线程屏障到达，不改产品代码。
2. keepalive最近记录已200并落盘，但等待其未消费响应体finished会挂起：验证200及服务端真实最近记录；离页取消该响应体列为允许的导航结果，其他请求失败仍拒绝通过。
3. 原书架390旧摘要入口在初始化完成前被点击，初始化随后切回正文面板：验证脚本先等待章节就绪再打开导航；产品代码未改。重跑原书架完整两宽度回归通过。
4. 截图发现verified旁仍显示先前状态404失败提示，Node新增用例RED后，在成功状态GET后清除旧提示，GREEN。
5. failed/pending仍显示未来的默认入口重载说明，Node新增用例RED后，将该说明限制为verified，GREEN；最终完整8场再次通过。

## 当前源码及报告SHA256

| 路径（相对项目） | SHA256 |
| --- | --- |
| creative_os/bookshelf_issues_web.py | 148F6B140113C81737E770B9A1A8A1A1A9A10650E45E24FB590D220CF8CCD16E |
| creative_os/web/bookshelf-issues.js | 91FA9B5F7138A22C79B9C16E5964CCA9C6E2EE3493784EFEBE9DCE97F5A85887 |
| tests/test_bookshelf_issues_ui.js | F0D4F0CB8D5B95D68E2C3AE070ABCE4B606051A6EA9692DF9DC1157420E0360F |
| scripts/validate_bookshelf_issues_ui.py | 874331C7E626DE8A6876875A5C763C387F01C7771BE83E552654D90F9A7B5095 |
| scripts/bookshelf_issues_fixture.py | 94542676232571F9CE5C8D711C386AB5F6634036D9012150D7EF07F616B935D6 |
| scripts/bookshelf_issues_acceptance.py | F81936625D9DE33F2BB0FA2CDA13156DFC4253818528C3A8ED728ABCD1CDAB65 |
| scripts/validate_bookshelf_ui.py | 678C5BEFDB10192D1DC0A381AAA8B95D35DCF73F6409CAA3599D2115DCFB50D1 |
| .backup/bookshelf-issues-task6/report.json | 78A797716D72298D03F31F3262BA63D2A650D14106FF49B9BAC7B1059C366322 |

## 限制与待处理

本轮是Windows、Chromium、loopback及隔离根验收，未验证其他操作系统或真实断电；浏览器三个断连位置用请求线程SystemExit模拟持久执行中断，guard Python另有真实进程退出测试。不是正式部署验收。

外置写锁/记录锁要求所有写进程采用匹配协议版本，不能混用旧写进程直接部署。任务6未操作正式三书、8877、生产Runtime、模型或Git。历史人类授权重启没有启动前哈希基线，仍不能补充“零影响”承诺，详见进度记录。

待总控独立最终验收；正式加载和远程仓库操作不在本次执行范围。
