# 作品书架与统一创作空间实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 将已批准三屏结构接入现有新书、Writer和Story功能。
**Architecture:** 独立作品目录查询及UI最近记录，不装配Runtime。既有项目作用域页面保持隔离，前端统一导航，不重建创作业务。
**Tech Stack:** Python、原生HTML/CSS/JavaScript、pytest、Node、Chromium。
**Spec:** docs/superpowers/specs/2026-10-19-bookshelf-workspace-design.md

## Global Constraints

- 保留所有共享未提交修改；不commit/push/merge，不自动重启8877。
- 全部GET无写入；最近记录仅明确POST更新工作区UI元数据。
- 仅临时项目及fake_validation_guard测试，禁止真实模型和小说测试写入。
- 桌面1440与窄屏390；复用现有浅色样式，不增加框架。

## Review Focus

- 目录包含损坏或越界项目：隔离错误，不使全部作品消失（任务1）。
- 两页面同时写最近记录：原子更新保留其他项目记录（任务2）。
- 页面加载失败：不得记录为成功打开（任务2、3）。
- 未保存编辑切书：提示后才离开，迟到响应不串项目（任务4）。
- 旧未绑定URL与source参数：默认项目和稿件来源保持正确（任务3、4）。

### 任务1：只读作品目录

**Files:** 新增creative_os/project_catalog.py、tests/test_project_catalog.py；最小修改creative_os/web_workspace.py。
**Interfaces:** ProjectCatalog(projects_root).list_projects(query: str = '', offset: int = 0, limit: int = 20) -> dict；GET /api/projects返回items、total、warnings。items仅含project_id/title及可用入口，不返回正文。有效目录验证复用现有规则但不调用Registry.get。
- [x] 写临时三作品、损坏metadata、符号链接越界、分页搜索和查询mtime不变测试，先观察失败。
- [x] 实现纯文件查询和GET；限制limit为1至100，非法参数400；异常条目列警告而非误报空书架。
- [x] 运行python scripts/run_fake_writer_tests.py tests/test_project_catalog.py，要求全通过且无Runtime实例。

### 任务2：真实最近打开记录

**Files:** 新增creative_os/workspace_recent_store.py、tests/test_workspace_recent_store.py；修改web_workspace.py。
**Interfaces:** WorkspaceRecentStore(projects_root).read() -> list；record(project_id: str, page: str, chapter_number: int | None) -> dict。存放projects根/.creative_os/workspace-recent.json；GET /api/projects/recent；POST /api/projects/recent接受page=writer|story及合法项目/章节，服务端记录UTC时间。
- [x] 测试空记录不创建文件、并发两项目保留、非法项目不写、损坏记录明确报错、同项目更新位置。
- [x] 使用工作区锁和原子replace更新，不改项目目录；损坏文件不静默覆盖。
- [x] guard下运行上述测试；记录失败不阻断打开书，前端显示非阻塞提示。

### 任务3：书架和兼容入口

**Files:** 修改web/index.html、app.js、styles.css；新增tests/test_bookshelf_ui.js；更新tests/test_web_workspace_routes.py。
**Interfaces:** 根页读取任务1/2接口，渲染最近打开和全部作品；所有书链接使用/p/{编码ID}/入口。/story继续新书创建；项目入口根据合法最近记录或真实稿件选择Writer/Story，不以投影推测位置。
- [x] 写列表搜索、空态、部分损坏、读取失败、新建后可发现、旧链接默认项目正确的失败测试。
- [x] 替换根页为已批准书架；保留单项目摘要为次级信息，不展示无来源的阶段或完成状态。
- [x] 打开目标页面成功加载后POST最近记录，不在书架GET或点击尚未成功时写入。
- [x] Node与guard路由测试通过，确认技术诊断独立可达。

### 任务4：统一书内导航

**Files:** 修改web/writer.html、writer.css、writer.js、story.html、story.css、story.js、project-scope.js；必要时新增小型共享导航模块web/workspace-navigation.js；新增tests/test_workspace_navigation_ui.js。
**Interfaces:** 显式项目URL导航，Writer继续使用已有章节/source/Proposal接口；Story继续既有对话/确认接口，记录成功位置调用任务2。共享模块仅导航展示，不拥有正文或Runtime状态。
- [x] 先测同章正式/工作稿切换、目录筛选、跨书导航、未保存离开取消、迟到响应、旧章节锚点兼容。
- [x] 左目录、中对话、右内容沿用既有模块；合并重复章节列表入口，Story保持相同壳层级；窄屏采用分面展示。
- [x] Node行为测试通过，保存/接受/确认不因导航产生隐式提交。

### 任务5：整体验收

**Files:** 新增scripts/validate_bookshelf_ui.py；记录docs/bookshelf-workspace-v1.md。
- [x] 临时项目Chromium走书架→旧书工作稿→切书→新书构思→返回书架→刷新恢复位置，验证真实记录与项目隔离。
- [x] 1440/390截图检查空态、错误、长标题、未保存保护；断言零模型调用，GET项目文件内容/mtime不变。
- [x] guard运行相关Writer/Story/Web/目录及最近记录回归，Node行为回归；独立审查后处理阻塞。
- [x] 汇报已完成/未完成、证据与限制；用户另行授权后加载正式服务，不提交推送。

## 执行与检查点

沿用单开发负责人顺序实施、独立审查，避免多个代理同时修改路由或共享前端。总控按任务交付证据推进。以上五项覆盖规格全部范围；作品删除、云同步、归档和跨书记忆不在本轮。
