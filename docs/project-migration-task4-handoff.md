# 任务4只读交接 — 2026-10-24

DONE：只读检查计划、规格及现有预览/记录/命令/租约接入点。
CURRENT：任务3源码冻结，等待独立审计；本记录不代表任务4已经实施。
TODO：收到任务4指令后先以回归测试统一以下契约，再实施备份、原子移动和中断核对。

## 接口偏差及阻塞

1. 命令契约不一致。计划HTTP表使用migrate_project_directory/reconcile_project_directory/continue_project_directory，现DTO为start_project_migration/reconcile_project_migration/continue_project_migration，target/payload也不同。后者缺preview_token、confirmed和服务端固定幂等键的契约。任务4/5不能直接把现DTO当作计划中的成品。
2. 操作聚合缺证据字段。当前Store严格拒绝未知字段，只允许目录、ID、指纹、阶段、continuation_no、reason及可选actor；尚无原请求/trace/结果模板、清单哈希、已验证备份证据及所有者。需要受控schema演进，不能在旁处另造互不原子的索引，也不能丢失已有记录或将坏记录当空。
3. continue_operation目前只检查编号为上次+1，然后直接置backup_verified。它不是“已经核对过备份”的凭证，不能在任务4作为移动许可。编号应由明确核对的证据产生，执行只消费该编号；重复编号不再移动。
4. 当前预览的指纹只有稳定ID、源名、目标名、相对清单哈希及目标空缺；缺工作区/源文件系统身份。operation_id由指纹确定，非计划要求的UUID；backup_root配置未参与预览输出。任务4需先补身份变化、UUID操作身份、不可变备份位置的验证，不因现有少量测试通过而跳过。
5. build_inventory已有文件SHA及空目录集合，但尚无copy_verified/rename_no_replace；链接检查只有is_symlink，未显式拒绝Windows junction。备份需完整隐藏内容，manifest为同备份容器的旁置文件，不能混入project副本。
6. 核对租约接入存在缺口。migration_lease当前必须validated_project找到唯一存在目录并检查该目录活动证据后才能yield；双存/重复ID、双失、metadata损坏等恰是明确核对需记录needs_reconciliation的分支，不能靠此入口进入。任务4需增加按已验证持久操作稳定ID取工作区/外置身份锁的核对入口，再有界检查源/目标/备份；不能放松首次迁移的唯一ID及活动状态检查。该改动须等任务3审计快照解除冻结。

以上为源码与既定计划的实际差异，本次只报告，不变更已审模块，也不擅自改规格。

## 预期接入顺序

- 新操作：服务端路径与确认校验→取得工作区/稳定ID租约→Registry.assert_migration_idle→重新验证完整预览→持久原意图→通用命令reserve→backing_up→完整备份及校验→backup_verified→源/目标末次复核→moving落盘→原子拒绝覆盖rename→目标/备份/ID复验→verified及原结果模板→补原complete→同租约内失效闲置缓存。
- 既有操作重复POST：安全读取完整聚合→绑定作者/原身份→返回已有结果或未知结果；不得因token过期、重启、源已移动或原RESERVED而重新备份/移动。
- GET status：只投影已存状态及需明确核对提示；不写锁、不补记录、不创建Runtime、不恢复或移动。

## Windows移动与中断

- Windows使用明确拒绝目标已存在、同卷的原生目录移动；可选MoveFileExW(flags=0)，禁止REPLACE_EXISTING/COPY_ALLOWED，不接受先exists再用可能覆盖的跨平台降级。非Windows缺少等价原子拒绝覆盖原语时拒绝动作。
- 在原生移动调用前落moving；在调用后重新看实际源/目标及清单，不能从异常字符串或一次返回值推断最终结果。WinError 5可能来自短暂metadata/正文读句柄；不能杀任务、删除目标、覆盖或反复盲试。
- 备份失败/部分复制保留现场。只有尚未进入moving、源完全匹配原预览且目标缺失时，明确核对可终止failed，保留部分备份并允许另一个新操作。
- 源有/目标无且源和已验证备份一致：核对为backup_verified，产生当前继续编号，等待再次明确确认；源无/目标有且目标与原备份/ID一致：verified并按原身份补回执。
- 双存、双失、身份/清单/备份证据不匹配：needs_reconciliation；不搬、不覆盖、不回填，不把备份存在当成已验证备份。
- 中断注入覆盖每阶段记录前后、通用reserve前后、rename前后、verified前后、原complete前后；每次验证真实文件和回执，不只断言mock次数。

## 下一轮验证边界

仅guard临时项目、Fake及原生临时目录移动；不写真实三书，不操作8877，不调用真实模型，不提交/推送/合并。默认旧根的503/409和HTTP/UI接入留待任务5，当前不能宣称端到端迁移已经安全可用。
