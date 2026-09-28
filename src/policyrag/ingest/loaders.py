"""语料加载：JSON（推荐）/ PDF / 纯文本 → Document。"""

from __future__ import annotations

import json
from pathlib import Path

from ..schema import Document
from .chunker import sections_from_plain_text


class LoadError(RuntimeError):
    pass


def load_json_document(path: Path) -> Document:
    """加载结构化条款 JSON。"""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise LoadError(f"{path.name} 不是合法 JSON：{e}") from e

    if "doc_id" not in payload:
        raise LoadError(f"{path.name} 缺少必填字段 doc_id")

    doc = Document.from_dict(payload)
    if not doc.sections:
        raise LoadError(f"{path.name} 的 sections 为空，没有可检索内容")
    doc.source_path = str(path)
    return doc


def load_pdf_document(path: Path, doc_id: str, meta: dict | None = None) -> Document:
    """从 PDF 抽文本。

    ⚠️ 已知限制（要写进 README，别装作没有）：
    - 只支持**文本型 PDF**，扫描件抽出来是空的
    - 表格会抽成错乱文本（现金价值表、保障责任表尤其明显）
    所以：真实语料建议先转成 JSON 再入库。
    """
    try:
        from pypdf import PdfReader
    except ImportError as e:
        raise LoadError("未安装 pypdf，先执行：pip install pypdf") from e

    reader = PdfReader(str(path))
    pages: list[str] = []
    for i, page in enumerate(reader.pages):
        t = page.extract_text() or ""
        if not t.strip():
            continue
        pages.append(t)

    if not pages:
        raise LoadError(
            f"{path.name} 没抽出任何文本 —— 很可能是扫描件（图片 PDF）。"
            "需要 OCR，或先手工转成 JSON/文本。"
        )

    meta = meta or {}
    return Document(
        doc_id=doc_id,
        product_name=meta.get("product_name", path.stem),
        company=meta.get("company", ""),
        version=meta.get("version", ""),
        doc_type=meta.get("doc_type", ""),
        effective_date=meta.get("effective_date", ""),
        source_path=str(path),
        sections=sections_from_plain_text("\n".join(pages)),
    )


def load_text_document(path: Path, doc_id: str, meta: dict | None = None) -> Document:
    meta = meta or {}
    text = path.read_text(encoding="utf-8", errors="replace")
    return Document(
        doc_id=doc_id,
        product_name=meta.get("product_name", path.stem),
        company=meta.get("company", ""),
        version=meta.get("version", ""),
        doc_type=meta.get("doc_type", ""),
        effective_date=meta.get("effective_date", ""),
        source_path=str(path),
        sections=sections_from_plain_text(text),
    )


def load_documents(raw_dir: Path) -> tuple[list[Document], list[str]]:
    """扫描目录，加载所有支持的语料。

    支持的格式：
      .json           结构化条款（推荐，条号与层级最准）
      .pdf            文本型 PDF（扫描件会明确报错）
      .txt / .text    纯文本条款（标题需独占一行）

    不加载：.md / .markdown / .csv  —— 这些是说明性文件，不是语料。

    返回 (documents, warnings)。warnings 会打印出来，不静默失败。
    """
    docs: list[Document] = []
    warnings: list[str] = []

    # 「设计上不当作语料」的格式
    SKIP_SUFFIXES = {".md", ".markdown", ".csv"}

    for path in sorted(raw_dir.rglob("*")):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()

        if suffix in SKIP_SUFFIXES:
            continue
        if path.name.startswith("."):
            continue

        try:
            if suffix == ".json":
                docs.append(load_json_document(path))
            elif suffix == ".pdf":
                docs.append(load_pdf_document(path, doc_id=path.stem))
            elif suffix in {".txt", ".text", ".policy"}:
                # ⚠️ 之前 .txt 被静默跳过，用户把在线工具转出的 txt 丢进来
                # 会「什么都没发生」且没有任何提示 —— 这是个真实的坑。
                # 现在按纯文本加载：用标题识别重建层级（不需要人工转 JSON）。
                docs.append(load_text_document(path, doc_id=path.stem))
        except LoadError as e:
            warnings.append(f"[跳过] {e}")
        except Exception as e:                     # noqa: BLE001 - 兜底不中断整批
            warnings.append(f"[跳过] {path.name} 加载异常：{type(e).__name__}: {e}")

    if not docs:
        warnings.append(
            f"{raw_dir} 下没有找到任何语料。\n"
            f"        放一个 .json / .pdf / .txt 进去，或运行：python scripts/make_sample_data.py"
        )
    return docs, warnings
