"""Fix docstring indentation inserted at column 0."""

from pathlib import Path


def fix_file(path: Path) -> bool:
    """修正函数体 docstring 的缩进。

    Args:
        path (Path): Python 源文件路径。

    Returns:
        bool: 有改动时返回 ``True``。
    """
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    changed = False
    idx = 0
    while idx < len(lines):
        line = lines[idx]
        stripped = line.lstrip()
        if stripped.startswith("def ") and line.rstrip().endswith(":"):
            def_indent = len(line) - len(stripped)
            if idx + 1 < len(lines):
                next_line = lines[idx + 1]
                next_stripped = next_line.lstrip()
                if next_stripped.startswith('"""') or next_stripped.startswith("'''"):
                    doc_indent = len(next_line) - len(next_stripped)
                    expected = def_indent + 4
                    if doc_indent < expected:
                        lines[idx + 1] = (" " * expected) + next_stripped
                        changed = True
        idx += 1
    if changed:
        path.write_text("".join(lines), encoding="utf-8")
    return changed


def main() -> None:
    """扫描并修正仓库内 Python 文件的 docstring 缩进。"""
    for path in Path(".").rglob("*.py"):
        if ".venv" in path.parts or "migrations" in path.parts:
            continue
        if fix_file(path):
            print(path)


if __name__ == "__main__":
    main()
