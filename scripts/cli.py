"""命令行问答 —— 最快的验证入口。

用法：
    python scripts/cli.py ask "等待期是多少天"
    python scripts/cli.py ask "甲状腺结节能赔吗" --mode vector
    python scripts/cli.py compare "等待期是多少天"     # 三种检索模式对照
    python scripts/cli.py products
"""

from __future__ import annotations

import argparse
import sys

import _bootstrap  # noqa: F401

from policyrag.config import get_settings
from policyrag.pipeline import Pipeline


def _print_answer(ans) -> None:
    print("=" * 70)
    print(f"问题：{ans.question}")
    print("-" * 70)
    print(f"回答：{ans.answer}")
    print("-" * 70)
    print(f"可答：{ans.answerable}   耗时：{ans.latency_ms}ms   缓存：{ans.debug.get('cache_hit')}")
    if ans.debug.get("recall_ms") is not None:
        print(f"检索：{ans.debug.get('recall_ms')}ms  召回 {ans.debug.get('recall_count')} 个块")
    if ans.citations:
        print("引用：")
        for c in ans.citations:
            # citation_label() 已经包含产品名、条号与条标题，不要再拼一次
            label = (c.product_name or "").strip()
            if c.article_no and c.article_no not in label:
                label = f"{label} {c.article_no}".strip()
            if c.article_title and c.article_title not in label:
                label = f"{label} {c.article_title}".strip()
            print(f"  - {label}")
            if c.quote:
                print(f"    「{c.quote[:70]}」")
    print("=" * 70)


def main() -> int:
    ap = argparse.ArgumentParser(description="保险条款 RAG 命令行")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_ask = sub.add_parser("ask", help="提问")
    p_ask.add_argument("question")
    p_ask.add_argument("--mode", default="hybrid", choices=["hybrid", "vector", "keyword"])
    p_ask.add_argument("--top-k", type=int, default=None)
    p_ask.add_argument("--top-n", type=int, default=None)
    p_ask.add_argument("--docs", nargs="*", default=None, help="限定产品 doc_id")

    p_cmp = sub.add_parser("compare", help="三种检索模式对照（评测用）")
    p_cmp.add_argument("question")

    sub.add_parser("products", help="列出已入库产品")

    args = ap.parse_args()
    p = Pipeline(settings=get_settings())

    if not p.index_ready:
        print("[fail] 索引未就绪。先运行：python scripts/build_index.py")
        return 1

    if args.cmd == "products":
        for item in p.list_products():
            print(f"{item['doc_id']:32s} {item['product_name']:24s} {item['chunks']:4d} chunks")
        return 0

    if args.cmd == "ask":
        try:
            ans = p.ask(args.question, mode=args.mode, top_k=args.top_k, top_n=args.top_n,
                        doc_ids=args.docs)
        except ValueError as e:
            # 参数错误（比如 doc_id 不存在）打成人话，不要抛堆栈
            print(f"\n[参数错误] {e}\n")
            return 1
        _print_answer(ans)
        return 0

    if args.cmd == "compare":
        try:
            for mode in ("vector", "keyword", "hybrid"):
                chunks, debug = p.retriever.retrieve(args.question, mode=mode, top_n=5)
                print(f"\n### mode={mode}  召回 {debug.get('recall_count')} 个块，{debug.get('recall_ms')}ms")
                for i, rc in enumerate(chunks, 1):
                    label = rc.chunk.citation_label()
                    print(f"  {i}. [{rc.score:.4f}] {label}")
                    print(f"     {rc.chunk.raw_text[:90].replace(chr(10), ' ')}")
        except ValueError as e:
            print(f"\n[参数错误] {e}\n")
            return 1
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
