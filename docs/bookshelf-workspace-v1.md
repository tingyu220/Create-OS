# 作品书架与统一创作空间验收

状态：已完成。独立复审已确认本轮规格范围无未关闭阻塞，未加载正式服务。日期：2026-10-19。

## 交付行为

- `/` 为全局书架，读取真实作品目录与最近位置；支持搜索、分页、新建入口、空态与分区错误。没有最近记录时不借文件时间伪造记录。
- `/p/{id}/` 以最近位置优先；无记录时选择真实稿件或正式设定入口。同章有工作稿和正式稿时可显式切换，待确认候选可定位。
- Writer/Story共用作品切换与返回书架导航；完整项目URL隔离旧请求；未保存正文、候选、输入离开前提示，取消保留本地编辑，确认离开不隐式保存。
- Writer目录按真实标题/编号搜索，支持全部、工作稿、待确认筛选。桌面三栏，窄屏目录/对话/正文分面。
- 旧摘要完整保留在`/overview`及`/p/{id}/overview`，原`/writer`仍绑定启动默认作品；旧全局和显式项目章节锚点提供兼容链接。诊断保留次级入口。
- 最近记录仅显式POST写入projects根级`.creative_os/workspace-recent.json`，不改小说；UTC服务端时间，原子replace与工作区锁，损坏记录不静默覆盖。`source`可选，缺省auto。
- 目录不调用Registry.get，不装配Runtime；仅当前页读取摘要。损坏元数据隔离；单书摘要异常保留入口并显示partial及未知数量，正常作品继续可见。

## 验证证据

- `scripts/validate_bookshelf_ui.py`：1440×1000与390×844，真实临时三书起步；书架→工作/正式稿→候选→切书Story→未保存离开取消/确认→返回书架→新书创建→搜索发现。故障验收再加入坏会话条目。
- 同脚本覆盖：GET文件内容/mtime不变；真实最近记录及刷新；项目哨兵隔离；Writer/Story未保存保护；显式旧锚点；坏会话不隐藏健康书；章节失败不写最近；最近POST失败不阻断编辑；目录失败保留最近；空书架；长标题；无页面错误、零模型调用。
- `scripts/validate_author_home_ui.py`：迁移后旧摘要1440/390通过，保留真实统计/筛选/章节跳转/故障独立性，显式draft/formal/auto语义通过，临时目录内容/mtime不变，零模型与生产Runtime。
- `node --test tests/test_*ui.js`：64项通过，覆盖保存作用域、来源、Story、导航、迟到响应和离开保护。
- 相关完整Python回归：456项通过、1项Windows符号链接权限不足跳过，日志`.backup/bookshelf-related-final.log`。该轮包含坏会话、候选定位与对账语义，发生在最后一次CommandStoreError补丁之前，不宣称是最终补丁后全套结果。
- 最后一次回执损坏补丁后：直接查询、目录、HTTP、最近记录、Writer摘要目标集合45通过、1权限跳过，日志`.backup/bookshelf-receipt-fix.log`。书架及旧摘要1440/390浏览器均重新通过；Node64项所测前端源码未再变化。
- 浏览器报告及截图：`.backup/bookshelf-ui/report.json`、`shelf-{1440,390}.png`、`writer-{1440,390}.png`、`story-{1440,390}.png`、`shelf-empty-*`、`catalog-error-*`、`chapter-error-*`、`partial-summary-*`。
- 日志：`.backup/bookshelf-related-regression.log`、`.backup/bookshelf-audit-fix.log`、`.backup/bookshelf-node.log`、`.backup/bookshelf-browser.log`、`.backup/author-home-migration.log`。

## 扩展回归限制

完整`python scripts/run_fake_writer_tests.py tests`结果为1759通过、9跳过、6失败。这不记为全项目通过：

1. `test_inspect_pov_strategy_script.py::test_inspect_script_exposes_no_write_mode`：Windows父进程GBK解码UTF-8子进程输出失败；同guard下设置`PYTHONUTF8=1`重跑，1项通过，无需修改业务源码。
2. `test_llm_writer.py`的`test_openai_compatible_client_reads_env`、`test_openai_compatible_client_reads_configurable_timeout`、`test_openai_compatible_client_requires_api_key`、`test_openai_compatible_client_reads_dotenv_file`、`test_openai_compatible_client_prefers_process_env_over_dotenv`：测试主动调用`OpenAICompatibleClient.from_env`，被本次强制guard以`fake_validation_real_client_forbidden`拦截。未放松保护或构造真实客户端，不宣称这些测试通过。

## 修复与边界

- 浏览器暴露候选入口auto会打开正式稿：新增失败测试后改为按真实工作/正式稿选择默认来源。
- 窄屏正文读取失败原来停留“正在读取”：失败测试后在正文分面显示错误。
- 版本读取慢响应原来抢回作者已切换分面：延迟响应失败测试后，成功正文读取即完成分面切换，版本结果不再触发切换。
- 独立审查发现坏会话jobs数组导致目录断连：先复现9项失败；校验jobs结构、单书摘要错误隔离；故障不修复磁盘，不将未知数量报零。独立稿件源可读时仍保留真实统计。
- 独立审查发现待确认目录会打开较新的已处理历史：3项Node失败后筛选pending/reviewing及既有review_recovery.required；终态仍需对账时复用已有public纯查询计入待确认。浏览器同章原pending与较新accepted/rejected/cancelled、终态待对账分别在两种宽度验证，不执行对账或重复审阅。
- 新增public查询依赖的命令回执损坏会抛领域CommandStoreError：直接查询、HTTP、目录兜底3项失败后，显式捕获该类型，候选统计为未知，独立正式/工作稿统计仍保留。未吞全部RuntimeError、未重构Proposal；浏览器真实损坏results.json与健康书并存通过，GET文件内容/mtime不变。
- 下拉列表限制首20本，当前作品始终显示；更多作品从书架搜索分页选择。
- 未删除文件、未清理共享工作区、未commit/push/merge；未启动或重启8877，未加载正式服务。已有共享未提交修改保留。后续正式加载需用户另行授权。

源码快照见`docs/bookshelf-workspace-sha256.md`；执行裁决完整记录见`docs/bookshelf-workspace-progress.md`。

## 独立复审结论

审计会话`01a13f91-a6c4-72e3-bf0a-bfcb8ee2c457`独立复现并复验关闭坏会话、候选历史抢占、损坏回执三项P2；最后14项定向测试及终态待对账1440/390验证通过，37文件清单逐项哈希一致。审计结论：本轮规格范围内无未关闭阻塞。未重新开放旧Proposal业务范围，也未操作真实作品或正式服务。
