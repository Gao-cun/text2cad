from __future__ import annotations

import ast
from dataclasses import dataclass, field

ALLOWED_IMPORT_ROOTS = {"__future__", "cadquery", "math", "typing"}
DISALLOWED_CALLS = {"open", "exec", "eval", "compile", "input", "__import__"}
DISALLOWED_ATTR_ROOTS = {"os", "sys", "subprocess", "shutil", "socket", "requests", "httpx", "pathlib"}
BUILD_ENTRYPOINTS = {"build_model", "build", "make_model"}
MODEL_VARIABLES = {"MODEL", "model"}
FORBIDDEN_BBOX_ATTRS = {"x0", "x1", "y0", "y1", "z0", "z1"}
CAD_MODULE_NAMES = {"cadquery", "cq"}


@dataclass
class StaticValidationResult:
    errors: list[str] = field(default_factory=list)
    syntax_ok: bool = True
    security_ok: bool = True


def _attribute_chain(node: ast.AST) -> list[str]:
    parts: list[str] = []
    current = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
    return list(reversed(parts))


class StaticCadValidator(ast.NodeVisitor):
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.syntax_ok = True
        self.security_ok = True
        self.import_aliases: dict[str, str] = {}
        self.has_entrypoint = False
        self.entrypoints_with_return: set[str] = set()
        self.uses_cadquery = False

    def _add_error(self, message: str, *, security: bool = False) -> None:
        if message not in self.errors:
            self.errors.append(message)
        if security:
            self.security_ok = False

    def _resolve_import_root(self, alias: str) -> str:
        return self.import_aliases.get(alias, alias)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            root = alias.name.split(".")[0]
            local_name = alias.asname or root
            self.import_aliases[local_name] = root
            if root not in ALLOWED_IMPORT_ROOTS:
                self._add_error(f"不允许导入模块: {alias.name}", security=True)
            if root == "cadquery":
                self.uses_cadquery = True
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ""
        root = module.split(".")[0]
        if any(alias.name == "*" for alias in node.names):
            self._add_error(f"不允许使用通配符导入: {module or '<unknown>'}")
        for alias in node.names:
            self.import_aliases[alias.asname or alias.name] = root
        if root not in ALLOWED_IMPORT_ROOTS:
            self._add_error(f"不允许 from-import 模块: {module}", security=True)
        if root == "cadquery":
            self.uses_cadquery = True
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if node.name in BUILD_ENTRYPOINTS:
            self.has_entrypoint = True
            has_return = any(isinstance(child, ast.Return) and child.value is not None for child in ast.walk(node))
            if has_return:
                self.entrypoints_with_return.add(node.name)
            else:
                self._add_error(f"入口函数 {node.name}() 必须返回一个 CadQuery 实体。")
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id in MODEL_VARIABLES:
                self.has_entrypoint = True
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if self._resolve_import_root(node.id) == "cadquery" or node.id in CAD_MODULE_NAMES:
            self.uses_cadquery = True
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name):
            if node.func.id in DISALLOWED_CALLS:
                self._add_error(f"不允许调用危险函数: {node.func.id}", security=True)
        else:
            chain = _attribute_chain(node.func)
            if chain:
                root = self._resolve_import_root(chain[0])
                if root in DISALLOWED_ATTR_ROOTS:
                    self._add_error(f"不允许调用危险模块 API: {'.'.join(chain)}", security=True)
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr in FORBIDDEN_BBOX_ATTRS:
            self._add_error(
                f"BoundingBox 属性 {node.attr} 不可用，请改用 xmin/xmax/ymin/ymax/zmin/zmax。"
            )

        if node.attr in {"X", "Y", "Z"} and isinstance(node.value, ast.Attribute) and node.value.attr in {"min", "max"}:
            self._add_error("不要使用 BoundingBox.min.X/max.X 风格访问，请改用 xmin/xmax/ymin/ymax/zmin/zmax。")

        self.generic_visit(node)


def collect_static_validation_result(code: str) -> StaticValidationResult:
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return StaticValidationResult(
            errors=[f"CAD 代码语法错误: {exc.msg} (line {exc.lineno})"],
            syntax_ok=False,
            security_ok=True,
        )

    validator = StaticCadValidator()
    validator.visit(tree)

    if not validator.has_entrypoint:
        validator.errors.append("CAD 代码必须定义 build_model()/build()/make_model() 或 MODEL/model。")
    if validator.has_entrypoint and not validator.entrypoints_with_return and not any(
        name in MODEL_VARIABLES for name in validator.import_aliases
    ):
        has_model_assignment = any(
            isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id in MODEL_VARIABLES for target in node.targets)
            for node in ast.walk(tree)
        )
        if not has_model_assignment:
            validator.errors.append("未检测到有效模型导出；入口函数需要返回实体，或显式赋值给 MODEL/model。")
    if not validator.uses_cadquery:
        validator.errors.append("未检测到 cadquery 几何构造，请确认代码确实在生成 CadQuery 实体。")

    return StaticValidationResult(
        errors=validator.errors,
        syntax_ok=validator.syntax_ok,
        security_ok=validator.security_ok,
    )
