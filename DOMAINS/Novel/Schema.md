# Novel Schema

Novel 是 Creative OS V1 的第一个 Domain Package。

## 核心对象

- Character
- World
- Chapter
- Scene
- Timeline
- Relationship
- Foreshadow
- Conflict
- Style

## Schema Definition

### Character

Required:

- name
- role
- goal
- state

Optional:

- conflict
- relations
- hooks

### World

Required:

- rule
- scope
- limit
- evidence

Optional:

- source
- risk

### Chapter

Required:

- chapter
- goal
- scenes
- knowledge_updates

Optional:

- hooks
- summary

### Scene

Required:

- scene
- goal
- characters
- conflict
- outcome

Optional:

- setting
- foreshadow

### Timeline

Required:

- time
- event
- impact

Optional:

- chapter
- scene

### Relationship

Required:

- source
- target
- relation

Optional:

- status
- evidence

### Foreshadow

Required:

- hook
- source
- status

Optional:

- resolution
- risk

### Conflict

Required:

- subject
- opponent
- stakes

Optional:

- resolution
- chapter

### Style

Required:

- tone
- pace
- constraints

Optional:

- examples

## 原则

小说领域结构只存在于 Novel Package，不写入 Foundation。

## M12 验收点

- Novel Package 定义完整核心对象。
- 每个核心对象有 required fields。
- Schema 通过 `NovelDomainPackage.schema_definition()` 读取。
