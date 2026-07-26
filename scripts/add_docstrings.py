"""One-off script to add missing function docstrings."""

import ast
from pathlib import Path

SKIP_PARTS = {"migrations", ".venv", "__pycache__"}


def describe(name: str) -> str:
    """根据函数名生成一行 docstring 文案。

    Args:
        name (str): 函数名。

    Returns:
        str: 单行 summary 文案。
    """
    if name == "setUp":
        return "准备测试数据。"
    if name == "__init__":
        return "初始化 middleware。"
    if name == "__call__":
        return "处理请求并注入 request_id。"
    if name == "ready":
        return "应用启动钩子。"
    if name == "main":
        return "Django 管理命令入口。"
    if name.startswith("test_"):
        return f"验证：{name.removeprefix('test_').replace('_', ' ')}。"
    if name.startswith("_"):
        readable = name.lstrip("_").replace("_", " ")
        return f"{readable}。"
    readable = name.replace("_", " ")
    return f"{readable}。"


def insert_docstring(source: str, node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """在函数定义后插入 docstring。

    Args:
        source (str): 源文件内容。
        node (FunctionDef | AsyncFunctionDef): 目标函数 AST 节点。

    Returns:
        str: 插入 docstring 后的源文件内容。
    """
    indent = " " * node.col_offset
    doc_lines = f'{indent}"""{describe(node.name)}"""\n'
    lines = source.splitlines(keepends=True)
    idx = node.lineno - 1
    while idx < len(lines) and not lines[idx].rstrip().endswith(":"):
        idx += 1
    insert_idx = idx + 1
    return "".join(lines[:insert_idx] + [doc_lines] + lines[insert_idx:])


def process_file(path: Path) -> bool:
    """为单个文件中缺失 docstring 的函数补全说明。

    Args:
        path (Path): Python 源文件路径。

    Returns:
        bool: 有改动时返回 ``True``。
    """
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    funcs = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        and ast.get_docstring(node) is None
    ]
    if not funcs:
        return False
    funcs.sort(key=lambda node: node.lineno, reverse=True)
    updated = source
    for node in funcs:
        updated = insert_docstring(updated, node)
    path.write_text(updated, encoding="utf-8")
    return True


def main() -> None:
    """扫描项目并为缺失 docstring 的函数批量补全。"""
    changed: list[str] = []
    for path in sorted(Path(".").rglob("*.py")):
        if SKIP_PARTS & set(path.parts):
            continue
        if "migrations" in path.parts or path.name == "__init__.py":
            continue
        if process_file(path):
            changed.append(str(path))
    print(f"Updated {len(changed)} files")
    for item in changed:
        print(item)


if __name__ == "__main__":
    main()
