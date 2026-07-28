# Writing Capability

Writing 负责根据 Context 生成创作结果。

## 输入

- Context

## 输出

- Result

Result 要求：

```text
kind = writing
content = 生成内容
```

## 禁止

- 直接访问 Knowledge
- 直接读取文件
- 修改 State
- 绕过 Compiler 写入内容

## M9 验收点

- 输入只有 Context。
- 输出只有 Result。
- 不产生 Knowledge Draft。
- 不产生 Follow-up Task。
