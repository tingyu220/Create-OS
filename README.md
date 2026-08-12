# Creative OS V1

Creative OS V1 是一个知识驱动的长期创作系统底座。

正式执行依据：[EXECUTION_PLAN.md](EXECUTION_PLAN.md)

核心流水线：

```text
                 Knowledge
                     ▲
                     │
              Compiler Update
                     ▲
                     │
Capability ◀──── Context ──── Retriever
     ▲               ▲              ▲
     │               │              │
     │         Project State         │
     │               ▲              │
     │               │              │
     └────── Task ◀── Workflow ◀── Domain
                     ▲
                     │
                    User
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

## 新开一本小说

使用书名作为项目总文件夹：

```powershell
python scripts\create_novel_project.py --title 雾城回声 --author 田雨 --genre 悬疑
```

生成路径：`projects\雾城回声\`

## 导出正式发布版

研发目录会保留完整过程产物；正式发布版使用单独导出目录，方便直接找正文：

```powershell
python scripts\export_novel_release.py --project-root projects\validation_novel --output-root releases
```

正式新书项目使用书名目录：

```powershell
python scripts\export_novel_release.py --project-root projects\雾城回声 --output-root releases
```

生成路径：

```text
releases\雾城回声\
├─ README.md
├─ book.md
├─ chapters\
├─ metadata.json
└─ reports\
```

## 查看控制台任务面板

章节生成或重写任务会写入统一状态文件，之后可以用控制台查看进度：

```powershell
python scripts\novel_console.py --project-root projects\雾城回声
```
