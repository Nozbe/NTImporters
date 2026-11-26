"""generated client under argv[1] slimmed in place: docstrings (incl. attribute ones),
*_with_http_info and *_without_preload_content methods removed (emptied body: pass)"""

import ast
import sys
from pathlib import Path

VARIANTS = ("_with_http_info", "_without_preload_content")
SCOPES = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)


def _span(node: ast.stmt) -> tuple[int, int]:
    """(first, last line) incl. decorators"""
    decorators = getattr(node, "decorator_list", [])
    return min([node.lineno, *(dec.lineno for dec in decorators)]), node.end_lineno


def _is_text(node: ast.stmt) -> bool:
    """bare string statement: docstring or attribute docstring"""
    return isinstance(node, ast.Expr) and isinstance(getattr(node.value, "value", None), str)


def cuts(tree: ast.Module) -> list[tuple[int, int, str]]:
    """(first, last line, replacement): 1-based, inclusive, disjoint, last first"""
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, SCOPES):
            continue
        dropped = [
            elt
            for elt in node.body
            if _is_text(elt)
            or isinstance(node, ast.ClassDef)
            and isinstance(elt, ast.FunctionDef)
            and elt.name.endswith(VARIANTS)
        ]
        for elt in dropped:
            pad = " " * elt.col_offset
            emptied = len(dropped) == len(node.body) and elt is dropped[0]
            found.append((*_span(elt), f"{pad}pass\n" if emptied else ""))
    outer = [
        cut
        for cut in found
        if not any(o[0] <= cut[0] and cut[1] <= o[1] and o != cut for o in found)
    ]
    return sorted(outer, reverse=True)


for path in Path(sys.argv[1]).rglob("*.py"):
    lines = path.read_text().splitlines(keepends=True)
    for first, last, replacement in cuts(ast.parse("".join(lines))):
        lines[first - 1 : last] = [replacement] if replacement else []
    path.write_text("".join(lines))
