"""层次感知切分器 —— 本项目的技术核心。

设计原则（面试可以直接讲）：

1. **以"条"为最小完整单元**：保险条款的编号结构本身就是法律意义上的语义边界，
   按固定字数切会把"等待期"和"保险责任"切进不同块，检索出来就是半句话。

2. **上下文注入**：每个 chunk 的 text 头部拼上父级路径。
   向量检索丢失了文档结构，我们用工程手段把它补回来。

3. **超长二次切分，超短向上合并**：
   800 字以上按列表项切；60 字以下和同级相邻条款合并（否则会出现
   "第X条 定义" 这种什么都检索不到的碎片块）。

4. **列表项不是边界**：`（一）（二）` 是条款内部结构，单独切开会丢主语。
"""

from __future__ import annotations

import re
from typing import Iterable

from ..config import ChunkConfig
from ..schema import Chunk, Document, Section, make_chunk_id


# --------------------------------------------------------------------------
# 标题识别
# --------------------------------------------------------------------------

# 顺序即优先级：越靠前越"像"标题
_ARTICLE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^第[一二三四五六七八九十百零〇\d]+条"),          # 第一条 / 第 12 条
    re.compile(r"^第[一二三四五六七八九十百零〇\d]+章"),          # 第一章
    re.compile(r"^第[一二三四五六七八九十百零〇\d]+部分"),        # 第一部分
    re.compile(r"^第[一二三四五六七八九十百零〇\d]+节"),
]

# 数字编号标题：1.1 / 3.2.1
_NUMBERED_RE = re.compile(r"^(\d+(?:\.\d+){1,3})\s*(\S.{0,79})$")
_APPENDIX_RE = re.compile(r"^附表\s*[0-9一二三四五六七八九十百零〇]+")

# 列表项：不作为标题/边界
_LIST_ITEM_RE = re.compile(r"^[（(]?[一二三四五六七八九十\d]{1,3}[）)、.．]\s*")

_TABLE_HINT_RE = re.compile(r"(\|.*\||表\s*\d|如下表|下表|单位：|金额单位)")

# 一段文字超过这个长度，基本不可能是标题
_MAX_TITLE_LEN = 40


def detect_heading(line: str) -> tuple[str, str] | None:
    """判断一行是不是标题。

    返回 (kind, title)，kind ∈ {article, chapter, part, section, numbered}。
    不是标题返回 None。
    """
    s = line.strip()
    if not s:
        return None
    # 句末标点 → 是正文
    if s.endswith(("。", "；", "，", "！", "？", "：", "”")):
        return None

    if _APPENDIX_RE.match(s) and len(s) <= _MAX_TITLE_LEN:
        return "part", re.sub(r"\s+", "", s).rstrip("：:")

    # 数字编号标题必须先判：像 "1.1 保险责任" 会被列表项规则误伤
    # （列表项规则匹配的是 "1. " 这种，但 "1.1" 也长得像，所以顺序不能反）
    if _NUMBERED_RE.match(s) and len(s) <= 100:
        return "numbered", s

    if len(s) > _MAX_TITLE_LEN:
        return None

    # 列表项排除：它们不是标题，也不是切分边界
    if _LIST_ITEM_RE.match(s) and not s.startswith("第"):
        return None

    for pat in _ARTICLE_PATTERNS:
        if pat.match(s):
            if s.startswith("第") and "章" in s[:6]:
                return "chapter", s
            if s.startswith("第") and "部分" in s[:8]:
                return "part", s
            if s.startswith("第") and "节" in s[:6]:
                return "section", s
            return "article", s

    return None


def _split_article_no(title: str) -> tuple[str, str]:
    """从 '第六条 保险责任' 拆出 ('第六条', '保险责任')。"""
    m = re.match(r"^(第[一二三四五六七八九十百零〇\d]+条)[\s、.．:：]*(.*)$", title.strip())
    if m:
        return m.group(1), m.group(2).strip()
    m = re.match(r"^(\d+(?:\.\d+){1,3})\s*[、.．:：]?\s*(.*)$", title.strip())
    if m:
        return m.group(1), m.group(2).strip()
    m = re.match(r"^(附表\s*[0-9一二三四五六七八九十百零〇]+)\s*[：:]?\s*(.*)$", title.strip())
    if m:
        return re.sub(r"\s+", "", m.group(1)), m.group(2).strip()
    return "", title.strip()


# --------------------------------------------------------------------------
# JSON 结构化文档 → chunk
# --------------------------------------------------------------------------

def _walk_sections(
    sections: Iterable[Section],
    parent_path: list[str],
) -> Iterable[tuple[list[str], Section]]:
    """深度优先展开，产出 (section_path, section)。"""
    for sec in sections:
        path = parent_path + ([sec.title] if sec.title else [])
        if sec.children:
            yield from _walk_sections(sec.children, path)
            # 父节点自身也可能有正文（如"第二部分 保险责任"下面的一段总述）
            if sec.text.strip():
                yield path, sec
        else:
            yield path, sec


def _split_long_text(text: str, max_chars: int) -> list[str]:
    """超长文本二次切分：优先在列表项/段落边界切，其次在句号切。"""
    text = text.strip()
    if len(text) <= max_chars:
        return [text] if text else []

    # 找所有可能的切点：列表项开头、空行后
    candidates: list[int] = []
    for m in re.finditer(r"(?m)^[（(]?[一二三四五六七八九十\d]{1,3}[）)、.．]", text):
        candidates.append(m.start())
    for m in re.finditer(r"\n\s*\n", text):
        candidates.append(m.end())
    if not candidates:
        for m in re.finditer(r"[。；]", text):
            candidates.append(m.end())

    if not candidates:
        # 实在没有边界，硬切
        return [text[i:i + max_chars] for i in range(0, len(text), max_chars)]

    pieces: list[str] = []
    start = 0
    for pos in candidates:
        if pos - start >= max_chars:
            piece = text[start:pos].strip()
            if piece:
                pieces.append(piece)
            start = pos
    tail = text[start:].strip()
    if tail:
        pieces.append(tail)

    # 仍有个别超长的，硬切兜底
    out: list[str] = []
    for p in pieces:
        if len(p) <= max_chars * 1.5:
            out.append(p)
        else:
            out.extend(p[i:i + max_chars] for i in range(0, len(p), max_chars))
    return out


def _merge_short(chunks: list[Chunk], min_chars: int) -> list[Chunk]:
    """把过短的块合并进前一块（同文档、同章节路径前缀）。

    为什么需要：像『第X条 定义』这种块单独存在时，既不携带信息，
    又会在 top_k 里挤掉真正有用的内容。
    """
    if not chunks:
        return []
    out: list[Chunk] = []
    for c in chunks:
        if (
            out
            and c.char_len < min_chars
            and out[-1].doc_id == c.doc_id
            and out[-1].char_len + c.char_len <= 2000
        ):
            prev = out[-1]
            prev.raw_text = f"{prev.raw_text}\n{c.raw_text}".strip()
            prev.text = f"{prev.text}\n{c.raw_text}".strip()
            if c.article_no and c.article_no not in prev.extra.get("merged_articles", []):
                prev.extra.setdefault("merged_articles", []).append(c.article_no)
            continue
        out.append(c)
    return out


def chunk_document(doc: Document, cfg: ChunkConfig) -> list[Chunk]:
    """把一个 Document 切成 Chunk 列表。"""
    raw_chunks: list[Chunk] = []
    seq = 0

    for path, sec in _walk_sections(doc.sections, []):
        body = sec.text.strip()
        if not body:
            continue

        article_no, article_title = _split_article_no(sec.title)
        has_table = bool(_TABLE_HINT_RE.search(body))

        for piece in _split_long_text(body, cfg.max_chars):
            seq += 1
            if cfg.inject_section_path:
                prefix = " > ".join([doc.display_name] + path)
                text = f"【{prefix}】\n{piece}"
            else:
                text = piece

            raw_chunks.append(
                Chunk(
                    chunk_id=make_chunk_id(doc.doc_id, path, piece, seq),
                    doc_id=doc.doc_id,
                    product_name=doc.display_name,
                    doc_type=doc.doc_type,
                    section_path=path,
                    text=text,
                    raw_text=piece,
                    article_no=article_no,
                    article_title=article_title,
                    has_table=has_table,
                )
            )

    return _merge_short(raw_chunks, cfg.min_chars)


# --------------------------------------------------------------------------
# 纯文本（PDF / txt / md）→ 顺序列表（不嵌套）
# --------------------------------------------------------------------------

def sections_from_plain_text(text: str) -> list[Section]:
    """把无结构的纯文本按标题行切成扁平的 Section 列表。

    PDF 抽出来的就是这个形态：只剩顺序，没有嵌套。
    我们用标题识别 + 层级栈把它重新组织成树。
    """
    lines = [ln.rstrip() for ln in text.splitlines()]
    root: list[Section] = []
    stack: list[Section] = []          # 层级栈，index = level - 1

    for line in lines:
        heading = detect_heading(line)
        if heading is None:
            if stack:
                target = stack[-1]
            else:
                if not root or root[-1].title:
                    root.append(Section(level=1, title="", text=""))
                target = root[-1]
            target.text = (target.text + "\n" + line).strip()
            continue

        kind, title = heading
        level = {"part": 1, "chapter": 2, "section": 3, "article": 3, "numbered": 4}[kind]

        node = Section(level=level, title=title, text="")
        # 弹出所有 >= level 的节点
        while stack and stack[-1].level >= level:
            stack.pop()
        if stack:
            stack[-1].children.append(node)
        else:
            root.append(node)
        stack.append(node)

    # 去掉纯空壳
    def _prune(secs: list[Section]) -> list[Section]:
        out = []
        for s in secs:
            s.children = _prune(s.children)
            if s.title or s.text.strip() or s.children:
                out.append(s)
        return out

    return _prune(root)
