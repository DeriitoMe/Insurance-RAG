"""BM25 关键词索引 —— 混合检索的另一半。

为什么必须有它（面试必答）：

| 查询 | 纯向量的问题 | BM25 怎么救 |
|---|---|---|
| "第六条怎么写的" | 向量不擅长精确编号匹配 | 关键词直接命中"第六条" |
| "免赔额是一万吗" | 数字匹配弱 | 精准匹配"一万"/"10000" |
| "甲状腺结节能赔吗" | 条款用的是"既往症""特定疾病"，字面无重叠 | 这一问**靠向量** |

→ 所以两个都用，用 RRF 融合。**任何单一路径都会在这三类问题里输掉一类。**

实现说明：手写 BM25 而不是调 rank_bm25，理由有两个 ——
① 少一个依赖，② 中文必须自己接分词器（jieba），用现成库反而要绕过它的英文分词。
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path

from ..schema import Chunk

# 中文标点和空白都当分隔符
_SPLIT_RE = re.compile(r"[\s\u3000,，。；;：:、！!？?（）()\[\]【】《》\"'“”‘’—\-/\\|]+")
_STOPWORDS = {
    "的", "了", "和", "与", "或", "在", "是", "有", "为", "对", "及", "本",
    "该", "按", "由", "并", "等", "之", "其", "此", "上", "下", "中",
}


class Tokenizer:
    """中文分词器。jieba 不存在时退化为字符 bigram（保证可跑）。"""

    def __init__(self) -> None:
        self._jieba = None
        try:
            import jieba
            jieba.setLogLevel(60)          # 关掉 "Building prefix dict" 噪音
            self._jieba = jieba
        except ImportError:
            pass

    def cut(self, text: str) -> list[str]:
        text = text.strip().lower()
        if not text:
            return []
        if self._jieba is not None:
            tokens = [t for t in self._jieba.lcut_for_search(text) if t.strip()]
        else:
            # 退化方案：字符 bigram + 单字
            compact = _SPLIT_RE.sub("", text)
            tokens = list(compact) + [compact[i:i + 2] for i in range(len(compact) - 1)]
        tokens = [t for t in tokens if t not in _STOPWORDS and len(t) >= 1]
        return tokens or _SPLIT_RE.split(text)


class BM25Index:
    """标准 BM25（Okapi）。

    score(q, d) = Σ_t IDF(t) * (f(t,d) * (k1+1)) / (f(t,d) + k1 * (1 - b + b * |d|/avgdl))
    IDF(t) = ln(1 + (N - df(t) + 0.5) / (df(t) + 0.5))
    """

    FILENAME = "bm25.json"

    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        self.tokenizer = Tokenizer()
        self.chunk_ids: list[str] = []
        self.doc_len: list[int] = []
        self.avgdl: float = 0.0
        self.postings: dict[str, list[tuple[int, int]]] = {}   # term -> [(doc_idx, tf)]
        self.df: dict[str, int] = {}
        self._warmup()

    def _warmup(self) -> None:
        """预热分词器。

        jieba 首次调用要加载词典，实测会让第一次检索多花 ~400ms。
        预热一次，避免这个延迟落在用户的第一次提问上。
        """
        try:
            self.tokenizer.cut("预热")
        except Exception:                                   # noqa: BLE001
            pass

    def build(self, chunks: list[Chunk]) -> None:
        self.chunk_ids = [c.chunk_id for c in chunks]
        self.postings = {}
        self.df = {}
        self.doc_len = []

        for i, c in enumerate(chunks):
            tokens = self.tokenizer.cut(c.text)
            self.doc_len.append(len(tokens))
            for term, tf in Counter(tokens).items():
                self.postings.setdefault(term, []).append((i, tf))
                self.df[term] = self.df.get(term, 0) + 1

        n = len(chunks)
        self.avgdl = (sum(self.doc_len) / n) if n else 0.0

    def _idf(self, term: str) -> float:
        n = len(self.chunk_ids)
        df = self.df.get(term, 0)
        # 用 1+ 的形式保证 IDF 非负（否则高频词会得到负分，排序会反）
        return math.log(1.0 + (n - df + 0.5) / (df + 0.5))

    def search(self, query: str, top_k: int = 20) -> list[tuple[int, float]]:
        if not self.chunk_ids:
            return []
        tokens = self.tokenizer.cut(query)
        if not tokens:
            return []

        scores: dict[int, float] = {}
        for term in set(tokens):
            posting = self.postings.get(term)
            if not posting:
                continue
            idf = self._idf(term)
            for doc_idx, tf in posting:
                dl = self.doc_len[doc_idx] or 1
                denom = tf + self.k1 * (1 - self.b + self.b * dl / (self.avgdl or 1.0))
                scores[doc_idx] = scores.get(doc_idx, 0.0) + idf * (tf * (self.k1 + 1)) / denom

        ranked = sorted(scores.items(), key=lambda kv: -kv[1])[:top_k]
        return ranked

    # ---------------- 持久化 ----------------

    def save(self, index_dir: Path) -> None:
        index_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "k1": self.k1,
            "b": self.b,
            "chunk_ids": self.chunk_ids,
            "doc_len": self.doc_len,
            "avgdl": self.avgdl,
            "df": self.df,
            # JSON 的 key 必须是字符串，但 postings 的 key 本身就是 str，直接用
            "postings": {k: v for k, v in self.postings.items()},
        }
        (index_dir / self.FILENAME).write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8"
        )

    def load(self, index_dir: Path) -> None:
        path = index_dir / self.FILENAME
        if not path.exists():
            raise FileNotFoundError(
                f"BM25 索引不存在：{path}。先运行：python scripts/build_index.py"
            )
        d = json.loads(path.read_text(encoding="utf-8"))
        self.k1 = d["k1"]
        self.b = d["b"]
        self.chunk_ids = d["chunk_ids"]
        self.doc_len = d["doc_len"]
        self.avgdl = d["avgdl"]
        self.df = d["df"]
        self.postings = {k: [tuple(x) for x in v] for k, v in d["postings"].items()}

    @property
    def size(self) -> int:
        return len(self.chunk_ids)
