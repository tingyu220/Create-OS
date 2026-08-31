# SDD ledger — plan: docs/superpowers/plans/2026-08-31-novel-real-writer-integration.md

## Pre-flight interface scan

| Scope | Producer → Consumer | Finding |
|---|---|---|
| Task 1 | `build_novel_writer_messages` → Task 2 adapter | Clean: deterministic list of `ModelMessage`. |
| Task 2 | `LLMNovelWriterAdapter`, config, telemetry → Tasks 3 and 5 | Clean: adapter owns model/output validation; observer is optional. |
| Task 3 | service factories → live composition | Clean: thin wrappers preserve existing `NovelDomainService`. |
| Task 4 | `IndependentNovelValidationCase` → Task 5 runner | Clean: project-backed fixture owns story-specific data. |
| Task 5 | validation runner/CLI → Task 6 evidence | Clean: report schema is fixed and redacted. |
| Task 6 | Fake/live reports → roadmap and next-stage gate | Clean: live success is mandatory before visualization projection work. |
| Tasks 1↔2 | prompt function consumed by adapter | Clean: signatures agree. |
| Tasks 2↔3 | adapter constructed by composition | Clean: `client/config/observer` parameters agree. |
| Tasks 2↔5 | telemetry consumed by report builder | Clean: report only uses declared scalar telemetry. |
| Tasks 3↔5 | both compose Writer/service | Ruling: validation runner may compose in memory but must use the same `LLMNovelWriterAdapter`; it must not duplicate environment factories — wrong ruling would allow composition drift. |
| Tasks 4↔5 | fixture path and case model | Clean: CLI accepts the project validation JSON path. |
| Tasks 5↔6 | report path and status fields | Clean: `compile_candidate_ready` and `review_passed` are shared gates. |

Pre-flight complete at commit `a40c162`.

Task 1: minor (deferred): `novel_writer_prompt.py:27` 存在未使用局部变量 `info`；不影响协议，交最终审查统一裁决。
Task 1: complete (commits a40c162..a704de0, review clean with 1 deferred minor)
Task 2: Ruling: 模型调用经现有 `RuntimeRunner.execute` 唯一出口，而非计划片段中的直接 `ModelClient.complete` — 保持主线 Writer 架构不被绕过 — 若判断错误会增加适配层耦合。
Task 2: complete (commits a704de0..0f80956, review clean)
Task 3: minor (deferred): 环境工厂测试未显式断言 `env_file` 透传和单次 `from_env` 调用；交最终审查统一裁决。
Task 3: complete (commits 0f80956..16de810, review clean with 1 deferred minor)
Task 4: Ruling: 基线证据同时绑定项目元数据声明的 `source_id`、来源文件 SHA-256 与 JSON Pointer 断言 — 仅校验哈希不足以阻止合法项目内文件替换 — 若判断错误会使独立验证证据可被语义替换。
Task 4: complete (commits 16de810..82f4f09, 20 tests passed; two Important findings fixed; final agent review unavailable due usage limit, controller verified targeted regression and diff check)
Task 5: complete (commits 82f4f09..2392501, review clean; 41 implementer regression tests and 9 reviewer target tests passed)
Task 6: complete (提交 2a0eea7，独立审查 clean，1254 passed/8 skipped，live blocked_missing_configuration)

Deferred minor 清理：
- Task 1：删除 `novel_writer_prompt.py` 中未使用的局部变量 `info`，消息协议保持不变。
- Task 3：补充环境工厂测试，显式锁定 `env_file` 透传及 `OpenAICompatibleClient.from_env` 单次调用；现有实现符合契约。
- 两项 deferred minor 已关闭。
