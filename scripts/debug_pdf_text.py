"""诊断：把 pypdf 抽出的文本按「可见符号」打印出来。

目的：看清 pypdf 到底给了什么分隔符 —— 页与页之间是 \\f 还是什么都没有。
这决定了页眉检测该用「按页处理」还是「按重复次数」。

用法：python scripts/debug_pdf_text.py data/samples/测试条款.pdf
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import _bootstrap  # noqa: F401


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--pages", type=int, default=3)
    args = ap.parse_args()

    path = Path(args.file)
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    n = min(args.pages, len(reader.pages))

    print("=" * 72)
    print("逐页抽取（每页独立），并显示不可见字符")
    print("=" * 72)

    for i in range(n):
        t = reader.pages[i].extract_text() or ""
        print(f"\n----- 第 {i + 1} 页（{len(t)} 字）-----")
        for ln in t.split("\n"):
            # 把制表、回车、换页显示成可见符号
            vis = ln.replace("\t", "\\t").replace("\r", "\\r").replace("\f", "\\f")
            vis = vis.rstrip(" ") + ("␣" * (len(ln) - len(ln.rstrip(" "))) if ln != ln.rstrip(" ") else "")
            print(f"  | {vis}")

    # 合并后再看，判断页与页之间有没有 \f
    merged = "\n".join((reader.pages[i].extract_text() or "") for i in range(n))
    print()
    print("=" * 72)
    print("合并全文后，检查分隔符")
    print("=" * 72)
    print(f"  总长          : {len(merged)}")
    print(f"  含 \\f (换页符): {merged.count(chr(12))} 个")
    print(f"  含 \\n         : {merged.count(chr(10))} 个")
    print(f"  含 \\r         : {merged.count(chr(13))} 个")
    print(f"  含全角空格    : {merged.count(chr(0x3000))} 个")
    print(f"  含半角空格    : {merged.count(' ')} 个")

    if merged.count(chr(12)):
        print("\n  → 有换页符，可以按页处理页眉（最准）")
    else:
        print("\n  → 没有换页符，只能靠「重复次数 + 短 + 无句末标点」来猜页眉")

    return 0


if __name__ == "__main__":
    sys.exit(main())
