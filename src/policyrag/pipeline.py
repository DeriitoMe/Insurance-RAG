"""编排层：把 检索 → 生成 串起来，并管理索引的加载与缓存。

所有入口（CLI / FastAPI / 评测脚本）都走这里，保证行为一致。
"""

from __future__ import annotations

import threading
from collections.abc import Iterator

from .config import Settings, get_settings
from .embedding.base import BaseEmbedder, build_embedder
from .generation.generator import (
    Generator,
    SYSTEM_PROMPT,
    build_user_prompt,
    build_llm,
    parse_answer,
)
from .index.bm25 import BM25Index
from .index.vector_store import NumpyVectorStore
from .retrieval.retriever import Retriever
from .schema import Answer, RetrievedChunk

# 简易答案缓存：相同问题直接命中（省钱 + 降延迟，面试常被问到的优化点）
_ANSWER_CACHE: dict[str, Answer] = {}
_CACHE_LOCK = threading.Lock()


class Pipeline:
    """一次装配，反复使用。FastAPI 启动时构造一个即可。"""

    def __init__(self, settings: Settings | None = None, load_index: bool = True) -> None:
        self.settings = settings or get_settings()
        self.embedder: BaseEmbedder = build_embedder(self.settings.embedding)
        self.store = NumpyVectorStore()
        self.bm25 = BM25Index()
        self.llm = build_llm(self.settings.llm)
        self.retriever = Retriever(
            store=self.store,
            embedder=self.embedder,
            bm25=self.bm25,
            cfg=self.settings.retrieval,
        )
        self.generator = Generator(self.llm)
        self._loaded = False

        if load_index:
            self.load_index()

    # ---------------- 索引 ----------------

    def load_index(self) -> None:
        self.store.load(self.settings.index_dir, expect_signature=self.embedder.signature)
        try:
            self.bm25.load(self.settings.index_dir)
        except FileNotFoundError:
            # BM25 缺失不致命，退化为纯向量检索，但必须明确告知
            print("[warn] BM25 索引缺失，退化为纯向量检索。重建：python scripts/build_index.py --rebuild")
        self._loaded = True

    @property
    def index_ready(self) -> bool:
        return self._loaded and self.store.size > 0

    @property
    def index_size(self) -> int:
        return self.store.size

    # ---------------- 问答 ----------------

    def ask(
        self,
        question: str,
        mode: str = "hybrid",
        top_k: int | None = None,
        top_n: int | None = None,
        doc_ids: list[str] | None = None,
        use_cache: bool = True,
    ) -> Answer:
        if not self.index_ready:
            raise RuntimeError("索引未就绪。先运行：python scripts/build_index.py")

        cache_key = f"{question}|{mode}|{top_k}|{top_n}|{','.join(doc_ids or [])}"
        if use_cache:
            with _CACHE_LOCK:
                if cache_key in _ANSWER_CACHE:
                    cached = _ANSWER_CACHE[cache_key]
                    cached.debug = {**cached.debug, "cache_hit": True}
                    return cached

        chunks, debug = self.retriever.retrieve(
            question,
            mode=mode,
            top_k=top_k,
            top_n=top_n,
            doc_filter=set(doc_ids) if doc_ids else None,
        )
        ans = self.generator.answer(question, chunks, debug=debug)
        ans.debug = {**ans.debug, "cache_hit": False}

        if use_cache:
            with _CACHE_LOCK:
                _ANSWER_CACHE[cache_key] = ans
        return ans

    def stream(
        self,
        question: str,
        mode: str = "hybrid",
        top_n: int | None = None,
        doc_ids: list[str] | None = None,
    ) -> Iterator[dict]:
        """流式问答。

        ⚠️ 两个工程细节（面试可以讲）：
        1. **引用和正文分开传**：引用在开始时一次性给出（用于前端立刻渲染来源），
           而不是混在 token 流里 —— 混进去前端要边收边解析 JSON，非常脆。
        2. **最后一条带完整结构化结果**：前端拿到即可覆盖渲染，避免解析半截 JSON。
        """
        if not self.index_ready:
            raise RuntimeError("索引未就绪。先运行：python scripts/build_index.py")

        chunks, debug = self.retriever.retrieve(
            question,
            mode=mode,
            top_n=top_n,
            doc_filter=set(doc_ids) if doc_ids else None,
        )
        yield {
            "type": "sources",
            "sources": [
                {
                    "label": rc.chunk.citation_label(),
                    "product_name": rc.chunk.product_name,
                    "article_no": rc.chunk.article_no,
                    "chunk_id": rc.chunk.chunk_id,
                    "preview": rc.chunk.raw_text[:80],
                }
                for rc in chunks
            ],
        }

        user = build_user_prompt(question, chunks)
        buf: list[str] = []
        try:
            for piece in self.llm.stream(SYSTEM_PROMPT, user):
                buf.append(piece)
                yield {"type": "delta", "text": piece}
        except Exception as e:                          # noqa: BLE001
            yield {"type": "error", "message": f"{type(e).__name__}: {e}"}
            return

        raw = "".join(buf)
        answer, answerable, cites, used = parse_answer(raw, chunks)
        yield {
            "type": "final",
            "answer": answer,
            "answerable": answerable,
            "citations": [
                {
                    "label": f"{c.product_name} {c.article_no}".strip(),
                    "product_name": c.product_name,
                    "article_no": c.article_no,
                    "quote": c.quote,
                }
                for c in cites
            ],
            "used_articles": used,
            "debug": debug,
        }

    # ---------------- 辅助 ----------------

    def list_products(self) -> list[dict]:
        seen: dict[str, dict] = {}
        for c in self.store.chunks:
            if c.doc_id not in seen:
                seen[c.doc_id] = {
                    "doc_id": c.doc_id,
                    "product_name": c.product_name,
                    "doc_type": c.doc_type,
                    "chunks": 0,
                }
            seen[c.doc_id]["chunks"] += 1
        return list(seen.values())
