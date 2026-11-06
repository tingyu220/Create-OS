# 书架异常详情与有界目录处理实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: 使用`superpowers:executing-plans`顺序实施；当前仅交付计划，待总控安排实施后再改代码。不另起重叠开发。

**Goal:** 作者能逐本查看异常、重新检查，并对首版支持的目录命名建议完成预览、明确确认、备份校验、迁移及中断核对。
**Architecture:** 查询复用安全项目索引和作者摘要；迁移使用工作区级操作记录及既有CommandBoundary/FileCommandResultStore。将项目写锁按稳定ID移至源目录外，再衔接原项目锁；迁移只拥有文件系统命名与备份，不拥有创作权限。
**Tech Stack:** Python、原生HTML/CSS/JavaScript、pytest、Node、Chromium；Windows PowerShell 7+。
**Spec:** `docs/superpowers/specs/2026-10-20-bookshelf-issue-actions-design.md`。

## Global Constraints

- 全部后续验证仅guard临时项目；不改真实三书，不真实模型调用，不commit/push/merge。
- 正式8877已由总控重启并确认三书、零警告；不再次重启。不涉及战斗Agent。
- GET不创建Runtime、锁文件、操作记录或备份；刷新不执行迁移、继续执行或核对。
- 仅整理英文技术目录为metadata.title/name清洗所得中文书名；中文简称不是异常；不改ID、metadata、正文或历史。
- 任何链接/junction/硬链接、重复ID、越界、目标占用、身份或内容变化、活动写任务不明确，均拒绝执行；不覆盖、不删除、不自动回滚。
- 完整备份及清单校验通过，才能进行同卷且拒绝已有目标的原子目录重命名。逐文件SHA256及空目录集合必须保留。
- 复用现有浅色青绿、原生栈；1440/390实测、键盘可用，错误不能仅用颜色表示。

## 当前调用链与必须补齐的边界

| 现有入口 | 实际调用关系 | 本轮衔接 |
|---|---|---|
| 项目发现 | `scan_project_directories`→`ProjectCatalog`→`AuthorHomeQuery` | 保留坏目录、稳定ID冲突与分来源摘要诊断，不把未知数量报零 |
| 写请求 | `do_POST`→只读`select_project`→完整预检→`_activate_project`→适配器执行 | 迁移API放在项目路由之前；原写请求预检后再检查迁移门禁，禁止为拒绝请求装配可写Runtime |
| Writer保存/发布 | `CommandBoundary.reserve`→`WriterDraftCommandHandler`→`WriterDraftStore.save/promote`项目锁→回执complete | 回执reserve先于正文锁，必须连回执的reserve/complete/release一起纳入门禁 |
| Proposal/Lesson/Story | 专用Boundary先持项目锁，再调用通用Boundary | 沿用原审阅/对账语义，只增加外置身份锁；不把它们的RESERVED续办规则复制到迁移 |
| Agent提交/更新 | `WriterAgentRuntime.submit/act/retry/_set`→项目锁；模型调用在锁外 | 现存任务/排队执行未结束就拒绝迁移；不取消任务、不构造模型 |
| 新书/recent | `project_authority_lock(projects_root)` | 迁移使用相同工作区锁，与创建互斥；最近记录仍保存原ID |
| 锁文件 | 项目锁位于源目录内部 | Windows移动前不能持有源内文件句柄；新增源外稳定ID锁，不以HTTP按钮或任务状态代替互斥 |
| Registry与默认入口 | scoped请求从Registry取实例；`create_server`还闭包绑定默认适配器 | 成功后清除该ID的闲置缓存；默认闭包不能静默换书，旧绑定失效时明确要求重载 |

## 接口与存储契约

新增文件按职责分开，避免将实现继续堆入`web_workspace.py`：

| 文件 | 职责／公开接口 |
|---|---|
| `creative_os/project_issues.py` | `ProjectIssuesQuery(root).read(offset=0, limit=20) -> dict`；元数据全量索引、仅本页摘要。返回`items,total,offset,limit,checked_projects,catalog_revision`，每项含`issue_id,project_id,directory,title,code,message,impact,actions,known_counts`；`DirectoryMigrationPreview(projects_root, backup_root, signing_key).build(project_id) -> dict`及`validate(token, operation_id, plan_fingerprint) -> dict`提供无副作用预览/复核 |
| `creative_os/project_directory_inventory.py` | `build_inventory(root) -> dict`、`inventory_hash(value) -> str`、`copy_verified(source, backup, manifest) -> None`、`rename_no_replace(source, target) -> None`；拒绝所有链接，备份与相对清单比较，不调用shell |
| `creative_os/project_migration_store.py` | `ProjectMigrationStore(root).read_operation(operation_id) -> dict | None`、`write_operation(record) -> None`；读无副作用、写原子；单聚合`projects/.creative_os/directory-migrations.json`，不另造索引事务 |
| `creative_os/project_write_gate.py` | `project_write_lease(project_root)`、`migration_lease(projects_root, project_id)`、`assert_directory_available(projects_root, directory)`；源外稳定ID锁、活动操作/旧路径检查，数据层不导入Runtime |
| `creative_os/project_migration.py` | `ProjectMigrationService(projects_root, backup_root, registry, default_project_id=None, default_root=None)`；`preview(project_id) -> dict`委派任务1预览，`status(operation_id) -> dict`、`execute(request, trace_id) -> CommandHandlerResult`提供有界迁移与核对状态机 |
| `creative_os/project_migration_command.py` | 三个明确命令的校验/Boundary装配；复用通用命令结果与HTTP DTO，不改通用RESERVED语义 |
| `creative_os/bookshelf_issues_web.py` | 全局查询与三个命令路由；身份/JSON错误转中文稳定code，不读取任意文件路径 |
| `creative_os/web/bookshelf-issues.js` | 异常列表、预览确认、真实状态轮询和明确核对/继续执行；不拥有业务结果 |

HTTP契约：

- `GET /api/projects/issues?offset=0&limit=20`：limit=1..100，offset非负；异常使用稳定issue_id逐本保留，按directory与稳定ID共同分组，不按书名或重复ID合并。返回catalog_revision；UI分页累计已检查项目，目录版本变化就标旧详情过期并重新累计，未查完不宣称“全部无异常”。
- `GET /api/projects/migration-preview?project_id=<稳定ID>`：返回服务端生成的UUID operation_id、plan_fingerprint、preview_token、expires_at、源/目标/备份相对目录、文件/目录数量、影响与reload_required。TTL=600秒；token为服务内存随机密钥签名，GET不落盘，服务重启使未执行预览失效。
- 指纹覆盖工作区文件系统身份、源目录身份、稳定ID、metadata字节哈希、完整相对清单及内容哈希、目标空缺；备份位置由服务端配置的工作区`.backup/project-directory-migrations/<operation_id>/`产生，不接受客户端路径。其`project/`子目录仅存原书完整副本，`manifest.json`为同容器的旁置证据，不能混入小说清单。
- `GET /api/projects/migrations/<operation_id>`：读取已存阶段、原因、是否需核对、可用动作和稳定ID入口。已失去执行所有者的非终态只在响应中标“需核对”，GET不补写。
- 三个POST沿用完整CommandRequest外壳，`expected_version=null`，actor固定本轮作者身份；服务端校验确定的幂等键，指纹包含actor，不信任客户端request_fingerprint。

| command_id／POST路径尾部 | target | payload | 幂等键 |
|---|---|---|---|
| `migrate_project_directory`／`migrate-project-directory` | `{project_id}` | `{operation_id,plan_fingerprint,preview_token,confirmed:true}` | `directory-migrate:<operation_id>` |
| `reconcile_project_directory`／`reconcile-project-directory` | `{project_id,operation_id}` | `{plan_fingerprint}` | `directory-reconcile:<operation_id>:<request_id>` |
| `continue_project_directory`／`continue-project-directory` | `{project_id,operation_id}` | `{plan_fingerprint,continuation_no,confirmed:true}` | `directory-continue:<operation_id>:<continuation_no>` |

全部路径前缀为`/api/commands/`，只在全局处理；scoped变体拒绝。continue是核对后再次明确执行，不是自动重试：服务端仅接受已核对记录当前的continuation_no。它使用独立命令回执，原迁移RESERVED不直接重跑；成功时根据已存原请求及原trace模板补齐原回执。

操作记录至少包含schema、operation_id、project_id、原actor/规范化请求/命令指纹、原trace/结果模板、服务owner_epoch、根与目录身份、受限相对路径、plan_fingerprint、清单哈希、阶段、continuation_no、失败code与已验证检查点。owner_epoch只是当前服务是否认领执行的证据，不能仅凭PID或实例不同就宣称其他进程已死；GET保留真实阶段并说明需核对，显式核对先尝试取排他锁，忙则拒绝，不补写。清单正文存在备份证据中，不塞进轮询响应。损坏记录只报错并禁用写动作，不以空记录覆盖。

## Review Focus

1. 初次登记迁移与普通写锁竞争：不得出现“写方已检查空门禁，之后绕过迁移锁”；任务3用真实双进程屏障验证。
2. Windows打开的源内锁文件、重命名前目标突然出现：不得卡住后靠覆盖完成；任务3/4验证外置句柄和原子拒绝目标。
3. 已缓存默认Runtime、无scoped前缀的保存，以及回执早于正文锁：不得写回旧目录或返回假空正文；任务3/4/5分别验证。
4. 原命令已RESERVED但操作意图/备份/结果回执中断：不得把重复POST当作重新执行许可；任务2/4枚举所有持久化窗口。
5. 坏metadata、未知数量、目录整理建议和分页检查混合：逐项保留、原因准确，中文简称不被改名；任务1/5/6验证。

### 任务1：纯异常详情与迁移预览

**Files:** 新增`project_issues.py`、`project_directory_inventory.py`及`tests/test_project_issues.py`、`tests/test_project_migration_preview.py`；最小修改`author_home_query.py`、`project_directory.py`和`project_catalog.py`，只增加结构化诊断，保留旧字段。
**Interfaces:** 产出上表查询、inventory与preview所需数据。AuthorHome附加`issues`，按metadata/formal/draft/candidate/session区分；不回传原始异常、正文或密钥。

- [x] 先写并运行失败测试：技术英文目录+中文书名可建议；中文简称无建议；不安全目标/重复ID/坏metadata/链接不可执行；坏会话与坏回执只影响已知来源；正常书可用。
  ```python
  assert issue["code"] == "candidate_unavailable"
  assert issue["known_counts"] == {"formal": 2, "draft": 2, "candidate": None}
  assert issue["actions"] == ["recheck", "open"]
  ```
- [x] 写分页与预览失败测试：limit非法400；页外不读摘要；完整清单含空目录；同内容指纹稳定，源身份/内容/metadata/目标变化使指纹变化；摘要读取前后根身份变化时不能将目录消失当作零稿件；过期/服务重启token拒绝；全部GET前后文件、目录、内容mtime相同且Registry.get禁止调用。
- [x] 实现纯查询与预览；签名密钥仅在服务初始化的内存中，不写真实目录。再校验时重新构造指纹，不能只验token签名。
- [x] `python scripts/run_fake_writer_tests.py tests/test_project_issues.py tests/test_project_migration_preview.py`，预期全绿；RED及GREEN记录到专用进度文件，不提交。

### 任务2：持久操作身份及命令幂等

**Files:** 新增`project_migration_store.py`、`project_migration_command.py`、`tests/test_project_migration_store.py`；修改`web_command_dto.py`只增加三个允许命令。
**Interfaces:** Store原子保存整个操作聚合；CommandRequest严格采用上表。状态集合`reserved,backing_up,backup_verified,moving,verified,failed,needs_reconciliation`。

- [x] 先写失败测试：意图先于命令reserve保存；相同ID/同原指纹只返回已有结果，不生成第二备份；换actor/项目/指纹/路径字段拒绝；两本操作不丢更新，损坏聚合、被篡改的持久相对路径或未知阶段不可覆盖或用来访问根外文件。
  ```python
  assert duplicate["operation_id"] == first["operation_id"]
  assert len(list(backup_root.iterdir())) == 1
  assert snapshot(project_root) == before
  ```
- [x] 测试CommandBoundary现有RESERVED仍返回`command_outcome_unknown`；状态GET不触发handler；continue无已核对continuation_no或重复旧号不执行；已有操作重复请求不因原预览过期而变成新操作。
- [x] 实现迁移操作存储与意图边界：原始意图先写盘，持久相对路径和阶段严格校验，重复操作复用原身份，继续编号单调递增；通用CommandBoundary语义保持不变。
- [x] `python scripts/run_fake_writer_tests.py tests/test_project_migration_store.py tests/test_web_command_dto.py`，预期全绿。

### 任务3：写入互斥、活动任务及旧路径门禁

**Files:** 新增`project_write_gate.py`、`tests/test_project_migration_concurrency.py`；修改`domains/project_authority.py`、`workspace_command.py`的FileCommandResultStore写方法、`novel_project_command.py`、`project_registry.py`；必要时给WriterRuntime增加只读的活动执行查询/其自有Future跟踪，不改模型或任务行为。
**Interfaces:** 上表lease与`ProjectRegistry.assert_migration_idle(project_id)`、`invalidate_after_migration(project_id)`；不调用Registry.get来检查未打开的书。

- [x] 先用真实线程/进程和屏障写失败测试：保存、发布、Story确认、Proposal审阅/核对、Lesson、命令reserve/complete/release及Agent提交/后台更新，与同书迁移不会交错；新书初始化与迁移互斥；另一书读取和正常写入不串书。
- [x] 再测：持久jobs、缓存任务或排队Future非终态、RESERVED写回执、源对应的新书initializing意图、不可解析活动状态，均在备份前拒绝；迁移后旧路径写调用在mkdir之前拒绝，不重建旧目录。GET不创建任何锁。
- [x] 实现源外`projects/.creative_os/project-write-locks/<sha256(stable_id)>.lock`，保留线程/跨进程互斥和同线程重入深度。普通项目写锁固定顺序：外置身份锁→原项目锁→命令存储锁；迁移固定顺序：工作区锁→同一外置身份锁。迁移请求使用非阻塞获取，忙则409，不能等待持锁后台任务再猜安全；源内锁句柄不能跨越rename。
- [x] 普通写方对有project.json的受管项目始终先取得身份锁，不能只在“已有迁移记录”时才加锁；锁内复查门禁。已迁移源路径通过操作记录反查稳定ID，拒绝所有旧路径写入与路径复用。原无metadata的独立领域测试根保持原锁接口，不推断它为工作区。
- [x] FileCommandResultStore仅reserve/complete/release纳入门禁，constructor/read仍纯读；避免“正文被锁但回执已写”。新书在写意图前检查旧源路径不可复用。Gate读存储不能循环导入CommandBoundary/Runtime；Store原子写辅助可延迟导入。
- [x] `python scripts/run_fake_writer_tests.py tests/test_project_migration_concurrency.py tests/test_project_authority_transaction.py tests/test_writer_draft_store.py tests/test_story_review_fixes.py tests/test_agent_proposal_reconcile_http.py`，预期全绿，无死锁、无真实客户端。

任务3证据及边界见`docs/project-migration-task3-progress.md`；忙错误当前为领域代码，HTTP 409映射属于任务5。稳定ID哈希采用casefold以与目录身份索引一致。

### 任务4：备份、原子重命名与显式核对

**Files:** 新增`project_migration.py`及`tests/test_project_migration.py`、`tests/test_project_migration_reconcile.py`；完成任务1的IO函数，使用任务2记录及任务3门禁，不调用一次性PowerShell迁移脚本。
**Interfaces:** `preview/status/execute`及三个命令处理器；CommandHandlerResult只在真实verified后为accepted，已知无移动失败为failed/rejected，未知结果保留原RESERVED。

- [x] 先写临时真文件失败测试：完整备份含隐藏文件/空目录，备份字节SHA与源一致才允许moving；执行前重查源身份/完整指纹/目标空缺/活动任务；复制、校验或rename失败不覆盖/删除。
- [x] 测试目标在rename前最后一刻出现：`rename_no_replace`必须原子拒绝，而不是`Move-Item`式嵌套到已存在目录；Windows使用拒绝目标存在的原生目录移动，其他平台无法提供同等保证时拒绝该动作，不退化为覆盖。
- [x] 在每阶段原子记录前/后、CommandStore.reserve前/后、rename前/后、verified记录前/后、原complete前/后注入中断。校验实际文件与回执，不只断言mock次数；重启GET不得续跑。
  ```python
  assert target_inventory == backup_inventory == original_inventory
  assert not old_source.exists()
  assert len(backups_for_operation) == 1
  assert final_project_id == "stable-book-a"
  ```
- [x] 实现显式核对：源存在+目标不存在+与已验证备份一致→`backup_verified`并生成当前continuation_no，等待再次确认；源不存在+目标存在+与原备份/ID一致→verified并补原回执；双存/双失/身份或清单不匹配→needs_reconciliation，不搬、不覆盖、不回填。
- [x] 对尚未进入moving且未形成已验证备份的中断，只有源完全匹配原预览且目标不存在时，明确核对可结束为failed，保留部分备份，允许新operation重新预览；否则保持needs_reconciliation。该保守解释需总控在计划审阅时确认。
- [x] 迁移活跃阶段对该书数据入口给出明确暂不可用，不能读旧根并返回假零数量；verified后清除该稳定ID的闲置Registry缓存。默认适配器仍绑定旧根时记录reload_required，旧默认API返回明确503，旧默认写请求409；scoped稳定ID入口重新取新根可打开。不能重启服务或静默重绑到另一书。
- [x] `python scripts/run_fake_writer_tests.py tests/test_project_migration.py tests/test_project_migration_reconcile.py tests/test_project_directory_identity.py`，预期全部通过；永久保留备份及原操作身份。

任务4实现/中断矩阵及源码哈希见`docs/project-migration-task4-progress.md`。按总控本轮范围，503/409以只读availability接口交付，真实HTTP接入留任务5；原命令契约已按本计划HTTP表统一。任务3已独立验收，本轮扩展含记录锁的进程退出释放，待任务4复审。

### 任务5：HTTP与“查看并处理”交互

**Files:** 新增`bookshelf_issues_web.py`、`web/bookshelf-issues.js`、`tests/test_bookshelf_issues_http.py`、`tests/test_bookshelf_issues_ui.js`；最小修改`web_workspace.py`路由/默认旧根门禁、`web/index.html`、`web/app.js`、`web/styles.css`。
**Interfaces:** 全部采用本计划HTTP表；create_server装配单个迁移服务（固定workspace/backup根），不装配第二套创作Runtime或模型队列。

- [x] 先测路由/身份/JSON/路径注入/无效确认/过期预览、scoped伪命令、伪operation_id与continuation_no；拒绝前不能可写接管或备份。新错误映射409/422/503，非JSON响应显示中文，不暴露堆栈。
- [x] Node失败测试：逐本异常保留、分类原因/影响/未知数；重新检查失败保留旧详情并标过期；列表/搜索分页和迟到响应不丢已有异常；中文简称无整理按钮。
- [x] 测预览→取消零POST；确认只有一次POST；提交丢响应后读取同operation_id，不生成新操作；每个真实阶段显示后端值，刷新仅GET；需核对先核对再明确继续，不能一按钮暗中连做两步；成功可打开稳定ID入口。
- [x] 实现原生详情面板/确认区域，使用textContent。确认文本严格为“已了解影响并确认先备份再迁移”；执行期间禁重复提交。将operation_id保存在当前origin的sessionStorage，页面重载仅恢复状态查询；成功/失败/需核对分别呈现。
- [x] 执行`python scripts/run_fake_writer_tests.py tests/test_bookshelf_issues_http.py tests/test_web_command_dto.py tests/test_web_workspace_routes.py`和`node --test tests/test_bookshelf_ui.js tests/test_bookshelf_issues_ui.js tests/test_workspace_navigation_ui.js`，预期全绿。

任务5 P1已定向关闭；P2并发补修后，定向验证Python31（含project_issues）、Node19通过；1440/390取消、6个重载反例及390相同双POST真实临时迁移通过。交付范围、RED/GREEN、哈希、重启事实与待复审项见`docs/bookshelf-issue-actions-progress.md`。任务6仍未完成。

### 任务6：完整临时浏览器与交付

**Files:** 新增`scripts/validate_bookshelf_issues_ui.py`、`docs/bookshelf-issue-actions-v1.md`；执行进度单独记录`docs/bookshelf-issue-actions-progress.md`，不改历史迁移哈希清单。

- [x] 使用临时正常书、命名建议书、坏metadata、ID冲突、坏摘要/回执；Chromium1440/390完整查看→预览→确认→各真实阶段→结果→打开；取消、重复点击、刷新恢复、错误与焦点返回均实测。
- [x] 分别实测备份前后/moving后丢响应、显式核对/再次确认、旧默认根503与稳定ID入口可读、旧Runtime写被拒绝；断言所有项目ID和字节保持、备份已验证、零模型、仅允许命令POST。
- [x] guard运行本轮新增全部Python及任务3列出的受影响旧测试；Node相关行为；原书架及目录身份浏览器回归。新改动/失败才扩大重跑；禁止用真实三书作写入验收。
- [x] 按spec逐条检查、对照截图，交总控独立审查；阻塞先失败用例再最小修复。报告实际测试/跳过/限制、临时备份路径、SHA256、未完成项，不将离线结果冒充正式加载。

任务6完整8场双宽度矩阵、guard Python260、Node35及原书架/身份浏览器回归通过。新增两项状态文案RED/GREEN修复，未改任务5后端审计实现。交付`docs/bookshelf-issue-actions-v1.md`，等待总控独立最终验收，不部署/重启。浏览器除三个迁移命令，仅允许既有的显式最近记录POST；旧默认写409的负向探针另行记录。

## 计划审阅需确认的安全决策

1. **源外身份锁和旧路径保留禁用：建议采用。** 这是阻止旧实例/CLI重建原目录的必要边界；首版不允许复用已迁移的技术目录名，不提供解除墓碑操作。代价是同名英文旧目录暂不能创建新书，正常中文书名不受影响。
2. **启动默认作品迁后入口：建议采用任务4行为。** scoped稳定ID可打开；默认旧绑定明确503/409并显示需重载，由总控安排加载，不能自动重启。代价是服务重载前旧未绑定链接暂不可编辑。
3. **备份尚未验证的中断：建议采用任务4的可证明failed分支。** 仅原源完全未变、目标不存在、阶段未到moving时关闭失败并允许新预览；保留所有部分备份。任何不确定证据继续needs_reconciliation，不加万能修复。

## 自审与交接

覆盖核对：逐本异常/只读预览→任务1；原请求身份/幂等→任务2；活动写与旧路径→任务3；备份/中断/拒绝覆盖→任务4；界面/刷新→任务5；实际验收/审查→任务6。接口名称与状态在各任务保持一致，所有Review Focus均有对应失败测试。

当前只读研究并编写本计划，没有执行上述测试、改生产代码或操作真实三书。总控审阅计划及三个安全决策后，再安排同一负责人顺序实施；不自动进入开发、不自行分派战斗Agent。
