"""一条命令把条款文件（PDF / txt）变成可以检索的语料。

用法：

    # 最简单：只给文件，其它全部自动推断
    python scripts/ingest.py "C:\\Users\\你\\Desktop\\平安e生保.pdf"

    # 想指定产品名（推荐，因为它会显示在引用里）
    python scripts/ingest.py "平安e生保.pdf" --product-name "平安e生保长期医疗险"

    # 只看看识别得对不对，不写文件
    python scripts/ingest.py "平安e生保.pdf" --dry-run

这个脚本把原来三步（抽文本 → 清噪声 → 转 JSON）合成一步，
专治真实 PDF 抽取出来的三个问题：

  1. **每页重复的页眉页脚**（"第 3 页 共 12 页"）→ 会污染所有 chunk，必须去掉
  2. **标题被换行拆开**（"第一条 保险合同的" / "构成"）→ 必须拼回来，
     否则条标题残缺、条号识别不全
  3. **标题和正文挤在一行**（"第一条 保险合同的构成 本保险合同由……"）→ 必须切开，
     否则整条被抓成标题，正文全丢
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import _bootstrap  # noqa: F401

from policyrag.config import get_settings

# --------------------------------------------------------------------------
# 一、噪声识别
# --------------------------------------------------------------------------

# 「第 3 页 共 12 页」「第3页/共12页」「3 / 12」「- 3 -」
_PAGE_NO_RE = re.compile(
    r"^\s*[-—－]?\s*(?:第\s*)?\d{1,4}\s*(?:页)?\s*(?:[/／]|共|of)\s*\d{1,4}\s*(?:页)?\s*[-—－]?\s*$"
)
_BARE_PAGE_RE = re.compile(r"^\s*[-—－]\s*\d{1,4}\s*[-—－]\s*$")
_INLINE_PAGE_NO_RE = re.compile(r"\s*[-—－]\s*\d{1,4}\s*[-—－]\s*$")
_FOOTER_HINTS = ("版权所有", "未经许可", "翻印必究", "http://", "https://", "www.")

# --------------------------------------------------------------------------
# 二、标题识别
# --------------------------------------------------------------------------

_PART_RE = re.compile(r"^第[一二三四五六七八九十百零〇\d]+部分")
_CHAPTER_RE = re.compile(r"^第[一二三四五六七八九十百零〇\d]+章")
_SECTION_RE = re.compile(r"^第[一二三四五六七八九十百零〇\d]+节")
_ARTICLE_RE = re.compile(r"^第[一二三四五六七八九十百零〇\d]+条")
_NUMBERED_RE = re.compile(r"^\d+(?:\.\d+){1,3}\s*\S.{0,79}$")
_APPENDIX_RE = re.compile(r"^附表\s*[0-9一二三四五六七八九十百零〇]+")
_LIST_ITEM_RE = re.compile(r"^[（(]?[一二三四五六七八九十\d]{1,3}[）)、.．]")

_MAX_TITLE_LEN = 40
_MAX_NUMBERED_TITLE_LEN = 100
# 「第X条」后面跟着的这一段，超过这个长度就认为正文跟着一起上来了
_TITLE_TAIL_MAX = 22


def _looks_like_title_text(s: str) -> bool:
    """判断一段文字像不像标题（没有句末标点、不太长）。"""
    s = s.strip()
    if not s or len(s) > _MAX_TITLE_LEN:
        return False
    if s.endswith(("。", "；", "，", "！", "？", "：", "”", "、")):
        return False
    return True


def split_title_and_body(line: str) -> tuple[str, str]:
    """把「第一条 保险合同的构成 本保险合同由……」拆成 (标题, 正文)。

    规则：标题标记词（条/章/节/部分）后面跟的文字，
    如果在 _TITLE_TAIL_MAX 字以内，就当成标题；超出的部分算正文。

    数字编号（1.1）同理。
    """
    s = line.strip()

    # 附表常被 PDF 抽取成「附表 1：表名 + 表格内容」一行；把编号留作标题，
    # 后面的表名和数据都留在正文，避免整张表被吞进标题。
    m = re.match(r"^(附表\s*[0-9一二三四五六七八九十百零〇]+)[\s、.．:：]*(.*)$", s)
    if m:
        marker = re.sub(r"\s+", "", m.group(1))
        return marker, m.group(2).strip()

    m = re.match(
        r"^(第[一二三四五六七八九十百零〇\d]+(?:条|章|节|部分))[\s、.．:：]*(.*)$", s
    )
    if m:
        marker, tail = m.group(1), m.group(2).strip()
        if not tail:
            return marker, ""
        if len(tail) <= _TITLE_TAIL_MAX:
            return f"{marker} {tail}", ""
        # 标题尾巴太长 → 在第一个句末标点或全角空格处切
        cut = _find_cut(tail, _TITLE_TAIL_MAX)
        return f"{marker} {tail[:cut]}".strip(), tail[cut:].strip()

    m = re.match(r"^(\d+(?:\.\d+){1,3})\s*[、.．:：]?\s*(.*)$", s)
    if m:
        marker, tail = m.group(1), m.group(2).strip()
        if not tail:
            return marker, ""
        # 紧凑定义标题（例如 10.8【重大疾病】）和长标题不应按正文切开。
        if _NUMBERED_RE.match(s) and not re.search(r"[。；！？]", s):
            return s, ""
        if len(tail) <= _TITLE_TAIL_MAX:
            return f"{marker} {tail}", ""
        cut = _find_cut(tail, _TITLE_TAIL_MAX)
        return f"{marker} {tail[:cut]}".strip(), tail[cut:].strip()

    return s, ""


def _find_cut(text: str, limit: int) -> int:
    """在 limit 附近找标题的结尾位置。

    优先级：
      1. **空白**（标题与正文之间常常是一个空格）—— 最可靠的信号
      2. 句末/句中标点
      3. 找不到就硬切在 limit

    踩过的坑：最初的版本只在标点里找切点。
    但真实 PDF 抽出来的长行往往是
        "保险合同的构成 本保险合同由保险单、保险条款……共同构成。"
    前半段（标题）和后半段（正文）之间是**一个空格**，
    要一直到很后面才有句号。只在标点里找就会切在 22 字处的半句话上。
    """
    window = text[:limit]
    # 1. 空白优先
    for i in range(len(window) - 1, 0, -1):
        if window[i].isspace():
            return i
    # 2. 标点
    for i in range(len(window) - 1, 0, -1):
        if window[i] in "。；、，：":
            return i + 1
    # 3. 硬切
    return limit


def drop_running_headers(lines: list[str], min_pages: int = 2) -> tuple[list[str], int, int]:
    """按页找并去掉跨页重复的页眉/页脚。

    为什么必须按页：这是唯一可靠的办法。

    踩过的坑（真实）：
    最初靠"整行重复次数 >= 2"来猜页眉。结果是 ——
      · 第 1 页页眉："示例财产保险股份有限公司"        出现 2 次 → 抓到了
      · 第 2 页页眉："示例财产保险股份有限公司 产品名"  出现 1 次 → **漏掉**
      · 第 3 页页眉："示例财产保险股份有限公司"        出现 2 次
    第 2 页那一行因为只出现一次，逃过检测，最后混进了上一条条款的正文里。

    而"每一页的第一行/最后一行"这个位置特征是稳定的，
    不管各页页眉文字是否完全相同。

    注意：这里依赖调用方用 \\f 分页。pypdf 自己**不会**插换页符，
    所以 extract_pdf_text() 显式插入了它。

    返回 (保留的行, 丢弃行数, 页数)
    """
    if "\f" not in "\n".join(lines) and len(lines) and not lines[0].startswith("\f"):
        # 拿不到分页信息 → 退回"重复次数"启发式（能用，但不如按页可靠）
        return _drop_by_repetition(lines)

    text = "\n".join(lines)
    pages = [p for p in text.split("\f")]

    # 收集每页首尾各 2 行
    heads: list[str] = []
    tails: list[str] = []
    for p in pages:
        pl = [x.strip() for x in p.split("\n") if x.strip()]
        if not pl:
            continue
        heads.extend(pl[:2])
        tails.extend(pl[-2:])

    from collections import Counter

    head_c = Counter(heads)
    tail_c = Counter(tails)

    def _is_header_like(s: str) -> bool:
        """判断一行"像不像页眉"。只做形态判断，不看它在几页里出现。

        判据：短、无句末标点、不是条款标题、不是列表项、不是页码。
        """
        if not s or len(s) >= 45:
            return False
        if s.endswith(("。", "；", "！", "？")):
            return False
        # 页首可能是实质条款编号或附表标题；不能因为它出现在页首就当作页眉删掉。
        if _NUMBERED_RE.match(s) or _APPENDIX_RE.match(s) or s.endswith("表"):
            return False
        if re.match(r"^第[一二三四五六七八九十百零〇\d]+(?:条|章|节|部分)", s):
            return False
        if _LIST_ITEM_RE.match(s):
            return False
        if _PAGE_NO_RE.match(s) or _BARE_PAGE_RE.match(s):
            return False
        return True

    def is_running(s: str, counter: Counter, page_count: int) -> bool:
        """出现 >= 2 页才算页眉 —— 这条用来保护文档标题。

        第 1 页的标题「示例e生保长期医疗险条款」也"像页眉"，
        但它只出现在第 1 页，不该被删。所以加一道跨页验证。
        """
        return counter[s] >= min_pages

    def is_page_zone_header(s: str, counter: Counter, page_count: int) -> bool:
        """首尾区域里"像页眉"就丢掉。

        ⚠️ 为什么不要求跨页重复：
        真实 PDF 的页眉经常各页不同（第 1 页只有公司名，
        第 2 页是「公司名 产品名」，奇偶页还可能不一样）。
        靠"重复次数"一定会漏。
        但"它在页面首行/尾行这个位置 + 形态像页眉"这个特征很稳，
        所以按位置判断更可靠。
        代价：只出现在第 1 页的文档标题也会被删 —— 那本来也不是条款内容，
        真正重要的是条款正文，所以可以接受。
        """
        if not _is_header_like(s):
            return False
        # 在不同页的首尾区域各出现过 → 强证据
        if counter[s] >= 2:
            return True
        # 只出现 1 次，但它所在的位置是"非首页的首行/尾行" → 也丢
        return s in single_zone_lines

    # 收集每页首尾各 2 行
    heads: list[str] = []
    tails: list[str] = []
    zone_lines: list[tuple[int, str]] = []      # (页号, 行内容)

    for pi, p in enumerate(pages):
        pl = [x.strip() for x in p.split("\n") if x.strip()]
        if not pl:
            continue
        front = pl[:2]
        back = pl[-2:] if len(pl) > 2 else []
        heads.extend(front)
        tails.extend(back)
        for s in front + back:
            zone_lines.append((pi, s))

    head_c = Counter(heads)
    tail_c = Counter(tails)

    # 非首页的首行 / 非末页的尾行 —— 这些位置几乎只可能是页眉页脚
    single_zone_lines: set[str] = set()
    page_list = [p for p in pages if p.strip()]
    for pi, s in zone_lines:
        if pi > 0 and _is_header_like(s):
            single_zone_lines.add(s)

    kept_pages: list[str] = []
    dropped = 0
    n_pages = len(page_list)

    for p in pages:
        pl = p.split("\n")
        stripped_idx = [i for i, ln in enumerate(pl) if ln.strip()]
        idx_front = set(stripped_idx[:2])
        idx_back = set(stripped_idx[-2:]) if len(stripped_idx) > 2 else set()

        out_lines: list[str] = []
        for i, ln in enumerate(pl):
            s = ln.strip()
            if s and i in idx_front and _is_header_like(s) and (
                head_c[s] >= min_pages or s in single_zone_lines
            ):
                dropped += 1
                continue
            if s and i in idx_back and is_running(s, tail_c, n_pages):
                dropped += 1
                continue
            out_lines.append(ln)
        kept_pages.append("\n".join(out_lines))

    kept = "\n".join(kept_pages).split("\n")
    return [x for x in kept if x.strip()], dropped, n_pages


def _drop_by_repetition(lines: list[str], min_repeat: int = 2) -> tuple[list[str], int, int]:
    """拿不到分页信息时的退路：靠"重复次数 + 短 + 无句末标点"猜页眉。

    不如按页检测准（跨页文字不同的页眉会漏），但比不处理强。
    """
    from collections import Counter

    counter = Counter(ln.strip() for ln in lines if ln.strip())
    dropped = 0
    out: list[str] = []

    for ln in lines:
        s = ln.strip()
        if not s:
            continue
        if (
            counter[s] >= min_repeat
            and len(s) < 40
            and not s.endswith(("。", "；", "！", "？", "："))
            and not re.match(r"^第[一二三四五六七八九十百零〇\d]+(?:条|章|节|部分)", s)
            and not _LIST_ITEM_RE.match(s)
        ):
            dropped += 1
            continue
        out.append(ln)

    return out, dropped, 0


def normalize_lines(lines: list[str]) -> list[str]:
    """把「标题 + 正文」拆成两行。

    ⚠️ 这一步必须在 merge_wrapped_titles 之前做，顺序不能反。

    真实踩过的 bug：
    "第一条 保险合同的构成 本保险合同由保险单、保险条款……"
    这条本来该被拆成标题行 + 正文行。但合并步骤会先看到它，
    发现它是「第X条」开头，于是把下一行「构成」也吸进来，
    变成一条超长行。之后 classify() 因为长度超过 40 直接放弃，
    整条被抓成一个巨大的标题，正文全丢。

    正确顺序：**先拆行内混合，再拼换行续行**。
    """
    out: list[str] = []
    for line in lines:
        title, body = split_title_and_body(line)
        if body:
            out.append(title)
            out.append(body)
        else:
            out.append(line)
    return out


def drop_table_of_contents(lines: list[str]) -> tuple[list[str], int]:
    """去掉封面后的目录块，避免目录页码和省略点进入前言语料。"""
    out: list[str] = []
    in_contents = False
    dropped = 0
    for line in lines:
        s = line.strip()
        if not in_contents and s in {"目录", "目 录"}:
            in_contents = True
            dropped += 1
            continue
        if in_contents:
            # 目录项带点线和页码；正文首个短章标题没有这些标记。
            is_body_chapter = (
                len(s) <= _MAX_TITLE_LEN
                and bool(_CHAPTER_RE.match(s))
                and not re.search(r"(?:\.{2,}|…{2,}|\d\s*$)", s)
            )
            if is_body_chapter:
                in_contents = False
                out.append(line)
            else:
                dropped += 1
            continue
        out.append(line)
    return out, dropped


def normalize_known_tables(lines: list[str]) -> tuple[list[str], int]:
    """把文本层完整保留的伤残比例表改成可检索的等级-比例键值对。"""
    out: list[str] = []
    converted = 0
    i = 0
    while i < len(lines):
        if i + 1 < len(lines) and lines[i].strip().startswith("伤残等级"):
            levels = lines[i].split()[1:]
            rate_match = re.match(r"^\s*保险金给付比例\s+(.+?)\s*$", lines[i + 1])
            rates = re.findall(r"\d+(?:\.\d+)?\s*%", rate_match.group(1)) if rate_match else []
            if len(levels) == 10 and len(rates) == 10:
                pairs = "；".join(f"{level}={rate}" for level, rate in zip(levels, rates))
                out.append(f"伤残等级与保险金给付比例：{pairs}")
                converted += 1
                i += 2
                continue
        out.append(lines[i])
        i += 1
    return out, converted


def merge_wrapped_titles(lines: list[str]) -> list[str]:
    """把被换行拆开的标题拼回来。

    PDF 里很常见：
        第一条 保险合同的
        构成
        本保险合同由保险单……

    「构成」没有句末标点、很短，是标题的续行，必须拼到上一行，
    否则会得到一个残缺的标题「第一条 保险合同的」+ 一个假的标题「构成」。
    """
    out: list[str] = []
    i = 0
    n = len(lines)

    while i < n:
        cur = lines[i]
        # 当前行是不是「条/章/节/部分」标记开头？
        if re.match(r"^第[一二三四五六七八九十百零〇\d]+(?:条|章|节|部分)", cur):
            merged = cur
            j = i + 1
            # 往后最多吸两行续行
            while j < n and j <= i + 2:
                nxt = lines[j].strip()
                # 续行条件：像标题、且不是新的标题标记、且拼接后不太长
                if (
                    _looks_like_title_text(nxt)
                    and not re.match(
                        r"^第[一二三四五六七八九十百零〇\d]+(?:条|章|节|部分)", nxt
                    )
                    and not _NUMBERED_RE.match(nxt)
                    and len(merged) + len(nxt) + 1 <= _MAX_TITLE_LEN
                ):
                    merged = f"{merged} {nxt}"
                    j += 1
                    continue
                break
            out.append(merged)
            i = j
            continue

        out.append(cur)
        i += 1

    return out


# --------------------------------------------------------------------------
# 三、清洗 + 建树
# --------------------------------------------------------------------------

def clean_lines(text: str, keep_formfeed: bool = False) -> tuple[list[str], dict]:
    """去空行 / 页码 / 页脚。

    keep_formfeed：是否保留 \\f 分页标记。
    ⚠️ 必须注意：`str.strip()` 会把 \\f 当空白去掉，
    所以处理 PDF 时如果不显式保留，分页信息会在这一步丢失，
    下游的"按页找页眉"就退化成了不靠谱的"按重复次数猜"。
    """
    stats = {"blank": 0, "page_no": 0, "footer": 0, "total_in": 0}
    out: list[str] = []
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    stats["total_in"] = len(lines)

    for raw in lines:
        # 换页符处理。
        # ⚠️ 实测 pypdf 把 \f 放在**下一页第一行的开头**，不是独立一行：
        #       '\x0c示例财产保险股份有限公司 示例e生保长期医疗险条款'
        #     所以不能只判断"整行等于 \f"，必须把行首的 \f 摘出来。
        line = raw
        had_ff = "\f" in line
        if had_ff:
            line = line.replace("\f", "")
            if keep_formfeed:
                out.append("\f")

        line = line.strip().replace("\u3000", " ")
        # pypdf 偶尔会把下一页页码粘到上一页最后一句后面。只去掉末尾页码，
        # 保留前面的正文，否则页眉清理会把这整句误判成页脚。
        page_suffix = _INLINE_PAGE_NO_RE.search(line)
        if page_suffix and line[:page_suffix.start()].strip():
            line = line[:page_suffix.start()].rstrip()
            stats["page_no"] += 1
        if not line:
            # 整行只有换页符的情况：不算空行
            if not had_ff:
                stats["blank"] += 1
            continue
        if _PAGE_NO_RE.match(line) or _BARE_PAGE_RE.match(line):
            stats["page_no"] += 1
            continue
        if any(h in line for h in _FOOTER_HINTS) and len(line) < 80:
            stats["footer"] += 1
            continue
        out.append(line.strip())

    return out, stats


def classify(line: str) -> tuple[int, str] | None:
    """返回 (level, title) 或 None。level: 1部分 2章 3节/条 4数字编号"""
    s = line.strip()
    if not s:
        return None
    if _APPENDIX_RE.match(s) and len(s) <= _MAX_TITLE_LEN:
        return 1, re.sub(r"\s+", "", s).rstrip("：:")
    if _NUMBERED_RE.match(s) and len(s) <= _MAX_NUMBERED_TITLE_LEN:
        return 4, s
    if len(s) > _MAX_TITLE_LEN:
        return None
    if s.endswith(("。", "；", "，", "！", "？", "：", "”")):
        return None

    if _LIST_ITEM_RE.match(s) and not s.startswith("第"):
        return None
    if _PART_RE.match(s):
        return 1, s
    if _CHAPTER_RE.match(s):
        return 2, s
    if _SECTION_RE.match(s):
        return 3, s
    if _ARTICLE_RE.match(s):
        return 3, s
    return None


def build_sections(lines: list[str]) -> list[dict]:
    """把扁平的行列表按标题重建成嵌套的 sections。

    前提：调用方已经用 normalize_lines() 把「标题 + 正文」拆成了两行。
    这里只负责识别标题、维护层级栈、把正文挂到当前节点。
    """
    root: list[dict] = []
    stack: list[tuple[int, dict]] = []
    preamble: dict | None = None

    def attach(level: int, node: dict) -> None:
        while stack and stack[-1][0] >= level:
            stack.pop()
        if stack:
            stack[-1][1].setdefault("children", []).append(node)
        else:
            root.append(node)
        stack.append((level, node))

    def add_text(txt: str) -> None:
        nonlocal preamble
        if not txt.strip():
            return
        if stack:
            t = stack[-1][1]
            t["text"] = (t.get("text", "") + "\n" + txt).strip()
        else:
            if preamble is None:
                preamble = {"level": 1, "title": "前言", "text": ""}
                root.append(preamble)
                stack.append((1, preamble))
            preamble["text"] = (preamble.get("text", "") + "\n" + txt).strip()

    for line in lines:
        hit = classify(line)
        if hit is None:
            add_text(line)
            continue
        level, title = hit
        attach(level, {"level": level, "title": title, "text": ""})

    def prune(nodes: list[dict]) -> list[dict]:
        out = []
        for n in nodes:
            kids = prune(n.get("children", []))
            text = n.get("text", "").strip()
            if kids:
                n["children"] = kids
            else:
                n.pop("children", None)
            if text:
                n["text"] = text
            if n.get("title") or text or kids:
                out.append(n)
        return out

    return prune(root)


def count_articles(sections: list[dict]) -> tuple[int, list[str]]:
    items: list[str] = []

    def walk(nodes: list[dict], path: list[str]) -> None:
        for n in nodes:
            p = path + [n.get("title", "")]
            if n.get("children"):
                walk(n["children"], p)
            elif n.get("text", "").strip():
                items.append(" > ".join(x for x in p if x))
            elif n.get("title"):
                items.append(" > ".join(x for x in p if x) + "  [无正文]")

    walk(sections, [])
    return len(items), items


# --------------------------------------------------------------------------
# 四、读 PDF / 文本
# --------------------------------------------------------------------------

def extract_pdf_text(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        print("[fail] 需要 pypdf：pip install pypdf")
        sys.exit(1)

    reader = PdfReader(str(path))
    pages: list[str] = []
    empty_pages = 0

    for page in reader.pages:
        t = page.extract_text() or ""
        if t.strip():
            pages.append(t)
        else:
            empty_pages += 1

    if not pages:
        print("\n[fail] 这个 PDF 一页文本都没抽出来。")
        print("       几乎可以确定是**扫描件**（整页是图片，没有文字层）。")
        print("       解决办法：用 OCR 工具先转成文本，比如")
        print("         · Adobe Acrobat 的「识别文本」")
        print("         · 微信/QQ 截图识别、WPS 的 PDF 转文字")
        print("         · 在线工具（注意隐私）")
        print("       转成 txt 后再跑本脚本。")
        sys.exit(1)

    if empty_pages:
        print(f"       [提示] 有 {empty_pages} 页没抽出文本（可能是图片页），已跳过")

    # ⚠️ 关键：pypdf 自己**不会**在页与页之间插入任何分隔符。
    # 实测合并后 \f 的数量是 0，于是"每页首尾行"这个最可靠的页眉特征就丢了。
    # 所以这里显式插入 \f，让下游能按页处理。
    return "\f".join(pages)


def guess_meta(path: Path) -> dict:
    """从文件名猜产品名、doc_id、doc_type。

    真实文件名往往很脏，比如：
        P3754+平安疾病住院（2026）团体医疗保险+条款_2887.pdf
    要清理成：
        product_name = 平安疾病住院（2026）团体医疗保险
        doc_id       = 平安疾病住院-2026-团体医疗保险
        doc_type     = 团体医疗险

    猜不准没关系，用户可以用 --product-name / --doc-id 覆盖。
    """
    stem = path.stem

    # ① 先把分隔符统一成空格，便于后续处理
    s = re.sub(r"[+_]+", " ", stem)
    s = re.sub(r"\s{2,}", " ", s).strip()

    # ② 去掉产品编号前缀。
    #    注意：前缀必须是**英文字母 + 数字**（如 P3754 / ABC123），
    #    不能用 [A-Za-z]{1,4}\d+ —— 那会把「P3754」这种匹配成
    #    「P + 3754」，但也会误伤更长的字母数字组合。
    s = re.sub(r"^[A-Za-z]{1,4}\d{2,6}\s+", "", s).strip()
    #    纯数字前缀（如 12345 xxx）
    s = re.sub(r"^\d{3,8}\s+", "", s).strip()

    # ③ 先去掉尾部产品码，再去掉尾部说明词。
    #    ⚠️ 顺序不能反。"团体医疗保险 条款 2887" 这种，
    #    如果先删「条款」，它不在结尾（后面还有 2887），删不掉；
    #    删完 2887 之后「条款」才露到结尾，这时才能删。
    s = re.sub(r"\s*\d{4,}$", "", s).strip()
    s = re.sub(r"(\s*(条款|保险条款|产品条款|条款及费率表|条款费率|费率表))+$", "", s).strip()

    cleaned = s or stem

    # ③ 猜险种
    doc_type = ""
    TYPE_RULES = [
        ("团体医疗", "团体医疗险"),
        ("百万医疗", "百万医疗险"),
        ("住院医疗", "住院医疗险"),
        ("住院", "住院医疗险"),
        ("门急诊", "门急诊医疗险"),
        ("防癌", "防癌险"),
        ("重疾", "重疾险"),
        ("重大疾病", "重疾险"),
        ("意外", "意外险"),
        ("定期寿", "定期寿险"),
        ("年金", "年金险"),
        ("医疗", "医疗险"),
    ]
    for kw, label in TYPE_RULES:
        if kw in stem:
            doc_type = label
            break

    # ④ doc_id：保留中文（可读），把不适合做 ID 的字符换掉
    doc_id = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "-", cleaned).strip("-")
    doc_id = re.sub(r"-{2,}", "-", doc_id)[:50] or "doc"

    return {
        "product_name": cleaned,
        "doc_type": doc_type,
        "doc_id": doc_id,
    }


# --------------------------------------------------------------------------
# 五、主流程
# --------------------------------------------------------------------------

def convert(path: Path, args) -> int:
    is_pdf = path.suffix.lower() == ".pdf"

    print("=" * 70)
    print(f"文件：{path.name}")
    print(f"类型：{'PDF' if is_pdf else '文本'}")

    if is_pdf:
        text = extract_pdf_text(path)
    else:
        text = path.read_text(encoding="utf-8", errors="replace")

    # --- 噪声清洗（PDF 要保留 \f 分页标记，供页眉检测使用）---
    lines, stats = clean_lines(text, keep_formfeed=is_pdf)
    print("-" * 70)
    print(f"读入 {stats['total_in']} 行 → 保留 {len([x for x in lines if x.strip() != chr(12)])} 行")
    print(
        f"  丢弃：空行 {stats['blank']}，页码 {stats['page_no']}，页脚 {stats['footer']}"
    )

    # --- 处理顺序很重要，不能颠倒 ---
    # ① 去页码/页脚（先做，否则页脚会干扰"每页最后一行"的判断）
    # ② 去跨页重复的页眉（按页处理，需要 ① 已经清过页脚）
    # ③ 拆「标题 + 正文挤在一行」
    # ④ 拼「标题被换行拆开」
    # ② 和 ③ 如果颠倒，第 ③ 步的目标行会先被合并成超长行，然后就再也拆不开了。
    lines, headers, n_pages = drop_running_headers(lines)
    if headers:
        pages_info = f"（{n_pages} 页）" if n_pages else ""
        print(f"  丢弃跨页重复的页眉/页脚：{headers} 行{pages_info}")

    lines, toc_lines = drop_table_of_contents(lines)
    if toc_lines:
        print(f"  丢弃目录块：{toc_lines} 行")

    normalized = normalize_lines(lines)
    inline_split = len(normalized) - len(lines)
    if inline_split:
        print(f"  拆开挤在一行的「标题 + 正文」：{inline_split} 处")

    normalized, tables_normalized = normalize_known_tables(normalized)
    if tables_normalized:
        print(f"  结构化表格行：{tables_normalized} 组")

    before = len(normalized)
    normalized = merge_wrapped_titles(normalized)
    merged = before - len(normalized)
    if merged:
        print(f"  拼回被换行拆开的标题：{merged} 处")

    # --- 建房 ---
    sections = build_sections(normalized)
    count, items = count_articles(sections)

    print(f"识别出可检索条款：{count} 条")

    if count == 0:
        print("-" * 70)
        print("[失败] 一条都没识别出来。可能的原因：")
        print("  · 条款标题不是独占一行，也不是「第X条」开头")
        print("  · 用的是「一、」「（一）」这种序号（本工具无法与列表项区分）")
        print("  · PDF 是扫描件，抽出来是乱码")
        print("\n前 15 行实际读到的内容（帮你看清问题）：")
        for ln in lines[:15]:
            print(f"    | {ln[:70]}")
        return 0

    print("  前几条：")
    for s in items[:8]:
        print(f"    · {s}")
    if count > 8:
        print(f"    …… 还有 {count - 8} 条")

    if args.dry_run:
        print("\n[预览模式] 没有写文件。确认无误后去掉 --dry-run 再跑一次。")
        return count

    # --- 元信息 ---
    guess = guess_meta(path)
    doc_id = args.doc_id or guess["doc_id"]
    product_name = args.product_name or guess["product_name"]
    doc_type = args.doc_type or guess["doc_type"]

    doc = {
        "doc_id": doc_id,
        "product_name": product_name,
        "company": args.company or "",
        "version": args.version or "",
        "doc_type": doc_type,
        "effective_date": args.effective_date or "",
        "source_pdf": path.name if is_pdf else "",
        "sections": sections,
    }

    out_dir = Path(args.out_dir) if args.out_dir else get_settings().raw_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{doc_id}.json"

    if out_path.exists() and not args.force:
        print(f"\n[中止] {out_path} 已存在。")
        print("       换个 --doc-id，或加 --force 覆盖。")
        return 0

    out_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")

    print("-" * 70)
    print(f"[ok] 写入 {out_path}  （{out_path.stat().st_size / 1024:.0f} KB）")
    print(f"     doc_id       = {doc_id}")
    print(f"     product_name = {product_name}")
    print(f"     doc_type     = {doc_type or '（未猜出，不影响使用）'}")
    print()
    print("下一步：")
    print("  1. 重建索引：  python scripts/build_index.py --rebuild")
    print("  2. 确认入库：  python scripts/cli.py products")
    print(f"  3. 试问一句：  python scripts/cli.py ask \"等待期是多少天\" --docs {doc_id}")
    return count


def main() -> int:
    ap = argparse.ArgumentParser(
        description="条款 PDF / 文本 一条命令入库",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "例子：\n"
            "  python scripts/ingest.py 平安e生保.pdf\n"
            "  python scripts/ingest.py 平安e生保.pdf --product-name \"平安e生保长期医疗险\"\n"
            "  python scripts/ingest.py 平安e生保.pdf --dry-run\n"
        ),
    )
    ap.add_argument("file", help="条款文件（.pdf 或 .txt）")
    ap.add_argument("--doc-id", help="文档 ID，默认从文件名推断")
    ap.add_argument("--product-name", help="产品名，默认从文件名推断")
    ap.add_argument("--company", default="")
    ap.add_argument("--version", default="")
    ap.add_argument("--doc-type", default="")
    ap.add_argument("--effective-date", default="")
    ap.add_argument("--out-dir", default=None, help="默认 data/raw")
    ap.add_argument("--dry-run", action="store_true", help="只看识别结果，不写文件")
    ap.add_argument("--force", action="store_true", help="覆盖同名文件")
    args = ap.parse_args()

    path = Path(args.file)
    if not path.exists():
        print(f"[fail] 文件不存在：{path}")
        return 1

    n = convert(path, args)
    return 0 if n else 1


if __name__ == "__main__":
    sys.exit(main())
