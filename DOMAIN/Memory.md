# Memory Model

Memory 保存 Creative OS 在长期运行中形成的决策、偏好和可复用方法。它不替代 Knowledge：Knowledge 回答“什么是真的”，Memory 回答“以前如何做、效果如何、当前任务是否适用”。

## 类型

- `working`：当前任务或项目的短期工作信息。
- `project_decision`：仅在当前项目有效的已确认决策。
- `user_preference`：用户长期偏好和创作禁区。
- `domain_method`：某个领域的通用方法。
- `experience`：从运行、审查和人工反馈中提炼的经验。

## 作用域

每条记忆必须声明作用域和 `scope_id`：

```text
task -> project -> domain / user -> global
```

项目记忆不能跨项目召回；领域记忆只能用于匹配的 Domain；用户记忆只能用于匹配用户。全局记忆必须谨慎审批。

## 生命周期

```text
candidate -> active -> archived
         \-> rejected -> archived
```

- 系统只能创建 `candidate`。
- `candidate` 必须经过人工审批才能成为 `active`。
- `system` 不能作为审批人。
- Retriever 只召回 `active`。
- 拒绝和归档必须保留审计记录。

## 来源追踪

每条记忆至少包含一条 Evidence，包括来源类型、来源 ID 和说明。Context Compiler 还会记录：

- 记忆 ID；
- 记忆版本；
- 召回原因；
- 内容哈希；
- 编译后的 Context 指纹。

## 效果评估

记忆被使用后，系统追加记录使用次数、审查问题变化和人工评分。效果数据只供人工判断，不会自动晋升、降级或覆盖记忆。

## 项目目录

```text
.creative_os/memory/
├─ items/
├─ revisions/
├─ audit.jsonl
└─ usage.jsonl
```

## 人工审批

```powershell
python scripts\memory_review.py --memory-root projects\文明升阶\.creative_os\memory list
python scripts\memory_review.py --memory-root projects\文明升阶\.creative_os\memory show <memory-id>
python scripts\memory_review.py --memory-root projects\文明升阶\.creative_os\memory approve <memory-id> --actor tingyu --note "确认适用范围"
python scripts\memory_review.py --memory-root projects\文明升阶\.creative_os\memory reject <memory-id> --actor tingyu --note "范围过宽"
```

第一版使用 JSON/JSONL 和确定性规则检索，不依赖向量数据库。
