# Novel Domain Package V1 设计规格

## 1. 决策

完善 Novel Domain 是当前项目必须执行的主线。

《文明升阶》只承担真实回归样本、Benchmark 和验收证据的职责，不再作为项目主目标。当前不开发 Video、Script、Article Domain，也不继续扩展与小说闭环无关的通用 Core 概念。

## 2. 现状证据

### 已具备

- `creative_os/domains/novel.py` 已声明 Character、World、Chapter、Scene、Timeline、Foreshadow 等 Schema 名称。
- Narrative 子系统已经具备 Chapter Contract、ScenePlan、POV、Technology、EvidenceRef、审批和 Writer Admission。
- 状态子系统能够保存 Character、Event、Timeline、Hook、Information Boundary 的候选变化。
- Publication 子系统已经暴露出并验证了字数、碎章、重复段落、章节边界和版本物化问题。
- 《文明升阶》提供了真实长篇正文、人工修订和失败案例。

### 必须补齐

1. `NovelDomainPackage` 当前主要是字符串清单和文本模板，没有稳定的领域服务接口。
2. Novel、Narrative、Publication、State 的能力分散，调用方无法通过一个领域入口发现和执行完整闭环。
3. Scene 缺少 `narrative_purpose` 与 `essential_information`，无法区分小说表达和故事事实。
4. Chapter/Scene Planner 没有以完整戏剧单元为硬边界；真实验证中产生了 449 字、1162 字碎章和场景中段切章。
5. Reviewer 缺少统一的碎章、重复长段、弱结尾、跨章对话未闭合和人物状态漂移审查结果模型。
6. Compiler 没有把通过审查的正文统一编译为 Story Canon、Character State、Timeline、Foreshadow 和下一任务输入。
7. 人工修订没有自动形成可追溯 Lesson，系统无法从真实失败中改进领域规则。
8. `validation_runtime.py` 中存在全书流程演示，但演示不能替代生产领域接口和真实项目验收。

## 3. 领域边界

Novel Domain 负责：

- 小说领域模型与不变量；
- Story、Volume、Arc、Chapter、Scene 的规划语义；
- Character Arc、Timeline、Foreshadow、Information Boundary；
- 小说 Writer Contract；
- 小说级 Review 规则与问题分类；
- 通过稿到 Story Canon/Creative State 的编译投影；
- 小说生产经验 Lesson 的候选生成；
- 对外提供稳定的 Domain Facade。

Novel Domain 不负责：

- 通用 Project、Task、Workflow、Knowledge 存储；
- 模型供应商与模型调用；
- Web UI；
- 视频、剧本或文章表达；
- 未经审批直接改写 Canon；
- 把《文明升阶》的专有设定写入通用领域规则。

## 4. V1 最小闭环

```text
NovelProjectState
        ↓
NovelPlanner
        ↓
ChapterContract + ScenePlan
        ↓
NovelWriterAdmission
        ↓
Draft
        ↓
NovelReviewer
        ↓
ApprovedDraft
        ↓
NovelCompiler
        ↓
CanonPatch + StatePatch + LessonCandidate + NextTaskInput
```

所有写入继续遵守现有审批、证据引用和失败关闭规则。

## 5. 核心模型调整

### SceneContract

在现有字段上增加：

- `narrative_purpose: str`：该场景为什么存在。
- `essential_information: tuple[str, ...]`：无论媒介如何转换都不能丢失的故事事实。
- `emotional_change: str`：场景前后情绪状态变化。
- `closure: SceneClosure`：目标、冲突、选择、结果是否闭合。

### ChapterBoundary

- `entry_state`：本章继承的状态。
- `exit_state`：本章造成的新状态。
- `ending_function`：resolve、escalate、reveal、decision、hook。
- `dialogue_closed`：跨章切分是否截断同一轮对话。
- `dramatic_unit_closed`：因果链是否闭合。

### NovelReviewIssue

- `code`
- `severity`
- `scope`
- `evidence`
- `repair_kind`
- `blocking`

首批问题码固定为：

- `fragment_chapter`
- `duplicate_long_paragraph`
- `weak_chapter_boundary`
- `dialogue_cut`
- `dramatic_unit_incomplete`
- `character_state_drift`
- `timeline_conflict`
- `foreshadow_lifecycle_break`
- `essential_information_missing`

## 6. Domain Facade

新增 `NovelDomainService`，作为外部唯一稳定入口：

```python
class NovelDomainService:
    def plan_chapter(self, request: ChapterPlanningRequest) -> ChapterPlanResult: ...
    def admit_draft(self, request: NovelWriterRequest) -> WriterAdmissionResult: ...
    def write_draft(self, request: NovelWritingRequest, admission: object) -> NovelDraft: ...
    def review_draft(self, request: NovelReviewRequest) -> NovelReviewResult: ...
    def compile_approved(self, request: NovelCompileRequest) -> NovelCompileResult: ...
```

Facade 组合现有 Narrative、State、Publication 能力，不复制第二套事实源。

## 7. 实施顺序

1. 领域能力目录与 Facade：先解决“Novel Domain 到底提供什么”。
2. Scene/Chapter 不变量：先阻止碎章和错误切分进入 Writer。
3. Novel Reviewer：把《文明升阶》人工发现的问题变成机器可复现问题。
4. Novel Compiler：把通过稿回写 Story Canon 与 Creative State。
5. Lesson Candidate：记录 Draft、Issue、Repair、Final 的因果关系。
6. 《文明升阶》回归：只验证能力，不为项目写专有分支。

## 8. V1 验收标准

- 调用方只依赖 `NovelDomainService` 即可完成单章闭环。
- ScenePlan 必须包含叙事目的、必要信息和闭合状态。
- 已知碎章、重复段落和中段切章样本能被 Reviewer 稳定识别。
- 未通过 Review 的正文不能编译为 Canon。
- Compiler 产物带正文证据和版本指纹，且不能直接覆盖已批准事实。
- 一次人工修订能够形成结构化 Lesson Candidate。
- 《文明升阶》回归样本通过后，不需要在通用模块中出现作品专有名称。
