# 战斗专家任务6报告：隔离全链验收与《文明升阶》只读研究

状态：**已完成**。

## 隔离验收结果

执行命令：

```text
python scripts/validate_combat_agent_ui.py --output-dir .backup/combat-task6-final
```

结果：`status=passed`，随机本机端口 `64999`，临时项目根为 `C:\Users\tingyu\AppData\Local\Temp\creative-os-combat-task6-...`（脚本每次运行随机生成），两本临时书为“任务6甲书”和“任务6乙书”。没有使用 8877、真实书、生产 Runtime 或真实模型。

覆盖链路：

- 甲书：讨论 → 显式 `requested_expert=combat` → 真实来源读取 → combat 候选 → 采用 → 作者编辑 → 确认版本 v1 → 目标第2章实际入模（含未来计划标签、版本、哈希、来源）→ Proposal 差异 → 接受工作稿 v1。
- 乙书：同编号项目隔离；专家返回 `insufficient` 并保留“目标章节正文未提供”未知；甲书结果没有进入乙书。
- 甲书先走自主普通分析（未设置 `requested_expert`，`combat_results=[]`），再走显式专家入口，证明专家是按需能力而非关键词必调。
- 未确认计划的显式 `require_confirmed_combat` 被 `story_confirmation_required` 阻断；普通写作仍生成 Proposal。重复旧 revision 采用返回冲突，确认版本保持 v1。
- Fake 首次 `乙书故障重试` 失败，HTTP retry 成功且沿用原任务范围；刷新只发 GET，不增加 POST。

浏览器证据：

- 1440×1000：[`combat-1440.png`](../.backup/combat-task6-final/combat-1440.png)
- 390×844：[`combat-390.png`](../.backup/combat-task6-final/combat-390.png)
- 两个尺寸均断言战斗入口/状态文本可见，入口按钮 `tabIndex >= 0`；390 断言 `document.documentElement.scrollWidth <= window.innerWidth`；`pageerror=[]`。

机器可核对证据：

- [`report.json`](../.backup/combat-task6-final/report.json)：随机端口、项目、结果 ID、Proposal、工作稿版本、消息哈希和浏览器错误。
- [`messages.json`](../.backup/combat-task6-final/messages.json)：Fake 实际收到的每一轮消息；甲书最终消息包含“未来创作计划，不是已发生事实”、作者编辑文本和确认 `story-confirmed` 来源。
- [`posts.json`](../.backup/combat-task6-final/posts.json)：13 条实际 POST，含请求路径、响应状态、UTF-8 字节长度、SHA-256 和 JSON 载荷。脚本逐条断言字节长度与 JSON 往返一致，脚本内纯 GET 刷新前后 POST 计数不变。

## 测试矩阵

| 检查 | 命令 | 结果 |
|---|---|---|
| 隔离全链 | `python scripts/validate_combat_agent_ui.py --output-dir .backup/combat-task6-final` | 通过；随机端口、双临时书、两视口、13 POST |
| Combat 与受影响后端 | `python scripts/run_fake_writer_tests.py <全部 tests/test_combat_*.py> tests/test_agent_proposal.py tests/test_story_architecture.py tests/test_agent_runtime.py tests/test_writer_production_exit_architecture.py` | **174 passed, 1 skipped**（符号链接权限用例沿用既有限制） |
| Combat UI | `node --test tests/test_combat_ui.js` | **4 passed** |
| 语法 | `python -m py_compile scripts/validate_combat_agent_ui.py` | 通过 |

## 《文明升阶》只读研究

研究文档：[`文明升阶-战斗与伏笔候选.md`](research/文明升阶-战斗与伏笔候选.md)。已读取 81 个正式章节文件、指定合同/元数据和生产审计报告，列出每章标题与 SHA-256；文档把已读事实、未知和推断分开，候选不会自动创建 `combat-plan`、候选版本或正文。原项目文件哈希在研究前后未被脚本写入或修改。

## 限制

Fake 模型只验证调用链、冻结来源、权限和消息证据，不能证明真实模型的文学质量。研究范围以当前正式正文和明确列出的合同/报告为准；未读草稿或未物化 State 不被推断为不存在。没有 commit、push、merge、部署或清理共享未提交改动。
