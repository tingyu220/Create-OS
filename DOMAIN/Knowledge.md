# Knowledge Model

Knowledge 是 Creative OS 的唯一可信数据源。

它不是聊天记录，不是 Prompt，也不是运行时 Context。

## 分类

- Domain Knowledge：领域规则，例如小说的人物、章节、伏笔概念。
- Project Knowledge：项目内事实，例如角色、事件、世界观、章节摘要。
- External Knowledge：外部资料，例如联网搜索、百科、文献。
- User Knowledge：用户偏好、创作禁区、长期风格要求。

代码枚举：

```text
domain
project
external
user
```

## 生命周期

```text
Draft -> Verified -> Active -> Archived
```

允许状态流转：

```text
Draft    -> Verified / Archived
Verified -> Active / Draft / Archived
Active   -> Archived
Archived -> Draft
```

禁止：

- Draft 直接进入 Active。
- Active 被 Draft 静默覆盖。
- Archived 默认参与检索。

## 边界

- Knowledge 保存长期事实。
- Memory 不作为独立长期层存在。
- Context 是运行时数据包，不回写为 Knowledge。
- State 只保存当前状态，不保存长期知识。

## 更新规则

- Capability 不能直接写 Knowledge。
- Result 必须经过 Compiler。
- 冲突内容先进入 Draft 或 Issue，不直接覆盖 Active。
- 同 ID 更新必须重建索引。
- 引用缺失时禁止写入。

## 引用规则

- Knowledge 可以通过 `references` 引用其他 Knowledge。
- 被引用的 Knowledge 不能硬删除。
- 引用关系必须进入索引，供 Review 和 Compiler 检查。
- 引用目标不存在时，写入失败。

## 删除与归档

- 删除前优先归档。
- 被引用的 Knowledge 不能硬删除。
- 低价值或过时内容进入 Archived。
- 硬删除仅允许在无入站引用时执行。
- 硬删除前必须保留 deleted backup。

## M1 验收点

- Knowledge 有明确分类。
- Knowledge 生命周期受状态机约束。
- Knowledge 引用关系可查询。
- 被引用内容不能硬删除。
- 删除前会保留备份。
