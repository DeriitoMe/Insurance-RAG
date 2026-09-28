"""诊断 drop_running_headers：把每一步的中间状态打出来。

用法：python scripts/debug_headers.py data/samples/测试条款.pdf
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

import _bootstrap  # noqa: F401

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ingest import clean_lines, extract_pdf_text  # noqa: E402


def show(lines: list[str], title: str) -> None:
    print(f"\n--- {title} ---")
    for i, ln in enumerate(lines):
        vis = ln.replace("\f", "\\f")
        print(f"  [{i:>3}] {vis!r}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    args = ap.parse_args()

    text = extract_pdf_text(Path(args.file))
    print(f"抽取长度：{len(text)}")
    print(f"含 \\f ：{text.count(chr(12))} 个")
    print(f"含 \\n ：{text.count(chr(10))} 个")

    lines, stats = clean_lines(text, keep_formfeed=True)
    show(lines, f"clean_lines 之后（{len(lines)} 行）")
    print(f"\nstats = {stats}")

    joined = "\n".join(lines)
    print(f"\njoin 之后含 \\f ：{joined.count(chr(12))} 个")
    pages = joined.split("\f")
    print(f"按 \\f 切出的页数：{len(pages)}")

    for i, p in enumerate(pages):
        pl = [x.strip() for x in p.split("\n") if x.strip()]
        print(f"\n=== 第 {i + 1} 页（{len(pl)} 行）===")
        for j, ln in enumerate(pl):
            print(f"  {j}: {ln!r}")

    heads: list[str] = []
    tails: list[str] = []
    for p in pages:
        pl = [x.strip() for x in p.split("\n") if x.strip()]
        if not pl:
            continue
        heads.extend(pl[:2])
        tails.extend(pl[-2:])

    print("\n--- heads（每页前 2 行）---")
    for s, c in Counter(heads).most_common():
        print(f"  {c} 次  {s!r}")
    print("\n--- tails（每页后 2 行）---")
    for s, c in Counter(tails).most_common():
        print(f"  {c} 次  {s!r}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
