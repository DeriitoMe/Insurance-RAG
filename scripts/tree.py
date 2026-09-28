"""打印项目目录树（跳过 node_modules 等）。"""

from __future__ import annotations

import sys
from pathlib import Path

import _bootstrap  # noqa: F401

sys.stdout.reconfigure(encoding="utf-8")

SKIP_DIRS = {"node_modules", "__pycache__", ".git", ".npm-cache", ".vite", "dist"}
root = Path(_bootstrap.ROOT)


def size_str(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / 1024 / 1024:.1f} MB"


def is_skipped(p: Path) -> bool:
    return any(part in SKIP_DIRS for part in p.parts)


lines: list[str] = ["insurance-rag/"]


def walk(d: Path, prefix: str = "") -> None:
    entries = sorted(
        [e for e in d.iterdir() if e.name not in SKIP_DIRS],
        key=lambda p: (p.is_file(), p.name),
    )
    for i, e in enumerate(entries):
        last = i == len(entries) - 1
        conn = "└── " if last else "├── "
        if e.is_dir():
            lines.append(f"{prefix}{conn}{e.name}/")
            walk(e, prefix + ("    " if last else "│   "))
        else:
            try:
                s = e.stat().st_size
            except OSError:
                s = 0
            lines.append(f"{prefix}{conn}{e.name}  ({size_str(s)})")


walk(root)
print("\n".join(lines))

count = sum(1 for p in root.rglob("*") if p.is_file() and not is_skipped(p.relative_to(root)))
print()
print(f"总文件数（不含 node_modules / __pycache__ / dist）：{count}")

# 按类别统计
categories = {
    "Python 源码 (src/)": list((root / "src").rglob("*.py")),
    "Python 脚本 (scripts/)": list((root / "scripts").rglob("*.py")),
    "测试 (tests/)": list((root / "tests").rglob("*.py")),
    "前端源码 (web/src/)": [p for p in (root / "web" / "src").rglob("*") if p.is_file()],
    "文档 (docs/)": list((root / "docs").rglob("*.md")),
    "语料 (data/raw/)": [p for p in (root / "data" / "raw").iterdir() if p.is_file()],
}
print()
for name, items in categories.items():
    total = sum(p.stat().st_size for p in items if p.exists())
    print(f"  {name:26s} {len(items):>3} 个文件   {size_str(total)}")
