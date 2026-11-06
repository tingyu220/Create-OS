# SDD ledger — plan: docs/superpowers/plans/2026-10-19-bookshelf-workspace.md

DONE：任务1至4及任务5验收完成；书架和旧摘要1440/390浏览器通过，零模型调用、GET文件内容/mtime不变；Node64项通过；完整相关Python456通过1权限跳过（最后回执错误补丁前）。
CURRENT：已完成；最后回执错误补丁3项RED→GREEN，补丁后目标45通过1跳过，浏览器重新通过；独立审查14项定向及终态待对账双尺寸通过、37文件哈希一致，规格范围无未关闭阻塞。
TODO：无本轮开发/验收遗留；正式加载需另行授权，不提交推送。

## 设计契约与裁决

- Ruling：规格首行“待确认”为旧状态，用户最新委派明确已批准，直接实施，不重复确认。
- Ruling：使用当前工作区、顺序开发、不提交和不清理，覆盖技能默认 worktree/commit/清理建议。
- Ruling：以参考图的浅色青绿、左导航/中对话/右详情层级为准；不写入或显示图中示例作品、阶段、日期。
- Ruling：书架主动作是进入作品；最近记录为空就显示空态，全部作品始终可搜索分页。1440 三栏，390 分面，沿用原生栈和既有创作模块。
- Ruling：共享导航只拥有作品/页面链接和离开保护，不保存正文、不创建运行时；切书为完整页面导航。
- Ruling：最近位置增加可选 source=auto|draft|formal，缺省auto；保持同章正式/工作稿恢复准确，兼容计划原三字段接口。
- Ruling：HTTP目录/最近边界拆为小型 bookshelf_web.py，避免继续扩充已有大型 web_workspace.py。
- Ruling：保留已验收的单项目摘要到 /overview 及 author-home.*，根路径仅书架；旧锚点提供明确兼容链接，诊断仍为 /inspector。
- Ruling：切书/返回书架不调用保存或创作命令；章内导航保留既有已排队自动保存的串行语义，避免破坏已验收的作用域保存。
- Ruling：导航作品下拉只取首20部，当前作品始终显示，并提供“返回全部作品”搜索分页入口；目录摘要不无限加载。
- Ruling：待确认候选对应章节仍按真实工作稿优先选择入口，显式source/auto行为保持既有约定；有正式设定但无稿件时默认Writer第一章，只打开不生成。
- Ruling：全项目guard测试1759通过9跳过6失败；其中5项LLM配置测试主动构造真实客户端被guard拒绝，不为这些无关测试放松保护。Windows编码项以PYTHONUTF8=1重跑1通过；另跑完整相关回归。
- Final fixed：正文加载失败在窄屏正文分面明确提示；Node先观察“正在读取”失败后修复，浏览器通过。
- Final fixed：慢版本响应不得抢回作者已切换分面；延迟versions Node先失败后修复，浏览器通过。
- Final fixed：旧/p/{id}/#overview或#chapters提供绑定本书的/overview兼容链接，继续执行未保存离开保护；Node先失败后修复，1440/390浏览器通过。
- Final fixed：坏会话jobs结构验证降partial；目录按单书隔离摘要异常并标未知数量，健康书不消失；9项失败用例后修复、41通过1权限跳过，GET内容/mtime不变。
- Final fixed：待确认目录不再被较新accepted/rejected/cancelled历史抢占；pending/reviewing和终态review_recovery.required均可定位。三项Node及终态计数用例RED→GREEN，64项Node通过，1440/390真实页面验证零模型、未执行对账或审阅命令。
- Final fixed：public新依赖的CommandStoreError显式降级，损坏回执只使候选数未知并显示partial；独立正式/工作统计保留、正常书继续返回。直接查询/HTTP/目录兜底3项RED→GREEN，修后45通过1跳过、书架及旧摘要浏览器重新通过。未将修前456项冒充补丁后全套。
- Final review：独立会话01a13f91-a6c4-72e3-bf0a-bfcb8ee2c457完成最后坏回执HTTP复验、14项定向测试、终态待对账双尺寸及37文件哈希核对；本轮规格无未关闭阻塞。保留全部记录与共享修改，不执行技能默认提交/清理。
- Pre-flight 1→2：目录提供纯项目身份校验；最近记录复用它，拒绝非法项目先于任何写入。
- Pre-flight 1+2→3：列表和最近为独立 GET，单项失败需局部提示；作品入口综合真实摘要及合法最近位置。
- Pre-flight 3→4：旧未绑定 Writer 固定启动默认项目；显式 URL 中 source 白名单保持现有语义。
- Pre-flight 4→5：成功打开后显式 POST 位置；目录 GET、失败加载与取消离开均不得写最近或产生创作命令。
