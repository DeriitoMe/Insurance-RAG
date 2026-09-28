"""评测脚本 —— 整个项目最值钱的部分。

用法：
    python scripts/eval.py --mode all                 # 三种检索模式对照（推荐先跑这个）
    python scripts/eval.py --mode hybrid --gen        # 带生成层评估（需要真实 LLM）
    python scripts/eval.py --mode hybrid --gen --judge

产出：
    - 终端对照表（Hit Rate / MRR / 全部命中率）
    - eval/results/<时间戳>-<mode>.json  逐题明细，可追溯
    - 追加一行到 docs/03-迭代日志.md 的统计（由你手工整理，脚本只给数字）

⚠️ 当 embedding 是 hash provider 或 LLM 是 mock 时，脚本会明确警告：
   这些数字**不能写进简历**，只说明链路是通的。
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path

import _bootstrap  # noqa: F401

from policyrag.config import get_settings
from policyrag.metrics import (
    GenMetrics,
    RetrievalMetrics,
    evaluate_retrieval_row,
    judge_with_llm,
    parse_expected_articles,
)
from policyrag.pipeline import Pipeline

ROOT = _bootstrap.ROOT
TESTSET = ROOT / "eval" / "testset.csv"
RESULTS_DIR = ROOT / "eval" / "results"


def load_testset(path: Path) -> list[dict]:
    if not path.exists():
        print(f"[fail] 测试集不存在：{path}\n       先运行：python scripts/make_testset.py")
        sys.exit(1)
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def run_retrieval_eval(p, rows: list[dict], mode: str, top_k: int) -> tuple[RetrievalMetrics, list[dict]]:
    m = RetrievalMetrics()
    details: list[dict] = []
    per_type: dict[str, dict] = defaultdict(lambda: {"n": 0, "hit": 0, "full": 0, "mrr": 0.0})

    for row in rows:
        expected = parse_expected_articles(row["expected_articles"])
        if row["type"] == "refuse":
            # 拒答题在检索层只记录召回了什么，不计分
            chunks, _ = p.retriever.retrieve(row["question"], mode=mode, top_k=top_k, top_n=top_k)
            details.append({
                "qid": row["qid"], "type": row["type"], "question": row["question"],
                "expected_articles": expected, "retrieved_articles": [],
                "hit": None, "rr": None, "full": None,
                "retrieved": [c.chunk.citation_label() for c in chunks],
            })
            continue

        doc_ids = [d.strip() for d in row["expected_doc_ids"].split(";") if d.strip()]
        chunks, debug = p.retriever.retrieve(
            row["question"], mode=mode, top_k=top_k, top_n=top_k,
            doc_filter=set(doc_ids) if doc_ids else None,
        )
        got = [c.chunk.article_no or c.chunk.article_title for c in chunks]
        hit, rr, full = evaluate_retrieval_row(expected, got)

        m.n += 1
        m.hit += int(hit)
        m.full_hit += int(full)
        m.mrr_sum += rr

        t = per_type[row["type"]]
        t["n"] += 1
        t["hit"] += int(hit)
        t["full"] += int(full)
        t["mrr"] += rr

        details.append({
            "qid": row["qid"], "type": row["type"], "question": row["question"],
            "expected_articles": expected, "retrieved_articles": got,
            "hit": hit, "rr": round(rr, 4), "full": full,
            "retrieved": [c.chunk.citation_label() for c in chunks],
        })

    for t, d in per_type.items():
        d["hit_rate"] = round(d["hit"] / d["n"], 4) if d["n"] else 0.0
        d["full_hit_rate"] = round(d["full"] / d["n"], 4) if d["n"] else 0.0
        d["mrr"] = round(d["mrr"] / d["n"], 4) if d["n"] else 0.0
    m.per_type = {k: v for k, v in per_type.items()}
    return m, details


def run_gen_eval(p, rows: list[dict], mode: str, judge: bool) -> tuple[GenMetrics, list[dict]]:
    g = GenMetrics()
    details: list[dict] = []

    for row in rows:
        ans = p.ask(row["question"], mode=mode, use_cache=True)
        is_refuse_q = row["type"] == "refuse"
        if is_refuse_q:
            g.refused_total += 1

        if judge:
            verdict = judge_with_llm(p.llm, row["question"], row["expected_answer"], ans.answer)
            correct = bool(verdict.get("correct"))
            hallu = bool(verdict.get("hallucination"))
        else:
            # 无裁判时用启发式：拒答题看是否说了"无法确定"，其他题看关键词重合
            if is_refuse_q:
                correct = ("无法确定" in ans.answer) or ("没有" in ans.answer and "条款" in ans.answer)
                hallu = ans.answerable and not correct
            else:
                key = [w for w in row["expected_answer"] if w.isdigit()]
                correct = bool(key) and any(k in ans.answer for k in set(key))
                hallu = False
            verdict = {"reason": "启发式（未启用 LLM 裁判）"}

        g.n += 1
        g.correct += int(correct)
        if is_refuse_q and correct:
            g.refused_correctly += 1
        if hallu:
            g.hallucinated += 1
        if ans.citations:
            g.cite_ok += 1

        details.append({
            "qid": row["qid"], "type": row["type"], "question": row["question"],
            "expected_answer": row["expected_answer"], "actual_answer": ans.answer,
            "answerable": ans.answerable,
            "citations": [f"{c.product_name} {c.article_no}".strip() for c in ans.citations],
            "correct": correct, "hallucination": hallu,
            "judge_reason": verdict.get("reason", ""),
            "latency_ms": ans.latency_ms,
        })
    return g, details


def main() -> int:
    ap = argparse.ArgumentParser(description="RAG 评测")
    ap.add_argument("--mode", default="all", choices=["all", "vector", "keyword", "hybrid"])
    ap.add_argument("--top-k", type=int, default=20)
    ap.add_argument("--gen", action="store_true", help="同时跑生成层评估")
    ap.add_argument("--judge", action="store_true", help="用 LLM 当裁判（需要真实 LLM）")
    ap.add_argument("--limit", type=int, default=0, help="只跑前 N 题（调试用）")
    args = ap.parse_args()

    settings = get_settings()
    rows = load_testset(TESTSET)
    if args.limit:
        rows = rows[: args.limit]

    p = Pipeline(settings=settings)
    if not p.index_ready:
        print("[fail] 索引未就绪。先运行：python scripts/build_index.py")
        return 1

    # ---------- 明确警告：什么样的配置下数字不可用 ----------
    unreliable: list[str] = []
    if settings.embedding.provider == "hash":
        unreliable.append("embedding=hash（字形重叠，非语义向量）")
    if settings.llm.provider == "mock" and args.gen:
        unreliable.append("llm=mock（未接真实模型）")
    if unreliable:
        print("!" * 72)
        print("⚠️  当前配置下的评测数字**不能写进简历**，只证明链路是通的：")
        for u in unreliable:
            print(f"     - {u}")
        print("   要拿到可用的数字：设置真实 embedding（PR_EMB_PROVIDER=api/local）")
        print("                    和真实 LLM（PR_LLM_PROVIDER=api + PR_LLM_API_KEY）后 --rebuild")
        print("!" * 72)
        print()

    modes = ["vector", "keyword", "hybrid"] if args.mode == "all" else [args.mode]
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")

    print(f"测试集：{len(rows)} 题    索引：{p.index_size} chunks    embedding={p.embedder.signature}")
    print()
    print(f"{'模式':<10}{'HitRate':>10}{'MRR':>10}{'全部命中':>10}")
    print("-" * 42)

    summary = {}
    for mode in modes:
        m, details = run_retrieval_eval(p, rows, mode, args.top_k)
        print(f"{mode:<10}{m.hit_rate:>10.2%}{m.mrr:>10.4f}{m.full_hit_rate:>10.2%}")
        summary[mode] = m.to_dict()

        out = {
            "timestamp": stamp, "mode": mode, "top_k": args.top_k,
            "embedding_signature": p.embedder.signature, "llm": p.llm.name,
            "index_size": p.index_size, "testset_size": len(rows),
            "reliable": not unreliable,
            "retrieval_metrics": m.to_dict(), "details": details,
        }
        (RESULTS_DIR / f"{stamp}-{mode}.json").write_text(
            json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # ---------- 分类型明细（最能说明问题） ----------
    best = "hybrid" if "hybrid" in summary else modes[0]
    print()
    print(f"【按题型拆分 · {best}】")
    print(f"{'类型':<14}{'题数':>6}{'HitRate':>10}{'全部命中':>10}")
    print("-" * 42)
    for t, d in summary[best].get("per_type", {}).items():
        print(f"{t:<14}{d['n']:>6}{d['hit_rate']:>10.2%}{d['full_hit_rate']:>10.2%}")

    # ---------- 生成层 ----------
    if args.gen:
        print()
        print(f"【生成层 · {best}】{'（LLM 裁判）' if args.judge else '（启发式，未启用裁判）'}")
        g, gdetails = run_gen_eval(p, rows, best, judge=args.judge)
        print(f"  答对率     ：{g.accuracy:.2%}  ({g.correct}/{g.n})")
        print(f"  拒答准确率 ：{g.refuse_accuracy:.2%}  ({g.refused_correctly}/{g.refused_total})")
        print(f"  幻觉题数   ：{g.hallucinated}")
        print(f"  有引用题数 ：{g.cite_ok}/{g.n}")
        lat = [d["latency_ms"] for d in gdetails]
        if lat:
            print(f"  平均延迟   ：{statistics.mean(lat):.0f}ms   P95：{sorted(lat)[int(len(lat)*0.95)-1]}ms")

        (RESULTS_DIR / f"{stamp}-{best}-gen.json").write_text(
            json.dumps(
                {"timestamp": stamp, "metrics": g.to_dict(), "details": gdetails},
                ensure_ascii=False, indent=2,
            ),
            encoding="utf-8",
        )

    # ---------- 失败案例（改进的入口） ----------
    print()
    print("【未命中明细 · 这些就是你下一步要修的地方】")
    shown = 0
    for d in details:
        if d["hit"] is False:
            print(f"  {d['qid']} [{d['type']}] {d['question'][:34]}")
            print(f"      期望：{d['expected_articles']}")
            print(f"      实际召回：{d['retrieved_articles'][:5]}")
            shown += 1
            if shown >= 8:
                break
    if shown == 0:
        print("  （无未命中）")

    print()
    print(f"明细已保存到 {RESULTS_DIR}")
    print("把关键数字整理进 docs/03-迭代日志.md —— 那是面试时的弹药。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
