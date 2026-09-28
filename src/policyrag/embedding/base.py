"""向量化层：可插拔设计。

为什么做成可插拔（真实原因，面试可以直说）：
1. **开发机装不了大模型**（Python 3.14 没有 torch 轮子）→ 需要零依赖兜底
2. **企业场景数据不能出内网** → 必须支持本地模型
3. **换模型必须重建索引** → 所以索引文件里必须记下用的是哪个模型

provider 三选一：
  hash  : 字符 n-gram 哈希。零依赖，**效果差，只为跑通链路**，不可用于评测结论
  api   : OpenAI 兼容接口（DeepSeek / 智谱 / 通义 / 硅基流动 / 本地 vLLM）
  local : sentence-transformers（需 torch），推荐 BAAI/bge-large-zh-v1.5
"""

from __future__ import annotations

import hashlib
import math
from abc import ABC, abstractmethod

import numpy as np

from ..config import EmbeddingConfig


class EmbeddingError(RuntimeError):
    pass


class BaseEmbedder(ABC):
    """所有 embedder 的统一接口。"""

    #: 写进索引文件的标识，用于校验"索引是用哪个模型建的"
    signature: str = ""

    @abstractmethod
    def embed_documents(self, texts: list[str]) -> np.ndarray:
        """返回 shape=(n, dim) 的归一化向量矩阵。"""

    @abstractmethod
    def embed_query(self, text: str) -> np.ndarray:
        """返回 shape=(dim,) 的归一化向量。"""

    @property
    @abstractmethod
    def dim(self) -> int:
        ...

    @staticmethod
    def _normalize(mat: np.ndarray) -> np.ndarray:
        """L2 归一化 → 之后内积等价于余弦相似度，省一次除法。"""
        norms = np.linalg.norm(mat, axis=-1, keepdims=True)
        norms[norms == 0] = 1.0
        return mat / norms


# --------------------------------------------------------------------------
# Provider 1: hash —— 零依赖兜底
# --------------------------------------------------------------------------

class HashEmbedder(BaseEmbedder):
    """字符 n-gram 哈希向量。

    ⚠️ 诚实说明：这**不是语义向量**，本质上只是"字形重叠度"。
    它能区分"等待期"和"保险责任"（因为字不同），
    但**无法识别"理赔要多久"和"赔付时效"是同义**——那正是向量检索的价值所在。
    所以：它只用于在没有任何依赖/密钥时跑通全链路，**产出的评测数字没有意义**。
    """

    def __init__(self, dim: int = 512, ngrams: tuple[int, ...] = (1, 2, 3)) -> None:
        self._dim = dim
        self._ngrams = ngrams

    @property
    def dim(self) -> int:
        return self._dim

    @property
    def signature(self) -> str:
        return f"hash-v1-dim{self._dim}"

    def _one(self, text: str) -> np.ndarray:
        vec = np.zeros(self._dim, dtype=np.float32)
        s = "".join(text.split()).lower()
        for n in self._ngrams:
            for i in range(max(0, len(s) - n + 1)):
                gram = s[i:i + n]
                h = hashlib.md5(gram.encode("utf-8")).digest()
                idx = int.from_bytes(h[:4], "little") % self._dim
                sign = 1.0 if h[4] % 2 == 0 else -1.0
                # 长 n-gram 权重更高：更具体
                vec[idx] += sign * (1.0 + 0.5 * (n - 1))
        return vec

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self._dim), dtype=np.float32)
        return self._normalize(np.vstack([self._one(t) for t in texts]))

    def embed_query(self, text: str) -> np.ndarray:
        return self._normalize(self._one(text).reshape(1, -1))[0]


# --------------------------------------------------------------------------
# Provider 2: api —— OpenAI 兼容接口
# --------------------------------------------------------------------------

class ApiEmbedder(BaseEmbedder):
    """走 OpenAI 兼容的 /embeddings 接口。

    换成任何兼容服务只需改 PR_EMB_API_BASE / PR_EMB_MODEL / PR_EMB_API_KEY，
    不用改代码 —— 这就是"可插拔"的实际收益。
    """

    def __init__(self, cfg: EmbeddingConfig) -> None:
        if not cfg.api_key:
            raise EmbeddingError(
                "PR_EMB_PROVIDER=api 但没有设置 PR_EMB_API_KEY。"
                "另一种选择：用本地模型 PR_EMB_PROVIDER=local"
            )
        try:
            import requests  # noqa: F401
        except ImportError as e:
            raise EmbeddingError("需要 requests：pip install requests") from e

        self.cfg = cfg
        self._dim = cfg.dim
        self._dim_probed = False

    @property
    def dim(self) -> int:
        return self._dim

    @property
    def signature(self) -> str:
        return f"api:{self.cfg.model_name}"

    def _post(self, texts: list[str]) -> list[list[float]]:
        import requests

        url = self.cfg.api_base.rstrip("/") + "/embeddings"
        resp = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {self.cfg.api_key}",
                "Content-Type": "application/json",
            },
            json={"model": self.cfg.model_name, "input": texts},
            timeout=60,
        )
        if resp.status_code != 200:
            raise EmbeddingError(
                f"embedding 接口返回 {resp.status_code}: {resp.text[:300]}"
            )
        data = resp.json()
        rows = sorted(data["data"], key=lambda r: r.get("index", 0))
        return [r["embedding"] for r in rows]

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self._dim), dtype=np.float32)
        out: list[list[float]] = []
        bs = max(1, self.cfg.batch_size)
        for i in range(0, len(texts), bs):
            out.extend(self._post(texts[i:i + bs]))
        mat = np.asarray(out, dtype=np.float32)
        if not self._dim_probed:
            self._dim = int(mat.shape[1])
            self._dim_probed = True
        return self._normalize(mat)

    def embed_query(self, text: str) -> np.ndarray:
        return self.embed_documents([text])[0]


# --------------------------------------------------------------------------
# Provider 3: local —— sentence-transformers
# --------------------------------------------------------------------------

class LocalEmbedder(BaseEmbedder):
    """本地中文向量模型。生产/内网场景用这个。

    为什么推荐 BGE 中文系列：中文保险条款里的专业表述（既往症、免赔额、
    等待期）在英文模型上表现明显更差。
    """

    def __init__(self, cfg: EmbeddingConfig) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as e:
            raise EmbeddingError(
                "本地模型需要 sentence-transformers（会连带安装 torch，约 2GB）：\n"
                "  pip install sentence-transformers\n"
                "如果装不上，改用 api provider。"
            ) from e

        self.cfg = cfg
        self.model = SentenceTransformer(cfg.model_name, device=cfg.device)
        self._dim = int(self.model.get_sentence_embedding_dimension())

    @property
    def dim(self) -> int:
        return self._dim

    @property
    def signature(self) -> str:
        return f"local:{self.cfg.model_name}"

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self._dim), dtype=np.float32)
        vecs = self.model.encode(
            texts,
            batch_size=self.cfg.batch_size,
            normalize_embeddings=True,
            show_progress_bar=len(texts) > 64,
        )
        return np.asarray(vecs, dtype=np.float32)

    def embed_query(self, text: str) -> np.ndarray:
        # BGE 系列检索任务建议加这个前缀，能明显提升召回
        q = f"为这个句子生成表示以用于检索相关文章：{text}"
        return self.embed_documents([q])[0]


# --------------------------------------------------------------------------
# 工厂
# --------------------------------------------------------------------------

def build_embedder(cfg: EmbeddingConfig | None = None) -> BaseEmbedder:
    cfg = cfg or EmbeddingConfig()
    provider = cfg.provider.lower()
    if provider == "hash":
        return HashEmbedder(dim=512)
    if provider == "api":
        return ApiEmbedder(cfg)
    if provider == "local":
        return LocalEmbedder(cfg)
    raise EmbeddingError(f"未知的 PR_EMB_PROVIDER={cfg.provider!r}，可选：hash / api / local")


def cosine_topk(query_vec: np.ndarray, mat: np.ndarray, k: int) -> list[tuple[int, float]]:
    """向量已归一化 → 内积即余弦相似度。返回 [(下标, 分数)] 降序。"""
    if mat.size == 0:
        return []
    scores = mat @ query_vec
    k = min(k, scores.shape[0])
    idx = np.argpartition(-scores, k - 1)[:k]
    idx = idx[np.argsort(-scores[idx])]
    return [(int(i), float(scores[i])) for i in idx]
