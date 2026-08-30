# Task 4 报告：独立短篇样本夹具

## 状态

已完成：新增《末班钟表店》独立验收项目、严格 JSON loader 与回归测试。样本未复用既有《文明升阶》资产。

## 红绿测试

- 本次红：`pytest -q tests/test_novel_validation_fixture.py::test_loader_rejects_baseline_evidence_hash_that_does_not_match_source tests/test_novel_validation_fixture.py::test_loader_rejects_tampered_baseline_evidence_source`，两个用例均因旧 loader 放行而失败。
- 本次绿及相关回归：`pytest -q tests/test_novel_validation_fixture.py tests/test_novel_scene_contract.py tests/test_novel_domain_end_to_end.py`，18 passed。

## 文件结构

- `projects/novel_domain_validation/project.json`
- `projects/novel_domain_validation/brief.json`
- `projects/novel_domain_validation/validation/independent_short_story.json`
- `creative_os/domains/novel_validation_fixture.py`
- `tests/test_novel_validation_fixture.py`

## 严格校验

- 拒绝未知根字段、缺失或不一致的章节身份、空场景、未完成场景闭合。
- `baseline_evidence.source_id` 必须是项目根目录内的相对文件路径；loader 解析后拒绝绝对路径、路径穿越和符号链接逃逸，并按来源文件原始字节重算 SHA-256。
- 校验基线证据哈希、上下文指纹、Fake 正文 SHA-256、最小 2500 汉字边界和正文实际字数。
- 正文逐项包含 `essential_information`，并拒绝系统术语。

## 哈希绑定修复

- 基线来源由不可重算的 `brief:last-train-clockshop` 改为项目文件 `brief.json`，夹具已记录该文件原始字节的 SHA-256。
- 新增回归：伪造的 64 位哈希、来源文件遭篡改、以及 `source_id` 路径越界，均会使 loader 失败关闭。
- 验证：`pytest -q tests/test_novel_validation_fixture.py tests/test_novel_scene_contract.py tests/test_novel_domain_end_to_end.py`，18 passed。

## 自审

- 独立性：夹具 JSON 不包含既有作品专名；测试中的专名仅用于隔离断言。
- 完整性：Profile、章节规划、当前状态、基线证据、写作/准入请求、边界、角色变化及确定性正文均由不可变对象提供。
- 工程性：loader 仅负责解码与边界校验，复用既有 Narrative/Novel 领域模型，未引入耦合到具体作品的逻辑。

## 提交

待提交。
