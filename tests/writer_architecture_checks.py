"""仅检查 Writer 透明委派契约；静态约束不等于 Python 运行时安全边界。"""

import ast
from copy import deepcopy
from pathlib import PurePosixPath


ADAPTER = "creative_os.writer_context_sources.CapturingModelAdapter"
RUNNER = "creative_os.runtime.runner.RuntimeRunner"
ADAPTER_FILE = "creative_os/writer_context_sources.py"
CALLER_FILE = "creative_os/agent_runtime.py"
CALLER = "WriterAgentRuntime._run"
CONTROLLED_CALLER = "WriterAgentRuntime._execute_story_step"


def validate_combat_loops(sources):
    """领域循环仅调用注入单步；保留原透明适配器的更严格检查。"""
    validate_transparent_delegate(sources)
    for module, name, maximum in (("combat_agent", "run_combat_expert", 4),
                                  ("chapter_agent_tools", "run_chapter_turn", 6),
                                  ("story_architecture_agent", "run_story_turn", 6)):
        tree = ast.parse(sources[f"creative_os/{module}.py"])
        function = qualified_definitions(tree)[name]
        constants = {node.targets[0].id: node.value.value for node in tree.body
                     if isinstance(node, ast.Assign) and len(node.targets) == 1
                     and isinstance(node.targets[0], ast.Name) and isinstance(node.value, ast.Constant)}
        assert constants.get("MAX_STEPS") == maximum, "unexpected domain step budget"
        assert not any(isinstance(node, (ast.While, ast.AsyncFor)) for node in ast.walk(tree)), "unbounded domain loop"
        loops = [node for node in ast.walk(function) if isinstance(node, ast.For)
                 and ast.unparse(node.iter) == "range(1, MAX_STEPS + 1)"]
        assert len(loops) == 1, "missing bounded domain loop"
        for call in (node for node in ast.walk(tree) if isinstance(node, ast.Call)):
            called = ast.unparse(call.func)
            assert not called.endswith((".complete", ".execute", ".client_factory", ".from_env")), "domain creates a model exit"
            assert "RuntimeRunner" not in called and "CapturingModelAdapter" not in called, "domain owns runtime adapter"


def qualified_definitions(tree):
    """使用类和函数的词法路径，避免不同类的同名方法互相覆盖。"""
    definitions = {}

    def visit(node, prefix=()):
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            prefix = (*prefix, node.name)
            key = ".".join(prefix)
            assert key not in definitions, f"ambiguous AST definition: {key}"
            definitions[key] = node
        for child in ast.iter_child_nodes(node):
            visit(child, prefix)

    visit(tree)
    return definitions


def signature(name, node):
    args = node.args
    parts = [arg.arg for arg in args.posonlyargs]
    if parts:
        parts.append("/")
    parts.extend(arg.arg for arg in args.args)
    if args.vararg:
        parts.append("*" + args.vararg.arg)
    elif args.kwonlyargs:
        parts.append("*")
    parts.extend(arg.arg for arg in args.kwonlyargs)
    if args.kwarg:
        parts.append("**" + args.kwarg.arg)
    return f"{name}({','.join(parts)})"


def module_name(path):
    parts = list(PurePosixPath(path).with_suffix("").parts)
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def _imports(tree, module, is_package):
    result = {}

    def bind(name, symbol):
        previous = result.get(name)
        related = lambda value: value is not None and (value.endswith((".CapturingModelAdapter", ".RuntimeRunner")) or ADAPTER.startswith(value + ".") or RUNNER.startswith(value + "."))
        assert previous in {None, symbol} or not (related(previous) or related(symbol)), "ambiguous protected import alias"
        result[name] = symbol

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                bind(alias.asname or alias.name.split(".")[0], alias.name if alias.asname else alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                package = module.split(".") if is_package else module.split(".")[:-1]
                base = ".".join(package[:len(package) - node.level + 1] + ([base] if base else []))
            for alias in node.names:
                assert not (alias.name == "*" and base in {"creative_os", "creative_os.writer_context_sources", "creative_os.agent_runtime"}), "delegate wildcard import"
                bind(alias.asname or alias.name, f"{base}.{alias.name}")
    return result


def _without_docstring(node):
    node = deepcopy(node)
    for item in ast.walk(node):
        if isinstance(item, (ast.ClassDef, ast.FunctionDef)) and item.body and isinstance(item.body[0], ast.Expr) and isinstance(item.body[0].value, ast.Constant) and isinstance(item.body[0].value.value, str):
            item.body.pop(0)
    return node


def validate_transparent_delegate(sources):
    trees = {path: ast.parse(source) for path, source in sources.items()}
    actual_class = qualified_definitions(trees[ADAPTER_FILE])["CapturingModelAdapter"]
    expected_class = ast.parse("""class CapturingModelAdapter:
    def __init__(self, client, capture):
        self.client, self.capture = client, capture
    def complete(self, messages, **kwargs):
        self.capture(messages)
        return self.client.complete(messages, **kwargs)
""").body[0]
    # 整个透明类限定为原样保存依赖、先观察再一次委派；拒绝额外路径及改参。
    assert ast.dump(_without_docstring(actual_class)) == ast.dump(expected_class), "delegate is not transparent"
    imports = {path: _imports(tree, module_name(path), PurePosixPath(path).stem == "__init__") for path, tree in trees.items()}
    exports = {f"{module_name(path)}.{name}": symbol for path, aliases in imports.items() for name, symbol in aliases.items()}

    def canonical(symbol):
        # 解析导入别名和已知模块再导出，不推断任意动态赋值。
        seen = set()
        while symbol not in seen:
            seen.add(symbol)
            parts = symbol.split(".")
            for index in range(len(parts), 0, -1):
                key = ".".join(parts[:index])
                if key in exports:
                    replacement = ".".join([exports[key], *parts[index:]])
                    if replacement != symbol:
                        symbol = replacement
                        break
            else:
                return symbol
        raise AssertionError("delegate import cycle")

    delegate_modules = {ADAPTER.rsplit(".", 1)[0]}
    delegate_modules.update(name.rsplit(".", 1)[0] for name, value in exports.items() if canonical(value) == ADAPTER)

    def delegate_namespace(symbol):
        return any(module == symbol or module.startswith(symbol + ".") for module in delegate_modules)

    constructions = {CALLER: 0, CONTROLLED_CALLER: 0}
    for path, tree in trees.items():
        aliases = imports[path]
        parents = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
        definitions = qualified_definitions(tree)
        function_names = {id(node): name for name, node in definitions.items() if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}

        def resolve(node):
            if isinstance(node, ast.Name):
                return canonical(aliases.get(node.id, node.id))
            if isinstance(node, ast.Attribute):
                return canonical(f"{resolve(node.value)}.{node.attr}")
            return ""

        def protected(symbol):
            return symbol in {ADAPTER, RUNNER} or delegate_namespace(symbol) or RUNNER.startswith(symbol + ".")

        # 类的直接导入或跨模块再导出，仅允许既有 Writer 模块消费。
        for symbol in aliases.values():
            if canonical(symbol) == ADAPTER:
                assert path == CALLER_FILE, "delegate imported outside Writer"
        for node in ast.walk(tree):
            if isinstance(node, ast.arg) and node.arg in aliases:
                assert not protected(canonical(aliases[node.arg])), "delegate/Runner import shadowed by argument"
            if isinstance(node, ast.ExceptHandler) and node.name in aliases:
                assert not protected(canonical(aliases[node.name])), "delegate/Runner import shadowed by exception"
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in aliases:
                assert not protected(canonical(aliases[node.name])), "delegate/Runner import shadowed by definition"
            if not isinstance(node, (ast.Name, ast.Attribute)):
                continue
            symbol = resolve(node)
            if isinstance(node.ctx, (ast.Store, ast.Del)):
                assert not protected(symbol), "delegate/Runner import reassigned"
            if symbol.startswith(ADAPTER + "."):
                raise AssertionError("delegate method reference escaped")
            if symbol == ADAPTER:
                constructor = parents.get(node)
                assert isinstance(constructor, ast.Call) and constructor.func is node, "delegate class escaped"
                assert path == CALLER_FILE, "delegate constructed outside Writer"
                owner, cursor = None, constructor
                while cursor in parents:
                    cursor = parents[cursor]
                    assert not isinstance(cursor, (ast.For, ast.AsyncFor, ast.While, ast.comprehension)), "delegate construction in loop"
                    if isinstance(cursor, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        owner = function_names[id(cursor)]
                        break
                assert owner in constructions, "delegate constructed outside declared Writer entry"
                outer = parents.get(constructor)
                # 仅允许直接占据 execute 的 adapter 参数，禁止赋值、转交或直接 complete。
                if isinstance(outer, ast.keyword):
                    assert outer.arg == "adapter", "delegate in wrong keyword"
                    outer = parents.get(outer)
                    adapter_argument = True
                else:
                    adapter_argument = isinstance(outer, ast.Call) and len(outer.args) >= 2 and outer.args[1] is constructor
                assert adapter_argument and isinstance(outer, ast.Call), "delegate not immediate adapter argument"
                method = outer.func
                assert isinstance(method, ast.Attribute) and method.attr == "execute", "delegate sent to other entry"
                assert isinstance(method.value, ast.Call) and resolve(method.value.func) == RUNNER, "delegate not passed to RuntimeRunner"
                constructions[owner] += 1
            elif symbol and delegate_namespace(symbol):
                parent = parents.get(node)
                assert isinstance(parent, ast.Attribute) and parent.value is node, "delegate module escaped"
    assert all(count == 1 for count in constructions.values()), "Writer must have exactly one delegate construction per declared entry"
