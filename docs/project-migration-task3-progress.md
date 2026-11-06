# 任务3：并发写门禁 — 2026-10-24

DONE：任务3实现和临时项目回归完成，待独立复审。
CURRENT：已具备外置稳定ID写租约、工作区创建租约、非阻塞迁移租约、旧路径拒绝、活动证据检查、Runtime Future跟踪及空闲缓存失效接口。
TODO：独立复审；任务4实际备份/移动/核对及任务5 HTTP/UI均尚未启动。

## 独立复审P2修复：initializing目录大小写别名

复现：临时old目录稳定ID为stable，完整new-books initializing记录folder为OLD或Old，directory_identity为同一源目录设备号/inode；Windows samefile为True。原migration_lease及Registry.assert_migration_idle均错误放行，folder=old对照拒绝。

最小生产修改：project_migration_activity.py的初始化意图匹配由字符串相等改为folder.casefold()==source.name.casefold()，与现有稳定目录/旧路径规则一致。形状验证、未知状态拒绝、核对租约等其他代码未改。

新增tests/test_project_migration_activity.py，不创建Runtime、不调用模型：2入口×3种源大小写形式，以及2入口×非关联OTHER目录，共8场景。RED：4 failed / 4 passed，4处失败均为大小写别名被放行；GREEN：原任务3五文件111项加新增8项，共119 passed，49.44秒。

```text
python scripts/run_fake_writer_tests.py tests/test_project_migration_activity.py tests/test_project_migration_concurrency.py tests/test_project_authority_transaction.py tests/test_writer_draft_store.py tests/test_story_review_fixes.py tests/test_agent_proposal_reconcile_http.py
```

本轮源码SHA256（替代下方首次交付快照中同名文件哈希）：

- creative_os/project_migration_activity.py：65d682423477c1bf5fb9a6c7062c804ab0785188bacc47cfa5f64351c8779360
- tests/test_project_migration_activity.py：845818861af8caa33ca6c5eabb6dcb037357a7b451240cae53656f80fb456ce8

CURRENT：P2修复待定向复审；任务4仍未实施。未操作真实三书、8877或Git。

## 修改范围

- 新增creative_os/project_write_gate.py：线程RLock与系统字节锁组合，同线程重入；普通写先取得外置身份锁，再进入原项目权威锁/回执内部锁。迁移只持工作区外置锁及稳定ID外置锁，不打开源内权威锁文件。迁移忙立即抛project_migration_busy。
- 新增creative_os/project_migration_activity.py：纯读持久会话、命令回执、新书意图；活动任务、RESERVED回执、相关initializing、损坏JSON/形状、未知状态均拒绝。模块不导入Runtime或CommandBoundary。
- 修改domains/project_authority.py、workspace_command.py：项目权威锁外包身份租约；回执仅reserve/complete/release加门禁，构造/read仍只读。
- 修改novel_project_command.py：创建先取得工作区租约，在创建意图或目录前检查旧路径禁用。
- 修改project_registry.py：assert_migration_idle只检查持久证据和已有缓存；invalidate_after_migration拒绝活动任务，只失效空闲缓存，不取消任务。
- 修改agent_runtime.py：队列提交与任务/Future登记位于同一身份锁内；即便job已terminal，只要Future未done仍拒绝迁移。后台decision保存进入项目权威锁。
- 修改agent_conversation_store.py、agent_proposal_store.py：直接write也取得身份租约，防止绕过调用方的权威锁。
- 修改project_migration_store.py：增加无副作用read_operations，提供旧源反查，不修改任务2记录语义。
- 新增tests/test_project_migration_concurrency.py：53个临时项目场景。

## RED / GREEN

1. 首轮因缺少gate模块收集失败；有基础gate后得到13 failed / 7 passed，失败实证为原写入口未互斥、旧路径被重建、Registry缺检查接口。
2. 补Runtime/直接write用例得到7 failed / 28 passed；补后台decision入口得到2个预期失败；分别实现后通过。
3. 大小写别名旧路径用例2 failed后修复为2 passed；未知会话目录形状、残缺completed回执2 failed后修复。
4. 第一轮扩大验证1 failed / 282 passed / 1 skipped：等待写方测试屏障只到“线程启动”，与短暂metadata读句柄竞争，分别出现project_metadata_invalid及Windows rename WinError 5。将屏障移至写方已完成身份读取、正要取得真实外置锁的位置，单项通过。生产门禁未为通过测试而放松拒绝。
5. 最终扩大guard集：288 passed, 1 skipped，72.50秒。跳过项为tests/test_project_catalog.py中当前账户无法创建符号链接的场景。

最终命令（包含计划要求的全部5个文件及相邻回归）：

```text
python scripts/run_fake_writer_tests.py tests/test_project_migration_concurrency.py tests/test_project_authority_transaction.py tests/test_writer_draft_store.py tests/test_story_review_fixes.py tests/test_agent_proposal_reconcile_http.py tests/test_project_directory_identity.py tests/test_project_migration_store.py tests/test_project_migration_command.py tests/test_web_command_dto.py tests/test_author_home_query.py tests/test_project_catalog.py tests/test_project_catalog_http.py tests/test_workspace_command_adapter.py tests/test_novel_project.py tests/test_new_book_project_layout.py tests/test_agent_conversation.py tests/test_agent_proposal.py tests/test_writer_lessons.py tests/test_story_architecture.py tests/test_story_agent.py
```

## 并发证据

- 真线程及spawn子进程持有普通写锁时，迁移立即拒绝；迁移持锁时另一个spawn进程不能创建源内目录或保存，释放后才完成。
- 保存、发布、回执reserve/complete/release、Story确认、Proposal审阅/核对、Lesson、Agent提交/更新、会话/提案/decision直接写入均在迁移持锁时等待，释放后实际完成；同时另一书可保存。
- 创建与迁移共享工作区锁，测试覆盖初始化阻止迁移、迁移阻止新书意图落盘两个方向。
- 等待写方取得身份锁后复查旧路径；测试租约内rename及记录后，写方拒绝，旧目录不重建；替换metadata和Windows大小写别名也拒绝。
- 注册缓存的queued任务、真实排队/运行Future、未知Future、job已结束但真实Future仍收尾均拒绝迁移；检查不调用Registry.get，不取消任务。
- Registry只读get、Story查询、回执constructor/read及目录可用性查询前后路径、内容、mtime一致；无metadata的独立领域测试根继续可写。

## Rulings与限制

- Ruling：按用户要求复用当前共享工作区与docs进度账，不创建另一checkout、不提交；避免丢失既有未提交模块。
- Ruling：身份锁哈希和旧路径比较使用casefold，与现有稳定身份扫描规则一致，防止Windows目录大小写别名绕过；在大小写敏感系统上也保守禁止这些别名复用。
- Ruling：活动检查独立为project_migration_activity.py，避免gate循环导入命令/Runtime，并控制文件职责。
- 调用方须在migration_lease内调用Registry.assert_migration_idle后才开始任务4副作用，并在同一租约内按证据失效缓存。仅有租约不代表缓存已检查。
- 本任务返回领域忙错误；HTTP 409等响应映射留给任务5。
- 不承诺Windows所有rename必定成功：并发读取metadata或其他文件的短暂非共享删除句柄可能导致WinError 5。任务4必须保留备份和操作身份并按失败/需核对状态处理，不能因本任务测试通过而跳过rename失败路径。
- 尚无真实备份/移动服务、完整中断状态机或HTTP/UI端到端验证。本轮测试仅临时项目/Fake；未写真实三书、未重启8877、未commit/push/merge。

## SHA256

| 文件 | SHA256 |
| --- | --- |
| creative_os/project_write_gate.py | 1c88e1e83b9c6e4c0540ea3b24c895028edeb5816860f4423754e4d04e90666f |
| creative_os/project_migration_activity.py | 0d1ec392aed332794c2b486643a5136b302ae1dbea0d94387e042d8dbe440660 |
| creative_os/domains/project_authority.py | 1cddeb31d5a11e9a2be1162d3ffb310fb50eaf028529dcbad30ff856fb96e7e3 |
| creative_os/workspace_command.py | b42f9c4869c0b8503aea09e7f208b654b6226974f3607f0d0b43898e470c1ccb |
| creative_os/novel_project_command.py | 798dc7e608f9c6e0463092e6a950ef3e05b9d210b2eba47ef01f86d45ebb362d |
| creative_os/project_registry.py | e6c6daa114a5d337149348bfed17d1803ae82ffffaeef6834cad36e4d1bf80b3 |
| creative_os/agent_runtime.py | 2c3d6f8909bf47a233266237034a9a22a33afcab510a7ee0de4c4d25beac6f2d |
| creative_os/agent_conversation_store.py | dd633c8753fd06eb847cccf551e51e0dc4242957b746eb7d70c48571c792a2a7 |
| creative_os/agent_proposal_store.py | 5390b81a95c55883a29f3de04ea56cb680003d9266001e8bd622549a321e1ce2 |
| creative_os/project_migration_store.py | e5b95004891e130d7cf915b38bcdc2f01d44189ce92bcaad733a1a046830db06 |
| tests/test_project_migration_concurrency.py | 61eb251aa3090dedbb9ed4af04260042e245f2901a002e609169882f84a17964 |
