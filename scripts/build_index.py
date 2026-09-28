"""构建索引：加载语料 → 切分 → 向量化 → 落盘（向量 + BM25）。

用法：
    python scripts/build_index.py              # 有索引则复用，语料变了会提示
    python scripts/build_index.py --rebuild    # 强制重建（换了切分参数/embedding 模型必须用这个）
    python scripts/build_index.py --dump 3     # 顺便打印 3 个 chunk，检查切分质量

⚠️ 换了 embedding 模型或切分参数后，**必须 --rebuild**。
   否则向量空间和 chunk 边界都对不上，检索结果无意义。
"""

from __future__ import annotations

import argparse
import sys
import time
from collections import Counter

import _bootstrap  # noqa: F401

from policyrag.config import get_settings
from policyrag.embedding.base import build_embedder
from policyrag.index.bm25 import BM25Index
from policyrag.index.vector_store import NumpyVectorStore
from policyrag.ingest.chunker import chunk_document
from policyrag.ingest.loaders import load_documents


def main() -> int:
    ap = argparse.ArgumentParser(description="构建 RAG 索引")
    ap.add_argument("--rebuild", action="store_true", help="强制重建")
    ap.add_argument("--dump", type=int, default=0, help="打印前 N 个 chunk 供检查")
    args = ap.parse_args()

    settings = get_settings()
    index_dir = settings.index_dir

    if not args.rebuild:
        try:
            store = NumpyVectorStore()
            store.load(index_dir)
            print(
                f"[skip] 索引已存在（{store.size} 个 chunk，signature={store.signature}）。\n"
                f"       语料或参数有变动请加 --rebuild 强制重建。"
            )
            return 0
        except Exception:                                   # noqa: BLE001
            pass

    # ---------- 1. 加载 ----------
    print(f"[1/5] 加载语料：{settings.raw_dir}")
    docs, warnings = load_documents(settings.raw_dir)
    for w in warnings:
        print(f"      {w}")
    if not docs:
        print("[fail] 没有加载到任何语料。先运行：python scripts/make_sample_data.py")
        return 1
    for d in docs:
        print(f"      - {d.doc_id}  《{d.display_name}》  {d.doc_type}")

    # ---------- 2. 切分 ----------
    print(f"[2/5] 切分（max_chars={settings.chunk.max_chars}, min_chars={settings.chunk.min_chars}）")
    chunks = []
    for d in docs:
        cs = chunk_document(d, settings.chunk)
        chunks.extend(cs)
        print(f"      - {d.doc_id}: {len(cs)} 个 chunk，平均 {sum(c.char_len for c in cs)//max(1,len(cs))} 字")
    if not chunks:
        print("[fail] 切分结果为 0，检查语料结构")
        return 1

    lens = [c.char_len for c in chunks]
    print(f"      合计 {len(chunks)} 个 chunk，最短 {min(lens)}，最长 {max(lens)}，平均 {sum(lens)//len(lens)} 字")
    no_article = sum(1 for c in chunks if not c.article_no)
    if no_article:
        print(f"      [warn] {no_article} 个 chunk 没有识别出条款号，引用溯源会受影响")

    # ---------- 3. 向量化 ----------
    embedder = build_embedder(settings.embedding)
    print(f"[3/5] 向量化：provider={settings.embedding.provider} signature={embedder.signature}")
    if settings.embedding.provider == "hash":
        print("      [warn] 当前是 hash 兜底向量 —— 只能跑通链路，**评测数字没有意义**。")
        print("             换真实模型：设置 PR_EMB_PROVIDER=api 或 local 后 --rebuild")
    t0 = time.perf_counter()
    mat = embedder.embed_documents([c.text for c in chunks])
    print(f"      完成：shape={mat.shape}，耗时 {time.perf_counter()-t0:.1f}s")

    # ---------- 4. 落盘 ----------
    print(f"[4/5] 保存索引：{index_dir}")
    store = NumpyVectorStore()
    store.build(chunks, mat, signature=embedder.signature)
    store.save(index_dir)
    bm25 = BM25Index()
    bm25.build(chunks)
    bm25.save(index_dir)
    print(f"      vectors.npz / meta.json / bm25.json 已写入")

    # ---------- 5. 自检 ----------
    print("[5/5] 自检：用已知问题测召回")
    from policyrag.pipeline import Pipeline

    p = Pipeline(settings=settings)
    probes = [
        ("等待期是多少天", "sample-anxin-2024"),
        ("免赔额是多少", "sample-anxin-2024"),
        ("甲状腺结节能赔吗", "sample-kangjian-2024"),
    ]
    for q, doc in probes:
        hits = p.retriever.search_vector(q, top_k=3)
        top = hits[0] if hits else None
        label = top.chunk.citation_label() if top else "（无结果）"
        print(f"      「{q}」 → {label}")

    if args.dump:
        print(f"\n--- 前 {args.dump} 个 chunk 内容 ---")
        for c in chunks[: args.dump]:
            print(f"\n[{c.chunk_id}] path={' > '.join(c.section_path)}")
            print(f"article_no={c.article_no!r} article_title={c.article_title!r} len={c.char_len}")
            print(c.text[:400])

    print("\n[ok] 索引构建完成。下一步：python scripts/cli.py ask \"等待期是多少天\"")
    return 0


if __name__ == "__main__":
    sys.exit(main())
