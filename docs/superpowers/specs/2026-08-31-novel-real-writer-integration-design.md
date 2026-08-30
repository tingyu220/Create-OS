# Novel Domain 真实 Writer 接入与独立样本验证设计

## 1. 目标

在不复用任何具体作品提示词、人物名或事实词典的前提下，将现有 OpenAI-Compatible 模型通信能力适配为 `NovelWriterPort`，接入 `NovelDomainService` 的规划—准入—写作—审查—编译闭环，并用一部全新短篇小说证明该闭环不依赖《文明升阶》。

本阶段不开发 Web UI，也不直接把模型输出写入正式正文、Canon 或 State。

## 2. 已有能力与问题

可复用能力：

- `ModelClient.complete()`：稳定的模型通信端口；
- `OpenAICompatibleClient`：从环境读取地址、密钥、模型和超时；
- `NovelWriterPort`：Novel Domain 的正文生成端口；
- `NovelDomainService.run_chapter()`：规划、准入、Writer、Reviewer、Compiler 组合入口；
- `NovelDraft`：正文与内容哈希的统一输出。

不可直接复用 `run_llm_writer_pilot`。该流程包含特定作品的事实词典、人物名、地点名和旧生产落盘行为，若直接接入会破坏 Novel Domain 的通用边界。

当前机器尚未配置 `CREATIVE_OS_LLM_BASE_URL`、`CREATIVE_OS_LLM_API_KEY` 和 `CREATIVE_OS_LLM_MODEL`。这不阻碍适配器开发和 Fake Client 验证，但真实网络验收必须具备这些配置。

## 3. 方案

新增通用 `LLMNovelWriterAdapter`，只依赖 `ModelClient`，不依赖 `OpenAICompatibleClient` 的具体实现。生产组合根负责从环境创建真实客户端并注入适配器。

```text
NovelWritingRequest
        │
        ▼
Writer Admission Token ──身份绑定校验
        │
        ▼
LLMNovelWriterAdapter ──构建通用消息──> ModelClient
        │
        ▼
NovelDraft ──> NovelReviewer ──> NovelCompiler Candidate
```

适配器不读取项目文件、不保存草稿、不更新任务状态、不写 Canon/State。所有副作用仍由 Novel Domain 之外的编排层明确执行。

## 4. 数据契约

### 4.1 输入

沿用 `NovelWritingRequest`：

- `chapter_id`：章节身份；
- `chapter_contract`：已批准章节合同；
- `context_fingerprint`：与 Writer Admission 绑定的上下文指纹；
- `instruction`：本次写作补充指令。

适配器配置独立为不可变对象：

- `temperature`：默认 `0.7`；
- `max_tokens`：默认 `6000`；
- `system_instruction`：稳定的通用小说写作约束。

### 4.2 输出

成功时只返回 `NovelDraft`：

- `content`：清理首尾空白后的正文；
- `content_hash`：正文 SHA-256。

模型耗时和 Token 用量不能混入正文模型。它们作为独立 `NovelWriterTelemetry` 返回给可选观察器，供后续可视化投影读取。

## 5. 提示词边界

系统消息只表达通用约束：

- 依据批准合同写作，不自行改写合同；
- 只输出可发布正文，不输出分析、提纲、Markdown 代码块或系统术语；
- 完成合同要求的场景目的、必要信息、情绪变化和戏剧闭合；
- 不发明合同与输入未授权的既成事实。

用户消息由结构化合同字段确定性生成，至少包含：章节身份、章节功能、戏剧问题、主人公选择、读者变化、目标字数、场景顺序、场景目标/冲突/行动/状态变化、必要信息、情绪变化、闭合要求、禁止项和补充指令。

提示词生成器必须是纯函数，可独立快照测试。通用源码不得出现任何样本作品专名。

## 6. 准入与失败关闭

Writer 执行前必须验证：

1. admission 对象存在；
2. admission 的上下文指纹与请求一致；
3. admission 对应的合同身份与请求章节合同一致；
4. Chapter Contract 满足 Novel Scene 增强语义。

以下情况抛出 `NovelWritingError`，不得返回部分成功：

- 准入身份或上下文不匹配；
- 模型调用异常；
- 模型返回空文本；
- 输出包含明显的分析前缀或代码块包装；
- 输出没有达到最低可审查长度。

字数不足、重复、戏剧单元不闭合等内容质量问题仍由统一 `NovelReviewer` 判定，Writer 不复制 Reviewer 规则。

## 7. 组合入口

扩展组合根，而不改变 `NovelDomainService`：

- `build_novel_domain_service(...)` 继续支持注入任意 Writer；
- 新增从 `ModelClient` 构建 `LLMNovelWriterAdapter` 的工厂；
- 新增从环境构建真实服务的显式入口；
- 环境入口只在调用时读取凭据，测试和导入模块不触发网络。

这样 Fake Client、真实 OpenAI-Compatible Client 和未来其他 Provider 共用同一领域闭环。

## 8. 独立短篇验证

新建最小验证项目，题材与《文明升阶》完全不同。建议样本为现实悬疑短篇《末班钟表店》，验证一章完整事件：钟表修复师在闭店前发现委托怀表记录了不存在的时间，并必须决定是否把证据交给正在寻找失踪父亲的女孩。

样本只提供当前章节所需的最小 Profile、Chapter Contract、State 与基线证据，不复制《文明升阶》的文件或人物设定。

验收分两层：

1. Fake Client 端到端测试：确定性正文通过规划、准入、Writer、Reviewer，并产生 Compiler Candidate；
2. 真实 Client 验收：使用本机环境配置完成一次真实调用，保存脱敏运行报告，证明使用的 Provider、模型、耗时、Token、正文哈希和各阶段结果，但不保存 API Key。

若真实配置缺失，阶段状态只能记为“实现完成、真实验收阻塞”，不能宣称真实 Writer 已验证。

## 9. 测试策略

- 提示词生成：字段完整、顺序稳定、无作品专名；
- 准入绑定：合同、上下文指纹不一致时失败；
- Client 返回：字符串与 `TimedCompletion` 两种结果；
- 输出清理：空文本、分析包装、代码块和过短文本失败；
- 组合根：Fake Client 可装配完整服务，导入时不访问网络；
- 独立项目：完整 `run_chapter()` 达到 `compile_candidate_ready`；
- 回归：运行全量测试，并扫描通用源码不存在样本专名。

## 10. 可视化的后续接口

本阶段只留下稳定遥测和阶段结果，不实现页面。后续数据投影层应从这些只读事实生成章节状态、门禁、审查问题、角色状态、时间线和伏笔视图，不反向调用 Writer，也不修改领域对象。

## 11. 完成标准

- 真实 Writer 适配器只依赖通用端口；
- Novel Domain 组合入口可注入 Fake 或真实 Client；
- 全新短篇 Fake Client 端到端闭环通过；
- 配置存在时，真实模型端到端闭环通过并生成脱敏报告；
- 通用源码无《文明升阶》及新样本专名硬编码；
- 全量测试通过；
- 未提前开发 Web UI。
