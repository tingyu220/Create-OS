# Writer 透明模型委派的静态架构约束

2026-10-18。分支 `codex/writer-agent-conversation-v1`，HEAD `c67d87c`。仅补齐架构清单、扫描及隔离验证，生产业务实现保持不变。

## 问题与调用图

真实调用图为 `WriterAgentRuntime._run → RuntimeRunner.execute → CapturingModelAdapter.complete → client.complete`。Runner 仍是唯一业务执行入口；Source 透明适配器只观察实际消息，然后转交原请求。

原 v1 清单只声明 Runner 的模型调用位置，遗漏新增的透明委派，所以架构失败是真实的清单/扫描缺口，不应忽略或仅加白名单。

## 约束

- 保留 v1，新增 `tests/assets/writer_production_exits_v2.json`。透明条目使用完整符号 `creative_os.writer_context_sources.CapturingModelAdapter.complete`，标记 `transparent_delegate`，指定唯一业务入口与合法构造者。
- 定义使用类/函数词法路径定位，避免不同类的同名方法相互覆盖；签名包括位置参数、关键字参数、`*args` 和 `**kwargs`。
- 透明类的 AST 只能保存原 client/capture 依赖，`complete(self,messages,**kwargs)` 必须先调用 `self.capture(messages)`，然后一次 `return self.client.complete(messages,**kwargs)`。不允许改写参数、额外调用、循环、分支或其他执行路径。
- 解析生产代码中的直接、模块、相对导入别名及已知模块再导出。捕获类只能由既有 Writer 模块导入，并且只能在 `WriterAgentRuntime._run` 内构建，立即作为 `RuntimeRunner(...).execute` 的 adapter 参数。
- 拒绝保存捕获类/实例/绑定方法、交给其他入口、直接 `.complete`、受保护导入重绑定和构造循环。检查整份生产代码，不能只声明两个模型调用位置就放行。
- 保留原有正式稿写入点、受保护生产入口及准入令牌检查，没有放宽其他出口约束。

## 行为验证

反例覆盖直接调用、导入别名、模块别名、相对导入、再导出、赋值逃逸、改入口、错误参数位置、消息/kwargs 改写、重复调用、循环与分支；正例覆盖合法透明委派和合法导入别名。

实际运行隔离的 `WriterAgentRuntime → RuntimeRunner → CapturingModelAdapter` 链路，而不只是单独测试 wrapper：

- Runner 校验拒绝时，捕获回调和 Fake Client 调用均为 0，没有模型执行记录；任务明确失败。
- 合法执行顺序为 validate、capture、client，参数不变，成功记录关联实际任务。
- Fake Client 抛错时保留 Runner 的 failed 记录及真实错误，候选不写入工作稿。

全部测试使用临时项目及 Fake Client，没有生产数据写入或真实付费调用。

验证结果：全部 `test_writer*.py`、Agent/Conversation/Proposal、CreativeContext、Web Workspace、Runtime 相关测试合计 **221 项 Python 通过**；全部 Writer 页面行为 **29 项通过**，`git diff --check` 通过。覆盖原失败架构用例及字数功能，本轮没有剩余的原 `187+1` 架构失败。新增透明委派静态与动态测试为 30 项，包含 3 项实际 Writer 调用链测试，以及直接模块和再导出模块的赋值/查找逃逸反例。

## 文件范围与限制

修改 `tests/test_writer_production_exit_architecture.py`；新增 v2 manifest、`tests/writer_architecture_checks.py`、`tests/test_writer_transparent_delegate_architecture.py` 和本文档。v1 未删除，生产 Runner、Writer、Source 适配器均未修改。

这是对受支持静态代码模式的架构约束，不是 Python 运行时安全门禁。动态反射、运行时替换或直接在解释器中调用 wrapper 仍然可行，与原 client 直接调用属于同类能力；不能据此声称所有动态绕过均被禁止。本轮没有新权限体系或生产重构。复杂动态写法应显式进入审查，不作为自动解析器的支持目标。

DONE：版本化声明、透明性及受限调用位置检查、负例与真实链路隔离验证。

CURRENT：相关回归与交付，等待总控安排独立复审。

TODO：由总控进行架构独立复审；本轮不提交、推送或合并。
