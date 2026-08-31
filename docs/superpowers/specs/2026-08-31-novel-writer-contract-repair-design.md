# 小说 Writer 合同修复重试设计

## 背景与证据

独立短篇 Live 验收已经证明模型连接和正文生成可用，但连续两次生成都将三项 `essential_information` 同义改写，统一 Reviewer 因精确合同信息缺失而阻断。Prompt 单次约束不足，不能通过放松 Reviewer 或程序拼接句子掩盖。

## 决策

在 `LLMNovelWriterAdapter` 内增加最多一次、仅针对必要信息缺失的完整正文修复重试。Writer 负责让模型输出满足可机械验证的写作合同；Reviewer 仍是最终审查权威，标准不变。

不自动向正文插句，不用语义相似度替代精确合同校验，也不无限重试。

## 组件与数据流

新增独立的通用修复消息投影函数，输入仅包含原始写作请求、首次正文和缺失的必要信息，输出 `ModelMessage` 列表。该函数不得依赖具体作品、客户端或环境配置。

`LLMNovelWriterAdapter` 保持唯一模型出口：

1. 校验准入绑定并执行首次生成；
2. 校验正文基本结构，计算必要信息的精确缺失集合；
3. 无缺失则直接返回；
4. 有缺失则用“原请求、完整初稿、缺失项”执行一次完整重写；
5. 再次校验基本结构并返回第二稿；
6. 第二稿仍缺失时不进行第三次调用，由现有 Reviewer 阻断编译。

修复消息必须要求保留可发布正文形式、重写完整章节、逐字包含每项缺失信息，并禁止分析、清单、代码块或系统术语。首次正文只在本次请求内存中使用，不写入报告或磁盘。

## 配置与审计

`NovelWriterConfig` 增加 `max_contract_repairs`，只允许 `0` 或 `1`，默认 `1`。每次调用继续分别经过 `RuntimeRunner.execute`，不得直接调用 `ModelClient.complete`。

对外 `NovelWriterTelemetry` 聚合所有尝试的耗时与 Token；任一提供方未返回某项 Token 时，该聚合项保持 `None`，不得猜测。最终 `content_hash` 只对应交给 Reviewer 的正文。报告字段保持现有固定集合，不加入原始提示词、正文、客户端、环境字典、密钥或 Header。

## 错误处理

- 提供方失败：保持 `novel_writer_model_failed`；
- 任一稿为空、过短或带模型脚手架：保持现有 Writer 错误，不以重试掩盖；
- 第二稿仍缺必要信息：正常进入 Reviewer，以 `essential_information_missing` 失败关闭；
- 不为其他审查问题自动重试，避免 Writer 耦合 Reviewer 的完整策略。

## 配置修正

主项目 `.env` 中 DeepSeek Base URL 应从网页平台域名改为官方 `https://api.deepseek.com`。只修改 URL，不复制、打印或提交 `.env` 及密钥。

## 验证

- 无缺失时只调用一次；
- 首稿缺失时恰好调用两次，修复消息含完整初稿和精确缺失项；
- 第二稿合格时返回第二稿并聚合遥测；
- 第二稿仍缺失时不发生第三次调用，Reviewer 阻断；
- 旧错误行为不回归，Fake 验收仍一次调用并达到编译候选；
- Live 只有达到 `compile_candidate_ready` 且 `review_passed=true` 才开放投影层。

## 非目标

不实现通用 Reviewer 自动修复循环，不保存模型原始正文，不开发投影/UI，不加入作品专名或供应商特化业务逻辑。
