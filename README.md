# Creative OS V1

Creative OS V1 是一个知识驱动的长期创作系统底座。

正式执行依据：[EXECUTION_PLAN.md](EXECUTION_PLAN.md)

核心流水线：

```text
Task -> Retriever -> Context -> Capability -> Result -> Compiler -> Knowledge
```

V1 不追求完整产品 UI，而是验证：

- Knowledge 是唯一可信数据源；
- Task 驱动系统推进；
- Capability 只接收 Context，不直接读写 Knowledge；
- Result 必须经过 Compiler 才能回写 Knowledge；
- Novel 只是第一个 Domain Package。

当前执行进度：已完成阶段四 `Novel Domain`，V1 已具备小说领域包闭环。

## 目录

```text
DOMAIN/        核心领域模型文档
ENGINE/        创作引擎文档
CAPABILITY/    AI 能力边界文档
DOMAINS/Novel/ 小说领域包文档
creative_os/   V1 最小可运行核心
tests/         V1 验收测试
```

## 验证

```bash
python -m pytest -q
```
