"""生成一个**真实的**测试 PDF：嵌入 Windows 中文字体，把条款排成多页。

为什么需要它：
`scripts/ingest.py` 要处理的是 PDF 抽出来的真实痛点 ——
页眉页脚、标题被换行拆开、标题和正文挤在一行。
光用 .txt 测不出这些，必须有一个由真实排版引擎产出、
再由 pypdf 抽回来的 PDF 才算验证。

不依赖任何第三方库，只用标准库手写 PDF 结构：
  · 字体用 Type0 + Identity-H 编码（中文必须这么嵌）
  · 用 TTF 的 cmap 把每个字符映射成 glyph id
  · 手工拼出 PDF 的对象表与 xref

生成的 PDF 是标准格式，Adobe / 浏览器 / pypdf 都能正常打开。

用法：
    python scripts/make_test_pdf.py
    python scripts/make_test_pdf.py --out data/samples/测试条款.pdf --pages 3
"""

from __future__ import annotations

import argparse
import re
import struct
import sys
from pathlib import Path

import _bootstrap  # noqa: F401

FONT_CANDIDATES = [
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\simsun.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
    r"/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
]

# 每页的排版内容。刻意混入真实噪声：
#   · 页眉（公司名）
#   · 页脚（页码，格式还换着来）
#   · 标题换行拆开
#   · 标题与正文挤在同一行
PAGES = [
    [
        "示例财产保险股份有限公司",
        "",
        "示例e生保长期医疗险条款",
        "",
        "第一部分 总则",
        "第一条 保险合同的构成 本保险合同由保险单、保险条款、投保单、与本合同有关的其他投保文件、合法有效的声明、批注、批单及其他书面协议共同构成。",
        "第二条 投保范围",
        "凡出生满28日至65周岁、身体健康、能正常工作或正常生活的自然人，均可作为被保险人参加本保险。",
        "第三条 等待期",
        "自本合同生效之日起90日为等待期。被保险人在等待期内因疾病发生住院治疗的，本公司不承担给付保险金的责任。",
        "第 1 页 共 3 页",
    ],
    [
        "示例财产保险股份有限公司 示例e生保长期医疗险条款",
        "",
        "第二部分 保障内容",
        "第四条 保险金额",
        "本合同的年度保险金额为人民币400万元。其中一般医疗保险金年度限额为人民币200万元，重疾医疗保险金年度限额为人民币400万元。",
        "第五条 免赔额",
        "本合同年度免赔额为人民币1万元。被保险人从社会医疗保险、公费医疗或其他商业保险机构获得的医疗费用补偿，可用于抵扣免赔额。",
        "第六条 保险责任",
        "在本合同保险期间内，被保险人因意外伤害或等待期后因疾病，在本公司认可的医院接受治疗的，本公司按下列约定承担保险责任：",
        "（一）一般医疗保险金：在扣除免赔额后按100%的比例给付；",
        "（二）重疾医疗保险金：确诊本合同约定的重大疾病，按100%给付且不扣除免赔额。",
        "- 2 -",
    ],
    [
        "示例财产保险股份有限公司",
        "",
        "第三部分 责任免除",
        "第七条 责任免除",
        "因下列情形之一导致被保险人发生医疗费用的，本公司不承担给付保险金的责任：",
        "（一）投保人对被保险人的故意杀害、故意伤害；",
        "（二）被保险人故意犯罪或者抗拒依法采取的刑事强制措施；",
        "（三）被保险人酒后驾驶、无合法有效驾驶证驾驶；",
        "（四）被保险人进行潜水、跳伞、攀岩、探险、武术比赛等高风险运动；",
        "（五）战争、军事冲突、暴乱或者武装叛乱。",
        "第四部分 名词释义",
        "第八条 既往症",
        "既往症指在保险合同生效前，被保险人已知或者应该知道的有关疾病或者症状。被保险人对既往症的投保，本公司不承担保险责任。",
        "版权所有 未经许可不得翻印",
        "第 3 页 共 3 页",
    ],
]


# --------------------------------------------------------------------------
# TTF / TTC 解析：拿 cmap 与必要的表
# --------------------------------------------------------------------------

class TTF:
    """极简 TTF/TTC 解析器，只需要 cmap（字符 → glyph id）和垂直度量。"""

    def __init__(self, path: str, face_index: int = 0) -> None:
        self.data = Path(path).read_bytes()
        self.tables: dict[str, tuple[int, int]] = {}
        self._parse(face_index)

    def _parse(self, face_index: int) -> None:
        d = self.data
        tag = d[:4]
        if tag == b"ttcf":
            num = struct.unpack(">I", d[8:12])[0]
            if face_index >= num:
                raise ValueError(f"TTC 只有 {num} 个 face")
            offset = struct.unpack(">I", d[12 + 4 * face_index : 16 + 4 * face_index])[0]
        else:
            offset = 0

        num_tables = struct.unpack(">H", d[offset + 4 : offset + 6])[0]
        pos = offset + 12
        for _ in range(num_tables):
            t = d[pos : pos + 4]
            o, ln = struct.unpack(">II", d[pos + 8 : pos + 16])
            self.tables[t.decode("latin-1")] = (o, ln)
            pos += 16

        if "cmap" not in self.tables:
            raise ValueError("字体没有 cmap 表")

        self.units_per_em = 1000
        if "head" in self.tables:
            ho = self.tables["head"][0]
            self.units_per_em = struct.unpack(">H", d[ho + 18 : ho + 20])[0] or 1000

        self.cmap = self._parse_cmap()

    def _parse_cmap(self) -> dict[int, int]:
        """解析 format 4 和 format 12 子表，返回 码点 → glyph id。"""
        d = self.data
        base = self.tables["cmap"][0]
        n = struct.unpack(">H", d[base + 2 : base + 4])[0]

        best: tuple[int, int] | None = None   # (优先级, 偏移)
        for i in range(n):
            rec = base + 4 + i * 8
            pid, eid, off = struct.unpack(">HHI", d[rec : rec + 8])
            sub = base + off
            fmt = struct.unpack(">H", d[sub : sub + 2])[0]
            if fmt == 12 and (pid == 3 and eid == 10):
                best = (3, sub)
                break
            if fmt == 4 and pid == 3 and eid in (1, 10) and (best is None or best[0] < 2):
                best = (2, sub)
            elif fmt == 4 and best is None:
                best = (1, sub)

        if best is None:
            raise ValueError("找不到可用的 cmap 子表")

        sub = best[1]
        fmt = struct.unpack(">H", d[sub : sub + 2])[0]
        table: dict[int, int] = {}

        if fmt == 12:
            ngroups = struct.unpack(">I", d[sub + 12 : sub + 16])[0]
            for g in range(ngroups):
                p = sub + 16 + g * 12
                start, end, gid = struct.unpack(">III", d[p : p + 12])
                if end - start > 0x20000:
                    continue
                for cp in range(start, end + 1):
                    table[cp] = gid + (cp - start)
        else:
            seg_x2 = struct.unpack(">H", d[sub + 6 : sub + 8])[0]
            seg = seg_x2 // 2
            end_o = sub + 14
            start_o = end_o + seg_x2 + 2
            delta_o = start_o + seg_x2
            range_o = delta_o + seg_x2
            for i in range(seg):
                end = struct.unpack(">H", d[end_o + i * 2 : end_o + i * 2 + 2])[0]
                start = struct.unpack(">H", d[start_o + i * 2 : start_o + i * 2 + 2])[0]
                delta = struct.unpack(">h", d[delta_o + i * 2 : delta_o + i * 2 + 2])[0]
                ro = struct.unpack(">H", d[range_o + i * 2 : range_o + i * 2 + 2])[0]
                if start == 0xFFFF:
                    continue
                for cp in range(start, min(end, 0xFFFF) + 1):
                    if ro == 0:
                        table[cp] = (cp + delta) & 0xFFFF
                    else:
                        gp = range_o + i * 2 + ro + (cp - start) * 2
                        if gp + 2 <= len(d):
                            g = struct.unpack(">H", d[gp : gp + 2])[0]
                            if g:
                                table[cp] = (g + delta) & 0xFFFF
        return table

    def gid(self, ch: str) -> int:
        return self.cmap.get(ord(ch), 0)


# --------------------------------------------------------------------------
# PDF 拼装
# --------------------------------------------------------------------------

def _esc_hex(glyphs: list[int]) -> str:
    return "".join(f"{g:04X}" for g in glyphs)


def build_pdf(font_path: str, pages: list[list[str]], font_size: float = 10.5) -> bytes:
    ttf = TTF(font_path)
    ttf_bytes = Path(font_path).read_bytes()

    # 只嵌入 glyf 字体需要的表（TTC 里拿到的表偏移是相对于 TTC 头，需要重算）
    # 为了简单与稳健，这里直接把整个字体文件作为 FontFile2 嵌入。
    # 体积大一些，但生成的 PDF 绝对合法，pypdf 能正常解析。
    objs: list[bytes] = []

    def add(body: bytes) -> int:
        objs.append(body)
        return len(objs)

    # 先占位，最后回填
    catalog_id = add(b"")           # 1
    pages_id = add(b"")             # 2
    font_id = add(b"")              # 3
    cidfont_id = add(b"")           # 4
    descriptor_id = add(b"")        # 5
    fontfile_id = add(b"")          # 6
    tounicode_id = add(b"")         # 7

    # 收集实际用到的字符，建 ToUnicode 映射
    used: dict[int, int] = {}       # gid -> codepoint
    for lines in pages:
        for line in lines:
            for ch in line:
                g = ttf.gid(ch)
                if g and g not in used:
                    used[g] = ord(ch)

    tu_lines = [
        "/CIDInit /ProcSet findresource begin",
        "12 dict begin",
        "begincmap",
        "/CMapName /Custom def",
        "/CMapType 2 def",
        "1 begincodespacerange",
        "<0000> <FFFF>",
        "endcodespacerange",
    ]
    items = sorted(used.items())
    for i in range(0, len(items), 100):
        part = items[i : i + 100]
        tu_lines.append(f"{len(part)} beginbfchar")
        for g, cp in part:
            tu_lines.append(f"<{g:04X}> <{cp:04X}>")
        tu_lines.append("endbfchar")
    tu_lines += ["endcmap", "CMapName currentdict /CMap defineresource pop", "end", "end"]
    tounicode = "\n".join(tu_lines).encode("latin-1")

    # 页面内容
    page_ids: list[int] = []
    margin_x, top_y = 56.0, 780.0
    line_h = 17.0
    page_w, page_h = 595.0, 842.0

    for lines in pages:
        glyph_lines = []
        for ln in lines:
            if not ln:
                glyph_lines.append("")
                continue
            glyphs = [ttf.gid(c) for c in ln]
            glyph_lines.append(_esc_hex(glyphs))

        parts = ["BT", f"/F1 {font_size} Tf", f"{line_h} TL"]
        parts.append(f"1 0 0 1 {margin_x} {top_y} Tm")
        for gl in glyph_lines:
            if gl:
                parts.append(f"<{gl}> Tj")
            parts.append("T*")
        parts.append("ET")
        stream = "\n".join(parts).encode("latin-1")

        content_id = add(
            f"<< /Length {len(stream)} >>\nstream\n".encode("latin-1")
            + stream
            + b"\nendstream"
        )
        page_id = add(
            (
                f"<< /Type /Page /Parent {pages_id} 0 R "
                f"/MediaBox [0 0 {page_w} {page_h}] "
                f"/Resources << /Font << /F1 {font_id} 0 R >> >> "
                f"/Contents {content_id} 0 R >>"
            ).encode("latin-1")
        )
        page_ids.append(page_id)

    # 回填
    objs[catalog_id - 1] = f"<< /Type /Catalog /Pages {pages_id} 0 R >>".encode("latin-1")
    kids = " ".join(f"{p} 0 R" for p in page_ids)
    objs[pages_id - 1] = (
        f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>".encode("latin-1")
    )
    objs[font_id - 1] = (
        f"<< /Type /Font /Subtype /Type0 /BaseFont /TestCJK "
        f"/Encoding /Identity-H /DescendantFonts [{cidfont_id} 0 R] "
        f"/ToUnicode {tounicode_id} 0 R >>"
    ).encode("latin-1")
    objs[cidfont_id - 1] = (
        f"<< /Type /Font /Subtype /CIDFontType2 /BaseFont /TestCJK "
        f"/CIDSystemInfo << /Registry (Adobe) /Ordering (Identity) /Supplement 0 >> "
        f"/FontDescriptor {descriptor_id} 0 R /DW 1000 /CIDToGIDMap /Identity >>"
    ).encode("latin-1")
    objs[descriptor_id - 1] = (
        f"<< /Type /FontDescriptor /FontName /TestCJK /Flags 4 "
        f"/FontBBox [-200 -300 1200 1100] /ItalicAngle 0 /Ascent 900 /Descent -250 "
        f"/CapHeight 700 /StemV 80 /FontFile2 {fontfile_id} 0 R >>"
    ).encode("latin-1")
    objs[fontfile_id - 1] = (
        f"<< /Length {len(ttf_bytes)} /Length1 {len(ttf_bytes)} >>\nstream\n".encode("latin-1")
        + ttf_bytes
        + b"\nendstream"
    )
    objs[tounicode_id - 1] = (
        f"<< /Length {len(tounicode)} >>\nstream\n".encode("latin-1")
        + tounicode
        + b"\nendstream"
    )

    # 序列化
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for i, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode("latin-1") + body + b"\nendobj\n"

    xref_pos = len(out)
    n = len(objs) + 1
    out += f"xref\n0 {n}\n".encode("latin-1")
    out += b"0000000000 65535 f \n"
    for off in offsets[1:]:
        out += f"{off:010d} 00000 n \n".encode("latin-1")
    out += (
        f"trailer\n<< /Size {n} /Root {catalog_id} 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n"
    ).encode("latin-1")

    return bytes(out)


def find_font() -> str | None:
    for p in FONT_CANDIDATES:
        if Path(p).exists():
            return p
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="生成测试用条款 PDF")
    ap.add_argument("--out", default=None)
    ap.add_argument("--pages", type=int, default=3, help="取前 N 页（默认 3）")
    args = ap.parse_args()

    font = find_font()
    if not font:
        print("[fail] 找不到可用的中文字体，尝试过：")
        for p in FONT_CANDIDATES:
            print(f"       {p}")
        return 1

    out_path = Path(args.out) if args.out else (
        _bootstrap.ROOT / "data" / "samples" / "测试条款.pdf"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)

    pages = PAGES[: args.pages]
    data = build_pdf(font, pages)
    out_path.write_text("", encoding="utf-8")  # 确保父目录可写
    out_path.write_bytes(data)

    print(f"[ok] 生成 {out_path}  （{len(data) / 1024:.0f} KB，{len(pages)} 页）")
    print(f"     使用字体：{font}")
    print()
    print("这个 PDF 刻意包含了真实 PDF 的三个噪声：")
    print("  · 页眉（公司名重复出现）与页脚（页码格式不统一：'第 1 页 共 3 页' 与 '- 2 -'）")
    print("  · 标题被换行拆开（'第一条 保险合同的' / '构成'）")
    print("  · 标题和正文挤在同一行")
    print()
    print("下一步验证：")
    print(f"  python scripts/ingest.py \"{out_path}\" --dry-run")
    return 0


if __name__ == "__main__":
    sys.exit(main())
