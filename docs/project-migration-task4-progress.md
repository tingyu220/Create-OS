# 任务4交付记录 — 2026-10-24

DONE：任务3及其initializing大小写P2修复已通过独立复审；任务4的迁移服务、证据/命令契约补齐、真实临时文件迁移和中断回归已完成。
CURRENT：源码进入任务4独立复审；最终guard为407 passed、1 skipped，128.96秒。
TODO：独立复审后再进入任务5；尚无真实HTTP/UI迁移入口，不操作8877。

## 实现及入口

- ProjectMigrationService位于creative_os/project_migration.py。构造参数沿用计划的projects_root、backup_root、registry、default_project_id/default_root；备份根严格为工作区`.backup/project-directory-migrations`，在projects之外。
- 实际写入口为`service.commands.execute(CommandRequest)`，返回既有CommandResult。`service.execute(request, trace_id)`是边界内部领域处理器，要求当前线程持有匹配租约且操作已由边界认领，不能直接调用绕过reserve或互斥。
- project_migration_boundary.py复用CommandBoundary的reserve/complete及原RESERVED拒绝自动重跑语义，不覆写通用_reservation_result。初始意图先落盘；原规范化请求、包含actor的指纹、trace及结果模板绑定原操作。核对/继续具有独立回执；成功核对只补原迁移回执，不制造原请求的新trace。
- project_migration_contract.py及web_command_dto.py按批准表统一为migrate_project_directory/reconcile_project_directory/continue_project_directory，严格target/payload、confirmed必须True、固定幂等键、UUID和小写SHA。废弃旧DTO命令别名；未新增HTTP路由。
- project_migration_schema.py及Store采用版本2证据记录；读取兼容版本1，GET不升级/补写；版本2首次写聚合时保留全部旧记录。缺少版本2证据的旧操作不能授权移动，坏记录及不一致路径/指纹/检查点拒绝，不用空聚合覆盖。
- Preview现在使用随机UUID、内存随机签名密钥、600秒TTL；完整计划包含工作区/源文件系统身份、metadata字节SHA、完整相对清单哈希及目标空缺。重启拒绝尚未执行的旧token；已有操作的相同请求按原回执重放，不因过期重做。
- inventory提供完整隐藏文件/空目录清单、SHA校验、独占创建备份及Windows原子拒绝已有目标的同根rename；拒绝symlink/junction/reparse及文件硬链接。manifest在操作容器中旁置，不能混入project副本。非Windows移动原语明确拒绝，不退化为覆盖。
- project_migration_evidence.py和project_migration_recovery.py分别负责受限根证据及显式分类，不另造Runtime/事务系统。首次迁移必须唯一稳定ID；已持久操作的核对使用operation_migration_lease后再有界检查双存/双失，不放松初次校验。
- Registry增加仅检查已有缓存的方法；持久任务、真实Future及缓存失效均在同一租约内检查。测试只使用Fake缓存/真实Future，不创建生产Runtime。
- 记录存储随机临时文件使用独占创建，避免固定.tmp链接改写其他数据；记录锁复用现有系统文件锁，进程退出释放真实所有权，锁文件保留且不删除，不凭PID或文件存在猜测所有者。通用RESERVED与业务幂等语义未改。

## RED / GREEN证据

1. 先创建服务/原子移动/中断测试；初轮缺rename_no_replace及服务模块，2个收集错误。
2. 直接调用领域handler可绕过边界的回归1 failed，增加当前租约和操作认领检查后通过。
3. 继续/核对中断回放8 failed（旧POST会重复创建/删除记录锁改变目录mtime），改为只读返回既有回执；再次明确核对跳过已存在回执的旧继续编号。对应10场景通过。
4. 固定.tmp为硬链接时两个Store会截断关联临时哨兵文件：2 failed；改随机名+独占创建后2 passed。
5. 真子进程在原子替换前/后退出留下占位锁，操作及回执两个Store均永久busy：4 failed；改复用系统锁后恢复。原workspace_boundary四项旧“文件存在等于忙/释放必删除”的断言不再符合协议，已改为真实线程持锁、释放后可继续、冲突后不挂锁等行为校验；46项定向通过。
6. 非法UUID暴露库异常字符串：1 failed；改稳定领域错误码后通过。
7. 最终扩大guard：407 passed, 1 skipped，128.96秒。唯一跳过为test_project_catalog.py中当前账户无符号链接权限的既有用例；Windows junction、硬链接及真实进程退出用例均实际运行。

最终命令：

```text
python scripts/run_fake_writer_tests.py tests/test_project_migration.py tests/test_project_migration_reconcile.py tests/test_project_directory_identity.py tests/test_migration_atomic_evidence.py tests/test_project_migration_activity.py tests/test_project_migration_concurrency.py tests/test_project_migration_preview.py tests/test_project_migration_store.py tests/test_project_migration_command.py tests/test_web_command_dto.py tests/test_project_authority_transaction.py tests/test_writer_draft_store.py tests/test_story_review_fixes.py tests/test_agent_proposal_reconcile_http.py tests/test_author_home_query.py tests/test_project_catalog.py tests/test_project_catalog_http.py tests/test_workspace_boundary.py tests/test_workspace_command_adapter.py tests/test_novel_project.py tests/test_new_book_project_layout.py tests/test_agent_conversation.py tests/test_agent_proposal.py tests/test_writer_lessons.py tests/test_story_architecture.py tests/test_story_agent.py
```

## 中断矩阵

| 分组 | 实际覆盖 | 核对后的允许结果 |
| --- | --- | --- |
| 首次迁移16点 | intent前后、命令reserve前后、backing_up前后、backup_verified前后、moving前后、rename前后、verified前后、原complete前后 | 无意图则无操作；源未动且无已验证备份可明确failed；源+完整备份可等待新确认；仅目标且证据一致可verified并补原回执 |
| 继续5点 | reserve后、moving后、rename后、complete前后 | 原RESERVED不执行；再次明确核对后使用新编号，或核对为verified |
| 核对3点 | reserve后、backup_verified前后 | 原核对RESERVED不执行；另一明确核对请求才重新分类，不自动移动 |
| 失败/未知4点 | failed前后、needs_reconciliation前后 | 保留源/部分备份/竞争目标，不覆盖、不回填 |
| 真进程退出2点 | moving落盘后、rename完成后，子进程os._exit | 系统租约释放，重启GET/重复原POST不执行；明确核对后再确认继续或补verified |
| Store真进程退出4点 | 操作聚合及命令回执各在原子replace前/后os._exit | 只见旧或新完整聚合，遗留临时文件保留；不产生幽灵所有者，后续合法写可取得系统锁 |

另外验证：目标在移动前最后一刻出现、Windows占用导致rename失败、复制/校验失败、源内容/metadata/身份变化、备份变化、双存/双失、损坏metadata、无核对的继续、作者/项目/指纹篡改、隐藏文件/空目录、重复重放、partial备份保留后新UUID操作、尚未执行token过期/重启失效、中文简称不支持，以及Fake缓存Future阻止/允许后失效。

## Rulings与限制

- Ruling：以已批准HTTP表取代旧DTO命名和载荷，已有低层旧意图记录保留，但无完整证据不授权移动；与旧未部署DTO调用方不兼容，任务5只应使用新表。
- Ruling：备份证据、状态核对、命令契约拆为职责单一模块，继续使用原Store/Boundary/Gate，不新增创作Runtime或第二套事务系统。
- Ruling：显式核对遇到已保留的旧继续编号时生成更大的未使用编号；不解除旧RESERVED、不复用旧请求偷偷执行。
- Ruling：记录层占位文件锁改为复用既有系统锁，是覆盖真实进程退出窗口所必需；不删除锁文件。部署须使用一致版本的写入方，不能将旧版本仅靠占位文件判断所有权的活跃进程视为受新协议保护。
- 仅真正验证目标、备份和原ID一致后返回accepted；源有/目标无且备份一致只返回需明确确认，未当作成功。双存/双失/不匹配停在需核对，不自动移动、删除、回填或重试。
- 原complete中断可由明确核对按原trace/模板补齐；中断的继续/核对命令本身仍保留其原RESERVED，不伪造该请求的历史执行结果。
- `status`只读；`availability(project_id, root, writable=...)`提供旧默认根读取503/写入409及reload_required信息。按本轮授权未接HTTP，任务5必须在真实数据入口调用它；当前不能宣称浏览器端到端迁移已经可用。
- Windows短暂读句柄或外部目标竞争仍可使rename失败；本任务保留现场并通过明确核对分类，不能保证所有Windows目录都可无阻移动。非Windows不提供原子移动降级。
- 测试不等同于断电、磁盘硬件故障或任意外部进程篡改下的完整可靠性证明；临时文件和部分备份保留，不自动清理证据。
- 本轮仅guard临时项目和Fake回归，未写真实三书，未调用付费模型/生产Runtime，未重启8877，未commit/push/merge。

## SHA256（任务4最终源码快照）

| 文件 | SHA256 |
| --- | --- |
| creative_os/project_migration.py | 19a7edafd610a4fb15f9d728a9309cadfdfe1f8f524aa9ab74111cf6fed3183a |
| creative_os/project_migration_boundary.py | ce2ea68612ad4f6e761ba064ad4177cb8ea3989a6fc89c98cb916a0eb58bc0be |
| creative_os/project_migration_contract.py | 204ad86432f6e84eb18fb7d8e0539a422553d53cf8e18d00b4eaea000f56ecc2 |
| creative_os/project_migration_evidence.py | a0a13df32793b63559d3f706137a7b6105afaf67a7a1acd4eba1353c3b1e96b1 |
| creative_os/project_migration_recovery.py | 8d4f71f04bbc548d8f60623283518431b1169ec1a4fa9ebb3cec8a6e8b9df92e |
| creative_os/project_migration_schema.py | 4321906663d52ec9994a8447dabc2ec2b741f94d8fb9035d8b9e8c2b456453dc |
| creative_os/project_migration_store.py | f0f4dc7cc5a1616f85fefd2ba01724ba17962c3fd4909b5a8763993aa191f290 |
| creative_os/project_migration_preview.py | fa8f72f3afba9ef0c4707e0b4cb6b720c95e32aad85fe0eea33fd053ad2ce647 |
| creative_os/project_directory_inventory.py | 509bfac63f4c225ce84ffd45e8aa90d28c6eed436135f1c7e1e2c6966c21c7f2 |
| creative_os/project_write_gate.py | e112e1d550175508b321b60359cef23943b83446a90e9ec9b92939f72f0da6af |
| creative_os/project_registry.py | c7a8aa4193ce00e6c1351e7cdce9ef0f204264b9474216944c2be6567b9026a7 |
| creative_os/workspace_command.py | d548fcb9b77405e80523df3c13eb77b028a10234a270121ae30cffba9734ad08 |
| creative_os/web_command_dto.py | a994764ae6ab40e528174fbdf0844d91ec916c4ff12dc958b421bf6b34d230ad |
| tests/test_project_migration.py | dd47cb379e92fd753974233f26c73d5b86928b5765bdd28c80220abc44ff338c |
| tests/test_project_migration_reconcile.py | c944c92c82806596a276cac53fcc92265b35094d5e66e37eccb7448030da483e |
| tests/test_migration_atomic_evidence.py | 7469ff433270f8f992777582e3614dfda930e4e8041c091b3033b323ec0af893 |
| tests/test_project_migration_command.py | f53fa95225d71a4e6a6913cd7e5f655ff8352bf505fd24c38ba353558102aad4 |
| tests/test_workspace_boundary.py | ea5f1bafa8b9d887bf750b32171c1faa43663191ca841d153e03192021b38c13 |
