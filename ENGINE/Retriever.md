# Retriever

Retriever 负责回答：

> 当前 Task 最应该知道什么？

## 输入

- Task
- State
- Domain Package

## 输出

- 最小必要 Knowledge
- 相关 Domain Rules
- RetrievalResult

## 原则

- 不全量扫描 Knowledge。
- 规则检索优先。
- 语义检索作为后续增强。

## RetrievalResult

字段：

- items：检索到的 Knowledge。
- mode：检索模式，当前为 `rule`。
- reasons：每个 Knowledge 被选中的标签原因。
- scanned_all：是否全量扫描，M7 必须为 false。

## 检索规则

M7 只实现规则检索：

```text
Task.tags + Domain.default_retrieval_tags -> KnowledgeStore.find_by_tags
```

没有检索标签时，返回空结果，不能回退为全量扫描。

## M7 验收点

- 输入 Task。
- 输出最小 Knowledge 集合。
- 返回检索原因。
- 不返回 Archived Knowledge。
- 不做全量扫描。
