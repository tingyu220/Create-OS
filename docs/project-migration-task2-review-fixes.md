# 任务2审计修复 — 2026-10-24

DONE：reserve 通过当前工作区的 validated_project 解析稳定ID，并核对 source_directory；未知ID或其他作品目录在持久化前拒绝。聚合读取绑定字典键与记录 operation_id，错配时读取和后续写入均拒绝，保留原文件。

RED：新增两条回归测试，其中身份映射测试含两个参数场景；guard 输出 3 failed, 6 passed，全部失败均为缺少预期拒绝。

GREEN：原21项与新增3场景合计24 passed（0.21秒），命令：python scripts/run_fake_writer_tests.py tests/test_project_migration_store.py tests/test_project_migration_command.py tests/test_web_command_dto.py。

源码SHA256：

- creative_os/project_migration_command.py：489ef4845d6719962cc3b9de3de032ecaa9e6eebb122996197634aec3fe1b9a2
- creative_os/project_migration_store.py：8f34b1639723f8bed69b0cae20a691987ef06ee4e832cada31e54015bb731a12

CURRENT：两项审计缺陷修复完成，等待原反例复审。

TODO：任务3尚未推进。本轮仅运行临时项目guard测试，未操作真实三书或8877，未提交、推送或合并。

## 改名后重放回归修复

reserve 先安全读取聚合并校验既有操作的 actor、project_id、源目录、目标目录及原指纹。完全相同的重放返回原记录，聚合字节不变；首次登记才使用当前稳定ID映射核对源目录。损坏聚合仍在重放前拒绝。

RED：6 failed, 25 passed；原请求改名后被错误拒绝，5种身份变更未进入正确冲突分支。GREEN：同一guard命令31 passed（0.28秒），包含原24项及新增7场景；测试包含改名后跨实例重放、5类身份篡改及损坏聚合拒绝。

更新源码SHA256（creative_os/project_migration_command.py）：ef406ba6a54b799be0d20862a8b65eed9d2045ecfb2dafe80b57b92e3b523bf6。
