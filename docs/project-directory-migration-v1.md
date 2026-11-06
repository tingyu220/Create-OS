# 中文作品目录与稳定ID迁移交付

日期：2026-10-20。状态：目录迁移及身份兼容已完成；8877新代码加载、追加可视化功能待处理。

## 实际结果

| 迁移前 | 迁移后 | 稳定project.json.id | 文件数 | 子目录数 |
|---|---|---|---:|---:|
| `projects/validation_novel` | `projects/雾城回声` | `novel-validation-001` | 2321 | 795 |
| `projects/novel_domain_validation` | `projects/末班钟表店` | `novel-domain-validation` | 5 | 3 |

旧目录已不存在，新目录全部文件字节、长度和文件mtime与迁移前及完整备份一致，空目录集合保留。metadata.name未改：第二本仍为“末班钟表店独立验证项目”，仅目录按用户要求为“末班钟表店”。稳定ID、正文和历史身份均未改；`projects/文明升阶`保持原路径与ID。

## 备份与哈希

完整备份根：`D:/田雨/Creative OS/.backup/project-directory-migration-20261020-160349`。

两个原目录分别完整备份在该根的`validation_novel/`及`novel_domain_validation/`。同根两个`*.manifest.json`保存逐文件SHA256、长度、mtime和所有子目录；两个备份全部校验通过后才执行Move-Item。移动前再次核对源清单、活动任务、待核对回执和目标空缺，移动后再次核对。

| 作品 | 原目录＝完整备份＝迁后目录的清单SHA256 | project.json SHA256（前后相同） |
|---|---|---|
| 雾城回声 | `87cc2cdbf3828f2ab18243748e5317dd2e66fab5f3cd181fa0fb6800722533cd` | `56ea1656087a40fe3034ac7e7a04f2a06416e56084474fba8fdf2f463cd0d272` |
| 末班钟表店 | `7f35bcb3d71923dcb31a7917b58779247e70c7000b8ed253e75561fa487e82fb` | `92afd6f79ce893e4b822b68a8b5285992c590d01b23395541718f00607b2e323` |

执行结果：`.backup/project-directory-migration-execution.json`。没有覆盖或删除已有目标，没有删除备份，没有自动回滚或修复历史数据。

## 兼容实现与调用链

- 新增`project_directory.py`，纯元数据建立稳定ID→安全直接子目录映射。拒绝非法ID、符号链接／junction越界、metadata链接／超大文件、大小写重复ID、目录别名占用另一ID；异常项目不隐藏正常书。
- Catalog使用metadata.id返回作品入口、搜索与摘要作用域；分页仍只读取当前页摘要，不构造Runtime。
- Registry.get/register经同一映射定位。已有Runtime根已移动时明确要求重启，不静默复用旧路径；不自动恢复创作任务。
- 最近记录继续保存稳定ID，不需要改旧记录；scoped URL仍为`/p/novel-validation-001/`和`/p/novel-domain-validation/`。目录名不作为第二身份或旧目录别名。
- 创建命令检查全目录稳定ID占用后才创建；新书仍为`projects/<书名>`。创建HTTP响应从已校验metadata.id构造会话身份，避免返回物理目录名。
- `novel_web_workspace.py`已经从FilesystemProjectSource取得project_id并显式传Runtime，启动链无需改写；不会拿中文目录名替换稳定ID。
- 更新当前README、roadmap、状态记录、pilot默认路径和四处依赖真实fixture路径的测试常量；资源路径在迁后已确认存在。历史计划、临时测试中的旧示例ID、作品内部历史路径文本保留，不重写原作品文件。

## 验证证据

- 身份TDD首先7失败、1已有拒绝通过；修后相关回归：121通过、1符号链接权限跳过。日志`.backup/project-directory-regression.log`。
- 补充非法／大小写重复ID和受控迁移安全集：22通过，日志`.backup/project-directory-safety.log`。迁移脚本独立先RED，再4通过，覆盖完整备份/哈希/空目录/整体移动，以及目标占用、活动任务、稳定ID不符时在备份或移动前拒绝。
- guard临时三书HTTP：Catalog、默认Writer与显式作用域、三份隔离正文、Registry.register、移动后缓存拒绝、recent、创建响应均验证，读请求文件／目录／内容mtime不变；拒绝真实客户端构造。
- `validate_project_directory_identity_ui.py`：Chromium1440×1000和390×844真实走书架、三书按稳定ID打开、目录切换、recent刷新，零模型、无页面错误、无横向溢出、三书文件／目录／字节mtime不变。报告与截图`.backup/project-directory-ui/`，均已查看。
- 实际迁后只读身份核对：中文目录分别解析为两个原稳定ID；加禁止Registry.get的检查，新代码离线Catalog返回3书、0警告、生产Runtime实例0。未用真实作品进行创作／写入测试。
- 现有fixture路径仅检查迁后存在，未运行以真实作品为输入的写作测试；没有真实模型调用、Commit、Push或Merge。

## 未完成与界限

1. 正式8877仍是PID22920旧后端，未停止或重启；实际GET仍返回1书、2警告。离线新代码与临时浏览器通过不能表述为8877已显示三书。加载新代码由总控／用户另行决定。
2. 用户追加“查看并处理”可视化功能已形成短设计和书面规格：`docs/superpowers/specs/2026-10-20-bookshelf-issue-actions-design.md`。包含异常详情／重新检查与有界目录整理、全清单指纹、活动写互斥、备份校验、幂等和中断核对协议；新增持久命令需先批准书面规格，当前未实现该写命令或界面。
3. 当前一次性脚本只对应这两本已授权目录；不是可公开执行的通用迁移服务，不能把它当作未来UI的事务与恢复协议。

本轮源码／测试／当前引用快照见`docs/project-directory-migration-sha256.md`；保留全部共享未提交修改。
