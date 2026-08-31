# 单小说项目统一只读 Projection Layer 设计

## 1. 目标与边界

为 Creative OS 建立统一 Read Model：

```text
Domain / Knowledge / Runtime
            │
            ▼
   Projection Builder
            │
            ▼
      ProjectSnapshot
       /      |      \
     UI      API    Agent
```

第一版只构建一个明确 `project_id` 对应的小说项目快照，不开发跨项目总览，也不实现页面。架构允许未来将多个 `ProjectSnapshot` 组合为 `PortfolioProjection`，但后者不属于本阶段。

Domain、Knowledge、Runtime 始终是唯一真实数据源。Projection 是可丢弃、可重建、不可反向写入的派生结果。未来用户修改必须经过 `Command → Domain → Event → Projection Refresh`。

## 2. 现状判断

现有能力可以作为数据源，但不能直接作为统一投影：

- `AppendOnlyEventLog` 提供连续序号和运行事件，但事件本身没有 `project_id`；
- `ChapterTaskStatus` 提供章节结果、尝试次数、耗时和问题，但当前是独立 JSON，并保留旧格式回退；
- Novel Reviewer、Compiler、各 Gate 和状态存储分别拥有权威结果；
- Narrative Replay 已遵循“只依据证据、不从正文臆测”的原则，可复用其证据语义；
- `console_dashboard.py` 直接读取章节文件并统计，属于展示层拼接业务逻辑，只保留为兼容消费者，不继续扩张。

因此第一版不能假设 Event Log 已覆盖全部领域事实，也不能把文件是否存在直接解释成业务事实。

## 3. 方案比较

### 方案 A：类型化快照与纯投影器（采用）

以项目范围的 Source Adapter 读取权威数据，由无副作用 Section Projector 生成不可变 section，最后组装 `ProjectSnapshot`。构建接口接受刷新游标，但第一版可全量读取。

优点是边界清楚、便于测试、UI/API/Agent 共用同一语义，并能平滑演进到增量刷新。代价是需要显式维护来源适配器与投影模型。

### 方案 B：请求时查询门面（不采用）

每个消费者请求时直接读取多个 store 并现场拼接。初期代码少，但不同消费者会逐步复制业务判断，也无法保证一致切面和稳定追溯。

### 方案 C：立即建立持久化事件消费系统（暂不采用）

将所有领域变更统一事件化并持续物化投影。长期能力最强，但现有 Event Log 尚未覆盖全部领域数据，当前实施会迫使领域层同步重构，超出本阶段范围。

## 4. 模块边界

建议新增独立 `creative_os/projection/` 包：

```text
projection/
  model.py          # ProjectSnapshot 与各 section 的不可变读模型
  provenance.py     # SourceRef、SourceHead、Derivation
  source.py         # Source Adapter 协议和 ProjectSourceSet
  builder.py        # 一致性构建、重试、section 编排
  refresh.py        # Full/Incremental 刷新请求与结果协议
  projectors/       # 每个 section 一个低耦合纯投影器
  codec.py          # 稳定 JSON 编解码，不承担业务判断
```

依赖方向只能是 `projection → domain/runtime/knowledge`。领域包不得导入 projection。UI、API 和 Agent 只能依赖 `ProjectSnapshot` 或只读查询接口，不能自行读取领域文件后生成业务状态。

## 5. 顶层数据契约

`ProjectSnapshot` 是不可变值对象，至少包含：

- `schema_version`：读模型结构版本，不等同领域版本；
- `snapshot_id`：由项目、来源切面和结构版本确定性计算；
- `project_id`：显式项目身份，禁止使用进程级全局当前项目；
- `built_at`：完成构建时间，仅用于观察，不参与领域判断；
- `consistency`：一致性状态和本次构建尝试信息；
- `source_heads`：所有参与来源的版本、序号或内容指纹；
- `overview`、`chapters`、`quality`、`trace`：第一优先 section；
- `characters`、`story_threads`、`timeline`：后续同级 section，不嵌入第一优先模型内部；
- `diagnostics`：缺失、冲突、过期等投影诊断，不能伪装成领域 Issue。

所有集合采用稳定排序，序列化结果必须确定。`ProjectSnapshot` 不暴露保存、修改或审批方法。

未来 `PortfolioProjection` 只能接受 `ProjectSnapshot` 集合并做跨项目汇总；它不能绕过快照直接读取单项目领域数据。

## 6. 来源与追溯

关键投影字段必须携带或可关联以下结构：

- `SourceRef`：`source_kind`、`source_id`、`locator`、`content_hash`；
- `SourceHead`：某一来源在构建切面上的 `version/cursor/hash`；
- `Derivation`：派生值的规则编号、输入引用和可选说明。

`locator` 可以是事件序号、记录 ID、相对项目路径加 JSON Pointer，或领域对象稳定 ID。不得保存绝对机器路径，不得把未经结构化确认的正文推断写成事实。

例如“章节被阻塞”必须引用失败 Gate、阻塞 Issue 或运行失败事件；若找不到权威依据，只能投影为 `unknown` 并生成诊断，不能根据正文缺失自行断言。

## 7. 严格一致快照

第一版采用乐观的严格一致构建：

1. Builder 向每个 Source Adapter 获取构建前 `SourceHead`；
2. 各 projector 只读取该项目范围的数据并生成 section；
3. Builder 再次获取 `SourceHead`；
4. 任一来源发生变化则丢弃本次结果并按有限次数重试；
5. 来源头一致才发布完整 `ProjectSnapshot`。

文件来源使用规范化内容哈希或清单哈希；Event Log 使用末尾 `sequence + event_id`。读取 Event Log 时，项目范围由 `ProjectSourceSet` 对应的项目根和日志实例确定，不能依赖当前日志 payload 推断项目身份。

构建失败不得覆盖上一份成功快照。调用方收到明确错误和诊断，可继续读取标记为旧版本的上一快照，但不能把失败中的半成品发布为新快照。

## 8. 刷新接口

公开接口不绑定全量扫描：

```text
ProjectionBuilder.build(ProjectProjectionRequest) -> ProjectionBuildResult

ProjectProjectionRequest:
  project_id
  source_set
  previous_cursor?   # 第一版允许忽略，但语义预留
  requested_sections?

ProjectionBuildResult:
  snapshot
  cursor             # 各来源已消费位置/指纹
  refresh_mode       # full 或 incremental
```

第一版实现 `full`，但 projector 接口接收 `previous section + changeset` 的可选参数。未来 Event Log 足够完备后可增加增量 Source Adapter，而不修改消费者契约。

## 9. Section 语义

### 9.1 Overview

回答项目当前运行到哪里：当前阶段、总体状态、章节计数、最近活动、阻塞摘要和数据新鲜度。它只汇总其他 section 与权威运行事实，不自行扫描文件创造状态。

### 9.2 Chapter Matrix

每章一行，包含章节身份、规划/准入/写作/审查/编译阶段状态、尝试次数、耗时、当前 Gate、阻塞原因、产物引用和更新时间。阶段状态采用明确枚举，并区分 `not_started`、`running`、`passed`、`failed`、`blocked`、`unknown`。

### 9.3 Quality

统一呈现 Review、Gate、Issue，但保留来源类别和原始 code。Projection 可以派生阻塞数量、严重度统计和当前 Gate 结果；不得改写 Issue、自动批准或把 warning 提升为领域 error。

### 9.4 Runtime / Trace

按 Event Log sequence 和 execution record 展示最近动作、能力调用、结果、耗时、错误和输入/输出引用。Trace 只做关联与排序，不保存密钥、完整提示词或敏感模型响应。

### 9.5 Characters、Story Threads、Timeline

第二批实现。Characters 来源于已批准状态及明确候选状态；Story Threads 是 Foreshadow、Expectation、Open Loop 的 UI 聚合类型，但保留原始类型与来源；Timeline 只接受已结构化的时间线事实和冲突结果，不从正文自动补事实。

## 10. 缺失、冲突与降级语义

- 权威来源缺失：字段为 `unknown/not_available`，附诊断；禁止用空集合伪装“确认没有”。
- 多来源冲突：保留冲突引用，section 标记 `conflicted`；Projection 不裁决领域事实。
- 非关键扩展 section 不可用：可发布带诊断的快照。
- Overview、Chapters、Quality、Trace 任一必要来源损坏或无法形成一致切面：构建失败，不发布新快照。
- 旧格式兼容读取放在 Source Adapter 内，并标记 `legacy` 来源；核心模型不包含旧格式分支。

## 11. 只读约束

代码层保证：

- 模型使用冻结值对象和只读集合；
- projection 包不调用任何 `append/save/write/approve/transition` 方法；
- Builder 唯一允许的写入是可选的快照缓存，缓存不属于领域事实且可安全删除重建；
- 快照缓存使用原子替换，失败时保留上一成功版本；
- 对外服务只提供 `get_snapshot`、`build/refresh`，不存在字段级更新接口。

## 12. 测试策略

- 模型与 Codec：稳定排序、往返一致、schema version、无绝对路径；
- 来源适配器：项目隔离、旧格式标记、缺失与损坏处理；
- Projector：固定输入产生固定输出，派生值均可追溯；
- 一致性：构建中来源变化会重试，超过次数不发布；
- 只读性：测试替身若收到领域写调用立即失败；
- 冲突语义：不裁决、不伪造空值；
- Event Log：sequence/cursor 关联和最近活动排序；
- 消费者契约：控制台只能读取 snapshot，不能直接导入领域 store；
- 全量回归：现有 Novel Domain 和真实 Writer 验收不受影响。

## 13. 分阶段交付

1. 基础模型、来源协议、严格一致 Builder、Codec；
2. Overview、Chapter Matrix、Quality、Trace projector；
3. 将现有文本控制台改为 `ProjectSnapshot` 的薄消费者，作为架构验收，不增加页面；
4. Characters、Story Threads、Timeline projector；
5. 在 Event Log 项目身份和覆盖度完善后增加增量刷新实现；
6. Projection 接口稳定且工作台准入再次确认后，才规划 Web UI。

## 14. 完成标准

- 单项目可生成严格一致、确定性、可追溯的 `ProjectSnapshot`；
- Overview、Chapter Matrix、Quality、Trace 能回答运行进度、阻塞原因和最近活动；
- UI/API/Agent 无需拼接多个领域模块；
- Projection 无任何领域写入路径，删除缓存可完整重建；
- 第一版接口不依赖全局单项目，也不绑定全量扫描；
- 未实现跨项目总览，未提前堆 Web 页面。
