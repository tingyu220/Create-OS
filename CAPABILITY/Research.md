# Research Capability

Research 负责从 Provider 获取外部知识。

## Provider 预留

- Local Provider
- Web Provider
- MCP Provider
- User Provider

## 输出

Research 只输出 Knowledge Draft，不能直接写入 Active Knowledge。

Result 要求：

```text
kind = research
knowledge_drafts = list[KnowledgeDraft]
```

## 原则

外部知识必须经过验证和 Compiler。

## M11 验收点

- Research 通过 Provider 获取资料。
- Research 输出 Knowledge Draft。
- Research 不直接写 Knowledge。
- Knowledge Draft 必须经过 Compiler。
- Compiler 写入时状态为 Draft，不是 Active。
