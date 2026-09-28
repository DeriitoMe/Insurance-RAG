"""单元测试：切分器是最该测的地方，因为它是整个项目的技术核心。

运行：
    python -m pytest tests -q
或无 pytest 时：
    python tests/test_chunker.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from policyrag.config import ChunkConfig
from policyrag.ingest.chunker import (
    chunk_document,
    detect_heading,
    sections_from_plain_text,
    _split_article_no,
    _split_long_text,
    _merge_short,
)
from policyrag.schema import Chunk, Document


# --------------------------------------------------------------------------
# 标题识别
# --------------------------------------------------------------------------

def test_detect_article_heading():
    assert detect_heading("第一条 保险合同的构成")[0] == "article"
    assert detect_heading("第六条")[0] == "article"
    assert detect_heading("第十二条 既往症")[0] == "article"


def test_detect_chapter_and_part():
    assert detect_heading("第一章 总则")[0] == "chapter"
    assert detect_heading("第一部分 总则")[0] == "part"


def test_detect_numbered_heading():
    assert detect_heading("1.1 保险责任")[0] == "numbered"
    assert detect_heading("3.2.1 等待期")[0] == "numbered"


def test_reject_body_text():
    # 正文行（有句末标点）不能识别为标题
    assert detect_heading("保险期间为一年。") is None
    assert detect_heading("这一行是普通正文内容，不应该被识别成标题") is None
    # 列表项不是标题
    assert detect_heading("（一）投保人故意造成被保险人伤害；") is None
    assert detect_heading("1. 第一项内容") is None
    # 超长行不是标题
    assert detect_heading("第" + "很" * 60 + "条") is None


def test_split_article_no():
    assert _split_article_no("第六条 保险责任") == ("第六条", "保险责任")
    assert _split_article_no("第六条") == ("第六条", "")
    assert _split_article_no("1.1 等待期") == ("1.1", "等待期")


# --------------------------------------------------------------------------
# 长文切分
# --------------------------------------------------------------------------

def test_split_long_text_under_limit():
    t = "这是一段短文本。"
    assert _split_long_text(t, 100) == [t]


def test_split_long_text_over_limit():
    t = "（一）第一项内容。" * 20
    parts = _split_long_text(t, 60)
    assert len(parts) > 1
    # 每一块都不应该远超上限
    assert all(len(p) <= 60 * 1.5 for p in parts)
    # 内容不能丢
    assert sum(len(p) for p in parts) >= len(t) - 10


def test_split_long_text_hard_fallback():
    # 没有任何边界的长文本必须能硬切，不能死循环
    t = "啊" * 500
    parts = _split_long_text(t, 100)
    assert len(parts) >= 5


# --------------------------------------------------------------------------
# 短块合并
# --------------------------------------------------------------------------

def _mk(cid: str, text: str) -> Chunk:
    return Chunk(
        chunk_id=cid, doc_id="d1", product_name="测试产品", doc_type="医疗险",
        section_path=["第一章"], text=text, raw_text=text, article_no=cid,
    )


def test_merge_short_merges_into_previous():
    chunks = [_mk("a", "正常长度的内容" * 10), _mk("b", "太短")]
    merged = _merge_short(chunks, min_chars=60)
    assert len(merged) == 1
    assert "太短" in merged[0].raw_text


def test_merge_short_keeps_long_enough():
    chunks = [_mk("a", "正常内容" * 30), _mk("b", "也够长" * 30)]
    merged = _merge_short(chunks, min_chars=60)
    assert len(merged) == 2


def test_merge_short_does_not_cross_documents():
    a = _mk("a", "内容" * 30)
    b = _mk("b", "短")
    b.doc_id = "d2"
    merged = _merge_short([a, b], min_chars=60)
    assert len(merged) == 2


# --------------------------------------------------------------------------
# 文档级切分：项目最关键的一组断言
# --------------------------------------------------------------------------

def _sample_doc() -> Document:
    return Document.from_dict({
        "doc_id": "t1",
        "product_name": "测试医疗险",
        "version": "2024版",
        "doc_type": "百万医疗险",
        "sections": [
            {"level": 1, "title": "第一部分 总则", "text": "", "children": [
                {"level": 2, "title": "第一条 保险合同的构成",
                 "text": "本保险合同由保险单、保险条款、投保单共同构成，"
                         "以及与本合同有关的其他投保文件、合法有效的声明、批注、批单。"},
                {"level": 2, "title": "第二条 等待期",
                 "text": "自本合同生效之日起90日为等待期。被保险人在等待期内因疾病发生"
                         "住院治疗的，本公司不承担给付保险金的责任。"},
            ]},
        ],
    })


def test_chunk_document_injects_section_path():
    doc = _sample_doc()
    chunks = chunk_document(doc, ChunkConfig(min_chars=10))
    assert len(chunks) == 2
    c = chunks[1]
    # 上下文注入：text 里必须带层级路径，否则孤立片段没有上下文
    assert "测试医疗险（2024版）" in c.text
    assert "第一部分 总则" in c.text
    assert "第二条 等待期" in c.text
    # raw_text 必须是纯正文（用于展示和引用）
    assert "【" not in c.raw_text
    assert c.raw_text.startswith("自本合同生效之日起90日")


def test_chunk_document_metadata():
    chunks = chunk_document(_sample_doc(), ChunkConfig(min_chars=10))
    c = chunks[1]
    assert c.doc_id == "t1"
    assert c.article_no == "第二条"
    assert c.article_title == "等待期"
    assert c.section_path == ["第一部分 总则", "第二条 等待期"]
    assert c.product_name == "测试医疗险（2024版）"
    # 注意：这个 fixture 的 product_name 只有产品名（没有条号），
    # 所以 citation_label 会补上条号和条标题。
    assert c.citation_label() == "测试医疗险（2024版） 第二条 等待期"


def test_citation_label_does_not_duplicate_article_no():
    """回归测试：条款层级切分时「第X条」进入了 product_name，
    所以 citation_label 必须做重复检测，否则会出现『第三条 第三条』。

    这是真实踩过的 bug：CLI 里打印出「... 第三条 第三条」。
    """
    c = Chunk(
        chunk_id="x", doc_id="d", product_name="安心保百万医疗险（2024版） 第三条",
        doc_type="百万医疗险", section_path=["第一部分 总则", "第三条 等待期"],
        text="", raw_text="自本合同生效之日起90日为等待期。",
        article_no="第三条", article_title="等待期",
    )
    label = c.citation_label()
    assert label.count("第三条") == 1, f"条号重复了：{label!r}"
    assert label == "安心保百万医疗险（2024版） 第三条 等待期"


def test_chunk_ids_are_stable():
    """同样的输入必须得到同样的 ID，否则重建索引会重复。"""
    a = chunk_document(_sample_doc(), ChunkConfig(min_chars=10))
    b = chunk_document(_sample_doc(), ChunkConfig(min_chars=10))
    assert [c.chunk_id for c in a] == [c.chunk_id for c in b]


def test_chunk_document_respects_max_chars():
    long_text = "（一）内容项目。" * 200
    doc = Document.from_dict({
        "doc_id": "t2", "product_name": "长条款测试",
        "sections": [{"level": 1, "title": "第一条 责任免除", "text": long_text}],
    })
    chunks = chunk_document(doc, ChunkConfig(max_chars=200, min_chars=10))
    assert len(chunks) > 5
    # 除了极少数硬切情况，单块不应超过上限太多
    assert max(c.char_len for c in chunks) <= 400


# --------------------------------------------------------------------------
# 纯文本重建层级（PDF 路径）
# --------------------------------------------------------------------------

def test_sections_from_plain_text_builds_hierarchy():
    text = """第一部分 总则
第一条 保险合同的构成
本保险合同由保险单、保险条款、投保单共同构成。
第二条 等待期
自本合同生效之日起90日为等待期。
"""
    secs = sections_from_plain_text(text)
    assert len(secs) == 1
    part = secs[0]
    assert part.title == "第一部分 总则"
    assert len(part.children) == 2
    assert part.children[0].title == "第一条 保险合同的构成"
    assert "保险单" in part.children[0].text
    assert part.children[1].title == "第二条 等待期"
    assert "90日" in part.children[1].text


def test_plain_text_chunking_end_to_end():
    text = """第一条 保险责任
在本合同保险期间内，被保险人因意外伤害或等待期后因疾病，在本公司认可的医院
接受治疗的，本公司按下列约定承担保险责任。
第二条 责任免除
因下列情形之一导致被保险人发生医疗费用的，本公司不承担给付保险金的责任。
"""
    doc = Document(
        doc_id="p1", product_name="PDF测试产品",
        sections=sections_from_plain_text(text),
    )
    chunks = chunk_document(doc, ChunkConfig(min_chars=10))
    assert len(chunks) == 2
    assert chunks[0].article_no == "第一条"
    assert chunks[1].article_no == "第二条"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"[ok]   {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"[FAIL] {fn.__name__}: {e}")
        except Exception as e:                              # noqa: BLE001
            failed += 1
            print(f"[ERR]  {fn.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} 通过")
    sys.exit(1 if failed else 0)
