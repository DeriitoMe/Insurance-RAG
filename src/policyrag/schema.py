"""数据结构定义：整个项目的"契约层"。

所有模块之间传递的对象都在这里定义，避免各处自己拼 dict。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, asdict
from typing import Any


# --------------------------------------------------------------------------
# 输入侧：原始文档
# --------------------------------------------------------------------------

@dataclass
class Section:
    """原始文档里的一个章节节点（可嵌套）。"""

    level: int
    title: str
    text: str = ""
    children: list["Section"] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Section":
        return cls(
            level=int(d.get("level", 1)),
            title=str(d.get("title", "")).strip(),
            text=str(d.get("text", "")).strip(),
            children=[cls.from_dict(c) for c in d.get("children", [])],
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Document:
    """一份保险条款（一个产品一个版本 = 一个 Document）。"""

    doc_id: str
    product_name: str
    company: str = ""
    version: str = ""
    doc_type: str = ""          # 百万医疗险 / 重疾险 / 意外险 ...
    effective_date: str = ""
    source_path: str = ""
    sections: list[Section] = field(default_factory=list)

    @property
    def display_name(self) -> str:
        """给人和给模型看的名字，带版本避免歧义。"""
        if self.version:
            return f"{self.product_name}（{self.version}）"
        return self.product_name

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Document":
        return cls(
            doc_id=str(d["doc_id"]).strip(),
            product_name=str(d.get("product_name", "")).strip(),
            company=str(d.get("company", "")).strip(),
            version=str(d.get("version", "")).strip(),
            doc_type=str(d.get("doc_type", "")).strip(),
            effective_date=str(d.get("effective_date", "")).strip(),
            source_path=str(d.get("source_path", "")).strip(),
            sections=[Section.from_dict(s) for s in d.get("sections", [])],
        )


# --------------------------------------------------------------------------
# 中间侧：切分后的块（整个项目的核心对象）
# --------------------------------------------------------------------------

@dataclass
class Chunk:
    """一个可检索的最小单元。

    设计要点：
    - `section_path` 保存完整层级，用于**溯源**和**注入上下文**
    - `text` 是**注入了层级前缀**的版本（喂给 embedding 和模型）
    - `raw_text` 是纯正文（用于展示原文、做引用）
    - 两者必须都保留：检索要上下文，引用要原文
    """

    chunk_id: str
    doc_id: str
    product_name: str
    doc_type: str
    section_path: list[str]
    text: str
    raw_text: str
    article_no: str = ""
    article_title: str = ""
    has_table: bool = False
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def char_len(self) -> int:
        return len(self.raw_text)

    def citation_label(self) -> str:
        """完整引用标签：产品名 + 条号 + 条标题。

        形如『安心保百万医疗险（2024版） 第三条 等待期』。

        ⚠️ 这里必须做重复检测，原因是 Section 切分时把「第X条」当成了标题的一部分，
        所以 `product_name`（来自 Document.display_name + section_path）本身
        就已经包含条号。如果无脑拼接，就会得到『... 第三条 第三条』。
        """
        label = self.product_name
        if self.article_no and self.article_no not in label:
            label = f"{label} {self.article_no}"
        if self.article_title and self.article_title not in label:
            label = f"{label} {self.article_title}"
        return label.strip()

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["char_len"] = self.char_len
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Chunk":
        known = {f for f in cls.__dataclass_fields__}          # type: ignore[attr-defined]
        payload = {k: v for k, v in d.items() if k in known}
        payload.setdefault("section_path", [])
        payload.setdefault("extra", {})
        return cls(**payload)                                  # type: ignore[arg-type]


def make_chunk_id(doc_id: str, section_path: list[str], raw_text: str, seq: int) -> str:
    """稳定 ID：同样的输入必须得到同样的 ID，否则重建索引会产生重复。

    用内容哈希而非自增序号，是为了让"重新切分后仍能对上是同一块"。
    """
    h = hashlib.sha1(f"{doc_id}|{'/'.join(section_path)}|{raw_text}".encode("utf-8"))
    return f"{doc_id}#{seq:04d}-{h.hexdigest()[:8]}"


# --------------------------------------------------------------------------
# 输出侧：检索结果与答案
# --------------------------------------------------------------------------

@dataclass
class RetrievedChunk:
    """带分数的检索结果。分数含义随检索器不同，用 `source` 区分。"""

    chunk: Chunk
    score: float
    source: str = "vector"        # vector | bm25 | hybrid | rerank
    rank: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk.chunk_id,
            "score": round(self.score, 6),
            "source": self.source,
            "rank": self.rank,
            "doc_id": self.chunk.doc_id,
            "product_name": self.chunk.product_name,
            "article_no": self.chunk.article_no,
            "section_path": self.chunk.section_path,
        }


@dataclass
class Citation:
    """结构化引用 —— 这是"可溯源"的落地形态。"""

    doc_id: str
    product_name: str
    article_no: str = ""
    article_title: str = ""
    chunk_id: str = ""
    quote: str = ""

    @classmethod
    def from_chunk(cls, c: Chunk, quote: str = "") -> "Citation":
        return cls(
            doc_id=c.doc_id,
            product_name=c.product_name,
            article_no=c.article_no,
            article_title=c.article_title,
            chunk_id=c.chunk_id,
            quote=quote or c.raw_text[:120],
        )


@dataclass
class Answer:
    """最终返回给前端的对象。"""

    question: str
    answer: str
    answerable: bool
    citations: list[Citation] = field(default_factory=list)
    used_articles: list[str] = field(default_factory=list)
    retrieved: list[RetrievedChunk] = field(default_factory=list)
    latency_ms: int = 0
    debug: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "answer": self.answer,
            "answerable": self.answerable,
            "citations": [asdict(c) for c in self.citations],
            "used_articles": self.used_articles,
            "retrieved": [r.to_dict() for r in self.retrieved],
            "latency_ms": self.latency_ms,
            "debug": self.debug,
        }
