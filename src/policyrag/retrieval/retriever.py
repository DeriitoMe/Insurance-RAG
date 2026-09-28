"""检索器：向量 + BM25 → RRF 融合 → 可选 Rerank。

三种模式的对照（这是评测里最值得做的一组 A/B）：

  vector  : 纯向量             —— 语义好，编号/数字差
  keyword : 纯 BM25            —— 编号/数字准，同义表达差
  hybrid  : RRF 融合（默认）    —— 两者互补

RRF（Reciprocal Rank Fusion）：
    score(d) = Σ_i  1 / (k + rank_i(d))        k 默认 60

为什么用 RRF 而不是加权求和：
**它只用排名，不用分数**。向量相似度在 [-1,1]，BM25 分数是 [0, +∞)，
量纲完全不同，加权求和必须先归一化，而归一化方式又会引入新的超参。
RRF 直接绕开了这个问题 —— 这是工程上更稳的选择。
"""

from __future__ import annotations

import time

import numpy as np

from ..config import RetrievalConfig
from ..embedding.base import BaseEmbedder
from ..index.bm25 import BM25Index
from ..index.vector_store import NumpyVectorStore
from ..schema import Chunk, RetrievedChunk


class Retriever:
    def __init__(
        self,
        store: NumpyVectorStore,
        embedder: BaseEmbedder,
        bm25: BM25Index | None = None,
        cfg: RetrievalConfig | None = None,
    ) -> None:
        self.store = store
        self.embedder = embedder
        self.bm25 = bm25
        self.cfg = cfg or RetrievalConfig()
        self._reranker = None

    # ---------------- 单路检索 ----------------

    def search_vector(
        self, query: str, top_k: int, doc_filter: set[str] | None = None
    ) -> list[RetrievedChunk]:
        qv = self.embedder.embed_query(query)
        hits = self.store.search(qv, top_k=top_k, doc_filter=doc_filter)
        return [
            RetrievedChunk(chunk=self.store.chunks[i], score=s, source="vector", rank=r)
            for r, (i, s) in enumerate(hits)
        ]

    def search_keyword(self, query: str, top_k: int) -> list[RetrievedChunk]:
        if self.bm25 is None or not self.bm25.size:
            return []
        hits = self.bm25.search(query, top_k=top_k)
        out: list[RetrievedChunk] = []
        # BM25 的下标空间是它自己 build 时的 chunk 顺序，需映射回 store
        id_to_pos = {c.chunk_id: i for i, c in enumerate(self.store.chunks)}
        for r, (bidx, score) in enumerate(hits):
            cid = self.bm25.chunk_ids[bidx]
            pos = id_to_pos.get(cid)
            if pos is None:
                continue
            out.append(
                RetrievedChunk(
                    chunk=self.store.chunks[pos], score=score, source="bm25", rank=r
                )
            )
        return out

    # ---------------- RRF 融合 ----------------

    @staticmethod
    def _rrf_fuse(
        result_lists: list[list[RetrievedChunk]], k: int = 60
    ) -> list[RetrievedChunk]:
        acc: dict[str, float] = {}
        by_id: dict[str, RetrievedChunk] = {}
        for results in result_lists:
            for rank, rc in enumerate(results):
                cid = rc.chunk.chunk_id
                acc[cid] = acc.get(cid, 0.0) + 1.0 / (k + rank + 1)
                by_id.setdefault(cid, rc)
        fused = [
            RetrievedChunk(
                chunk=by_id[cid].chunk,
                score=score,
                source="hybrid",
                rank=r,
            )
            for r, (cid, score) in enumerate(
                sorted(acc.items(), key=lambda kv: -kv[1])
            )
        ]
        return fused

    # ---------------- Rerank ----------------

    def _load_reranker(self):
        """懒加载 reranker。装不上就降级并明确告知，不静默。"""
        if self._reranker is not None:
            return self._reranker
        try:
            from sentence_transformers import CrossEncoder

            self._reranker = CrossEncoder(self.cfg.rerank_model, device="cpu")
        except Exception as e:                              # noqa: BLE001
            print(
                f"[warn] Rerank 不可用，已跳过（原因：{type(e).__name__}: {e}）\n"
                f"       安装：pip install sentence-transformers，或用 api provider 的 rerank 接口"
            )
            self._reranker = False
        return self._reranker

    def rerank(self, query: str, candidates: list[RetrievedChunk], top_n: int) -> list[RetrievedChunk]:
        model = self._load_reranker()
        if not model or not candidates:
            return candidates[:top_n]
        pairs = [(query, c.chunk.raw_text) for c in candidates]
        scores = model.predict(pairs)
        order = np.argsort(-np.asarray(scores))
        return [
            RetrievedChunk(
                chunk=candidates[int(i)].chunk,
                score=float(scores[int(i)]),
                source="rerank",
                rank=r,
            )
            for r, i in enumerate(order[:top_n])
        ]

    # ---------------- 对外主入口 ----------------

    def retrieve(
        self,
        query: str,
        mode: str = "hybrid",
        top_k: int | None = None,
        top_n: int | None = None,
        doc_filter: set[str] | None = None,
    ) -> tuple[list[RetrievedChunk], dict]:
        """返回 (送进模型的 top_n 个块, 调试信息)。

        ⚠️ doc_filter 里的 doc_id 必须真实存在，否则直接报错。

        这条校验是踩坑加上的：以前传一个不存在的 doc_id，
        过滤会静默失效，函数照常返回**其它产品**的检索结果。
        用户看到"我限定了 A 产品，却返回了 B 产品的条款"，
        完全不知道是自己的 ID 写错了 —— 静默忽略参数比报错危险得多。
        """
        t0 = time.perf_counter()
        k = top_k or self.cfg.top_k
        n = top_n or self.cfg.top_n
        debug: dict = {"mode": mode, "top_k": k, "top_n": n}

        if doc_filter:
            available = {c.doc_id for c in self.store.chunks}
            unknown = sorted(doc_filter - available)
            if unknown:
                raise ValueError(
                    f"doc_id 不存在：{unknown}\n"
                    f"可用的 doc_id：{sorted(available)}\n"
                    f"（用 `python scripts/cli.py products` 可以查看全部产品）"
                )

        if mode == "vector":
            fused = self.search_vector(query, k, doc_filter=doc_filter)
        elif mode == "keyword":
            fused = self.search_keyword(query, k)
        else:
            lists = [self.search_vector(query, k, doc_filter=doc_filter)]
            if self.cfg.use_bm25:
                lists.append(self.search_keyword(query, k))
            fused = self._rrf_fuse(lists, k=self.cfg.rrf_k)

        debug["recall_count"] = len(fused)
        debug["recall_ms"] = round((time.perf_counter() - t0) * 1000, 1)

        if self.cfg.use_rerank:
            t1 = time.perf_counter()
            final = self.rerank(query, fused, n)
            debug["rerank_ms"] = round((time.perf_counter() - t1) * 1000, 1)
        else:
            final = fused[:n]

        debug["final_ids"] = [rc.chunk.chunk_id for rc in final]
        debug["final_articles"] = [
            f"{rc.chunk.product_name} {rc.chunk.article_no}".strip() for rc in final
        ]
        return final, debug
