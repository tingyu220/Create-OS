# 战斗专家任务3独立审查

状态：**已完成审查；实现待处理**。本轮发现 1 个 P2 阻塞项，修复并定向验证前不建议放行任务3。

## 规范结论

**暂不通过**：既有专家生产端可合法返回重复来源引用，本轮采用接口却无法消费该结果，尚未完整满足“消费现有 job 持久化的 CombatResult”。其余已审查要求符合任务3边界：服务端按 ID 取结果、跨书与本次重试身份校验、冻结来源归属与 hash 校验、CAS/幂等、保留非目标块及未决问题、作者编辑保留关联且取消修订文字背书、删块同步删关联、旧 hash/操作回执兼容、作者显式确认绑定 revision/hash 并保存完整快照。

## 质量结论

**暂不通过**：存在一个已定向复现的生产端/消费端契约不一致，现有新增测试没有覆盖该情形。除此之外未发现需要阻塞的质量问题；改动职责与规模可控，沿用原项目锁和单聚合原子提交，采用与确认均没有正文写入调用。

## 阻塞项

### [P2] 允许的重复证据引用使合法专家结果无法采用

- 位置：`creative_os/combat_story_candidate.py:136`（关联直接采用原 `evidence_refs`），触发校验位于同文件 `:37`。
- 原因：`creative_os/combat_agent.py:66` 至 `:75` 对结果数组检查字符串类型、引用是否属于实际已读集合，没有要求唯一。`CombatResult` 也没有该唯一性约束。因此专家在 finish 中输出同一已读 source_id 两次，会正常返回并可持久化；任务3的关联校验却拒绝重复引用。
- 影响：作者采用该服务端结果时收到 `combat_plans_invalid`，候选无法创建。这并非伪造身份或无效来源，不能以拒绝伪造结果解释。
- 定向复现：在 `fake_validation_guard` 和 `TemporaryDirectory` 中复用真实测试夹具，调用真实 `run_combat_expert` 先读取有效来源，再 finish 返回 `[source_id, source_id]`，把返回值经原 `AgentConversationStore` 持久化后调用 `stage_combat_candidate`。输出为：

```text
expert_result_accepted: 2
adoption_rejected: combat_plans_invalid
candidate: None
```

- 建议：在构造关联时按首次出现顺序去重 `evidence_refs`，保留完整原结果的 `result_hash` 绑定；添加上述生产/消费边界的回归用例，验证采用成功、关联引用唯一、来源 hash 正确、原完整结果 hash 未改变、重复 operation 可重放。无需修改任务2的生产契约或扩大重构。

## 范围和验证记录

- 先读取任务简报和实施报告，再直接读取四个指定共享文件及必要调用依赖，没有审查历史分支。
- 既有 **253 passed, 1 skipped** 来自实施报告，本轮没有重复运行大套件，也不把它声称为独立复跑结果。
- 本轮仅执行上述具体疑点的受保护临时项目验证；未调用真实书、真实模型、生产 Runtime、8877 或 Git，未派子代理。
- 任务4的章节范围过滤/写作消息消费和任务5的 UI 接入不属于本轮缺陷。
- 本轮只新增本审查文档，没有修改实现或测试。

## P2 修复轮1定向复审

状态：**已完成**。原唯一 P2 已解决，任务3可放行；本结论不扩大到任务4、任务5或真实模型端到端验收。

- **ADDRESSED：合法重复引用可采用且保持首次顺序。** `stage_combat_candidate` 仅在构造关联时使用 `list(dict.fromkeys(value["evidence_refs"]))`。新增真实专家用例先依次读取两条真实冻结来源，再 finish 返回交错重复引用，经原会话存储持久化并重读后 stage；断言关联按首次出现顺序保留两条引用，并对应正确来源 hash。
- **ADDRESSED：原完整结果 hash 和持久内容不变。** `_load_result` 返回原结果的深拷贝；去重仅生成关联数组，`result_hash` 与操作指纹仍使用 `content_hash(value)`。新增用例既断言其等于持久原结果 hash，又断言不等于替换为去重引用后的结果 hash，并重新读取会话断言持久结果完整相等。
- **ADDRESSED：非法引用仍拒绝。** `_load_result` 仍在构造关联前逐项调用 `read_combat_source` 并检查 included/hash；新增 `["forged-source", "forged-source"]` 参数断言采用抛错且无候选。去重没有绕开该校验路径。
- **ADDRESSED：幂等。** 新增真实链路用例用同一 operation 在新建 `StoryArchitectureStore` 后重放，断言完整候选相等；原结果 hash 继续参与指纹，没有将去重后的关联冒充原结果。
- **修复是否造成新破坏：本轮限定静态检查未发现。** 修复限于关联数组，原结果校验、完整结果 hash、来源 hash、存储内容及幂等入口均保持原语义；无需扩大重构。
- **验证证据归属：** 修复报告记录实际 RED 为 **1 failed, 19 deselected in 0.84s**（恢复缺陷行后在 stage 报 `combat_plans_invalid`），还原修复后 GREEN 为 **36 passed in 1.19s**，退出码0。本复审核对限定实现、测试和报告，未独立重跑上述测试，也未重跑253组合；没有具体新疑点需追加运行。
- 本轮只追加审查结论，未修改实现或测试，未操作真实书、真实模型、Runtime、8877 或 Git，未派代理。
