"""环境与链路自检 —— 不依赖任何外部服务，先确认"能不能跑"。

用法：
    python scripts/selfcheck.py

检查项：
    1. Python 版本与依赖
    2. 语料是否存在
    3. 切分器是否正常工作（含标题识别单测）
    4. embedding provider 是否可用
    5. LLM provider 是否可用
    6. 索引是否存在且与当前 embedding 匹配
"""

from __future__ import annotations

import sys

import _bootstrap  # noqa: F401

OK = "[ok]  "
WARN = "[warn]"
FAIL = "[fail]"

from policyrag.config import get_settings


def check_python() -> bool:
    v = sys.version_info
    print(f"{OK} Python {v.major}.{v.minor}.{v.micro}")
    if v < (3, 10):
        print(f"{FAIL} 需要 Python 3.10+（用到了 `X | None` 语法）")
        return False
    if v >= (3, 14):
        print(f"{WARN} Python 3.14 很新，chromadb / sentence-transformers 等可能没有轮子")
        print(f"       本项目默认实现零依赖，不受影响；要上生产建议用 3.11/3.12")
    return True


def check_deps() -> bool:
    ok = True
    for mod, why, required in (
        ("numpy", "向量运算", True),
        ("jieba", "中文分词（BM25 用）", False),
        ("fastapi", "API 服务", False),
        ("uvicorn", "运行服务", False),
        ("pypdf", "PDF 解析", False),
        ("requests", "调用 embedding / LLM 接口", False),
    ):
        try:
            __import__(mod)
            print(f"{OK} {mod:12s} 已安装（{why}）")
        except ImportError:
            mark = FAIL if required else WARN
            print(f"{mark} {mod:12s} 未安装（{why}）  →  pip install {mod}")
            ok = ok and not required
    return ok


def check_data() -> bool:
    from policyrag.ingest.loaders import load_documents

    s = get_settings()
    docs, warnings = load_documents(s.raw_dir)
    for w in warnings:
        print(f"{WARN} {w}")
    if not docs:
        return False
    print(f"{OK} 语料 {len(docs)} 份：")
    for d in docs:
        print(f"       {d.doc_id:28s} 《{d.display_name}》 {d.doc_type}")
    return True


def check_chunker() -> bool:
    from policyrag.ingest.chunker import detect_heading
    from policyrag.ingest.loaders import load_documents
    from policyrag.ingest.chunker import chunk_document

    cases = [
        ("第一条 保险合同的构成", "article"),
        ("第六条", "article"),
        ("第一章 总则", "chapter"),
        ("1.1 保险责任", "numbered"),
        ("保险期间为一年。", None),
        ("（一）投保人故意造成被保险人伤害；", None),
        ("这一行是普通正文内容，不应该被识别成标题", None),
    ]
    bad = 0
    for text, expect in cases:
        got = detect_heading(text)
        got_kind = got[0] if got else None
        if got_kind != expect:
            print(f"{FAIL} 标题识别错误：{text!r} → 期望 {expect}，实际 {got_kind}")
            bad += 1
    if bad == 0:
        print(f"{OK} 标题识别 {len(cases)} 个用例全部通过")

    s = get_settings()
    docs, _ = load_documents(s.raw_dir)
    total = 0
    for d in docs:
        chunks = chunk_document(d, s.chunk)
        total += len(chunks)
        if chunks:
            no_art = sum(1 for c in chunks if not c.article_no)
            print(f"       {d.doc_id}: {len(chunks)} chunks，未识别条款号 {no_art} 个")
    if total == 0:
        print(f"{FAIL} 切分结果为 0")
        return False
    print(f"{OK} 切分正常，共 {total} 个 chunk")
    return bad == 0


def check_embedding() -> bool:
    from policyrag.embedding.base import build_embedder

    s = get_settings()
    try:
        e = build_embedder(s.embedding)
    except Exception as ex:                                 # noqa: BLE001
        print(f"{FAIL} embedding provider={s.embedding.provider} 不可用：{ex}")
        return False

    try:
        vecs = e.embed_documents(["等待期是多少天", "保险责任包括哪些内容"])
    except Exception as ex:                                 # noqa: BLE001
        print(f"{FAIL} embedding 调用失败：{ex}")
        return False

    print(f"{OK} embedding provider={s.embedding.provider}  signature={e.signature}  dim={vecs.shape[1]}")
    if s.embedding.provider == "hash":
        print(f"{WARN} hash 是兜底方案，只能跑通链路。**用它得到的评测数字没有意义**")
        print(f"       换真实模型：$env:PR_EMB_PROVIDER='api'; $env:PR_EMB_API_KEY='sk-...'")
    return True


def check_llm() -> bool:
    from policyrag.generation.generator import build_llm, parse_answer

    s = get_settings()
    try:
        llm = build_llm(s.llm)
    except Exception as ex:                                 # noqa: BLE001
        print(f"{FAIL} LLM provider={s.llm.provider} 不可用：{ex}")
        return False

    print(f"{OK} LLM provider={s.llm.provider}  model={llm.name}")
    if s.llm.provider == "mock":
        print(f"{WARN} mock 模式不调用真实模型，回答是占位文本。评测前必须换成 api")

    # 结构化输出解析的单测（这个不依赖外部服务）
    ans, answerable, cites, used = parse_answer(
        '```json\n{"answer":"90天【安心保 第三条】","citations":'
        '[{"product_name":"安心保百万医疗险","article_no":"第三条","quote":"90日"}],'
        '"answerable":true,"used_articles":["第三条"]}\n```',
        [],
    )
    if "90天" not in ans or not answerable:
        print(f"{FAIL} 结构化输出解析异常：{ans!r}")
        return False
    print(f"{OK} 结构化输出解析（含 ```json 包裹）通过")
    return True


def check_index() -> bool:
    from policyrag.embedding.base import build_embedder
    from policyrag.index.vector_store import NumpyVectorStore

    s = get_settings()
    store = NumpyVectorStore()
    try:
        store.load(s.index_dir, expect_signature=build_embedder(s.embedding).signature)
    except Exception as ex:                                 # noqa: BLE001
        print(f"{WARN} 索引不可用：{ex}")
        return False
    print(f"{OK} 索引 {store.size} chunks，signature={store.signature}")
    return True


def main() -> int:
    print("=" * 68)
    print("保险条款 RAG · 自检")
    print("=" * 68)
    results = {
        "Python 环境": check_python(),
        "依赖": check_deps(),
        "语料": check_data(),
        "切分器": check_chunker(),
        "Embedding": check_embedding(),
        "LLM": check_llm(),
        "索引": check_index(),
    }
    print("=" * 68)
    for k, v in results.items():
        print(f"  {k:12s} {'通过' if v else '未就绪'}")
    print("=" * 68)

    if not all(results.values()):
        print("\n下一步：")
        if not results["语料"]:
            print("  python scripts/make_sample_data.py")
        if not results["索引"]:
            print("  python scripts/build_index.py")
        return 1
    print("\n全部就绪。下一步：python scripts/cli.py ask \"等待期是多少天\"")
    return 0


if __name__ == "__main__":
    sys.exit(main())
