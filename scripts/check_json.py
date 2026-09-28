"""检查生成的 JSON 里「标题 / 正文」是否被正确分开。

用法：python scripts/check_json.py data/_testpdf/test-pdf-product.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import _bootstrap  # noqa: F401


def walk(nodes, path=None, out=None):
    path = path or []
    out = out if out is not None else []
    for n in nodes:
        p = path + [n.get("title", "")]
        if n.get("children"):
            walk(n["children"], p, out)
        else:
            out.append((p, n.get("text", "")))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    args = ap.parse_args()

    p = Path(args.file)
    if not p.exists():
        print(f"[fail] 文件不存在：{p}")
        return 1

    d = json.loads(p.read_text(encoding="utf-8"))
    items = walk(d.get("sections", []))

    print("=" * 70)
    print(f"doc_id       : {d.get('doc_id')}")
    print(f"product_name : {d.get('product_name')}")
    print(f"doc_type     : {d.get('doc_type')}")
    print(f"条款数       : {len(items)}")
    print("=" * 70)

    empty = 0
    for path, text in items:
        title = path[-1] if path else "?"
        body = text.strip()
        flag = ""
        if not body:
            flag = "  ← 没有正文！"
            empty += 1
        print(f"\n[{title}]{flag}")
        print(f"  层级：{' > '.join(path[:-1]) if len(path) > 1 else '（顶层）'}")
        print(f"  正文：{body[:100]}{'…' if len(body) > 100 else ''}")

    print()
    print("=" * 70)
    if empty:
        print(f"⚠️  有 {empty} 条没有正文，说明标题识别把正文吃掉了")
        return 1
    print("✓ 每条都有正文，标题与正文分离正确")
    return 0


if __name__ == "__main__":
    sys.exit(main())
