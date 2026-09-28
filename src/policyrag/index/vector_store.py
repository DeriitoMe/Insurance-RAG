"""向量索引：默认 numpy 实现（零依赖、可持久化、数据量小场景够用）。

为什么不直接用 Chroma / Milvus：
1. 开发机 Python 3.14 装不上 chromadb（没有轮子）
2. **几万条以内的语料，numpy 暴力检索 < 10ms**，引入向量库纯属增加部署复杂度
3. 面试时能讲清"什么规模该上专业向量库"比"我会用 Chroma"更有价值

什么时候必须换专业向量库：
- chunk 数超过 ~10 万（暴力检索开始变慢）
- 需要增量更新、多租户隔离、持久化事务
- 需要 HNSW/IVF 索引（用精度换速度）

索引文件里记录 embedding signature —— 换模型后加载会直接报错，
而不是静默返回垃圾结果（这是很容易踩的坑）。
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from ..schema import Chunk


class IndexError_(RuntimeError):
    pass


class NumpyVectorStore:
    """暴力检索向量库。"""

    FILENAME = "vectors.npz"
    META_FILENAME = "meta.json"

    def __init__(self) -> None:
        self.chunks: list[Chunk] = []
        self.matrix: np.ndarray | None = None      # (n, dim) float32，已归一化
        self.signature: str = ""

    # ---------------- 构建 ----------------

    def build(self, chunks: list[Chunk], embeddings: np.ndarray, signature: str) -> None:
        if len(chunks) != embeddings.shape[0]:
            raise IndexError_(
                f"chunk 数({len(chunks)}) 与向量数({embeddings.shape[0]}) 不一致"
            )
        self.chunks = chunks
        self.matrix = embeddings.astype(np.float32)
        self.signature = signature

    # ---------------- 持久化 ----------------

    def save(self, index_dir: Path) -> None:
        if self.matrix is None:
            raise IndexError_("索引为空，无法保存")
        index_dir.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(index_dir / self.FILENAME, matrix=self.matrix)
        meta = {
            "signature": self.signature,
            "dim": int(self.matrix.shape[1]),
            "count": len(self.chunks),
            "chunks": [c.to_dict() for c in self.chunks],
        }
        (index_dir / self.META_FILENAME).write_text(
            json.dumps(meta, ensure_ascii=False), encoding="utf-8"
        )

    def load(self, index_dir: Path, expect_signature: str | None = None) -> None:
        meta_path = index_dir / self.META_FILENAME
        vec_path = index_dir / self.FILENAME
        if not meta_path.exists() or not vec_path.exists():
            raise IndexError_(
                f"索引不存在于 {index_dir}。先运行：python scripts/build_index.py"
            )

        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        self.signature = meta.get("signature", "")
        self.chunks = [Chunk.from_dict(c) for c in meta["chunks"]]
        self.matrix = np.load(vec_path)["matrix"].astype(np.float32)

        if expect_signature and self.signature != expect_signature:
            raise IndexError_(
                "向量模型与索引不匹配，必须重建索引：\n"
                f"  索引是用 {self.signature!r} 建的\n"
                f"  当前配置是 {expect_signature!r}\n"
                "原因：不同模型产出的向量不在同一空间，混用会得到无意义的结果。\n"
                "重建：python scripts/build_index.py --rebuild"
            )
        if len(self.chunks) != self.matrix.shape[0]:
            raise IndexError_("索引文件损坏：chunk 数与向量数不一致，请重建")

    # ---------------- 检索 ----------------

    def search(
        self,
        query_vec: np.ndarray,
        top_k: int = 20,
        doc_filter: set[str] | None = None,
    ) -> list[tuple[int, float]]:
        """返回 [(chunk 下标, 余弦相似度)]，降序。

        doc_filter：按产品过滤 —— 这是"结构化约束 + 语义检索"的组合，
        做多产品对比时必需。
        """
        if self.matrix is None or not self.chunks:
            return []
        if doc_filter:
            allowed = [i for i, c in enumerate(self.chunks) if c.doc_id in doc_filter]
            if not allowed:
                return []
            sub = self.matrix[allowed]
            scores = sub @ query_vec
            k = min(top_k, len(allowed))
            order = np.argsort(-scores)[:k]
            return [(allowed[int(i)], float(scores[int(i)])) for i in order]

        scores = self.matrix @ query_vec
        k = min(top_k, scores.shape[0])
        idx = np.argpartition(-scores, k - 1)[:k]
        idx = idx[np.argsort(-scores[idx])]
        return [(int(i), float(scores[i])) for i in idx]

    @property
    def size(self) -> int:
        return len(self.chunks)
