"""评测指标：检索层与生成层分开算。

为什么要分开（面试必答）：
  答错了到底是"没检索到"还是"检索到了但模型胡说"？分不开就无法定位问题。
  检索层可以**全自动**评估（测试集标注了答案在第几条），
  生成层需要 LLM 评审或人工抽查。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RetrievalMetrics:
    """检索层指标。"""

    n: int = 0
    hit: int = 0                 # top_k 内命中了任一 expected_article 的题数
    mrr_sum: float = 0.0
    full_hit: int = 0            # **所有** expected_articles 都被召回（多跳题关键指标）
    per_type: dict[str, dict] = field(default_factory=dict)

    @property
    def hit_rate(self) -> float:
        return self.hit / self.n if self.n else 0.0

    @property
    def mrr(self) -> float:
        return self.mrr_sum / self.n if self.n else 0.0

    @property
    def full_hit_rate(self) -> float:
        return self.full_hit / self.n if self.n else 0.0

    def to_dict(self) -> dict:
        return {
            "n": self.n,
            "hit_rate": round(self.hit_rate, 4),
            "mrr": round(self.mrr, 4),
            "full_hit_rate": round(self.full_hit_rate, 4),
            "per_type": self.per_type,
        }


@dataclass
class GenMetrics:
    """生成层指标。"""

    n: int = 0
    correct: int = 0
    refused_correctly: int = 0      # C 类题正确拒答数
    refused_total: int = 0          # C 类题总数
    hallucinated: int = 0           # 错误答案中"编造了条款里没有的内容"的题数
    cite_ok: int = 0

    @property
    def accuracy(self) -> float:
        return self.correct / self.n if self.n else 0.0

    @property
    def refuse_accuracy(self) -> float:
        return self.refused_correctly / self.refused_total if self.refused_total else 0.0

    def to_dict(self) -> dict:
        return {
            "n": self.n,
            "accuracy": round(self.accuracy, 4),
            "refuse_accuracy": round(self.refuse_accuracy, 4),
            "hallucinated": self.hallucinated,
            "cite_ok": self.cite_ok,
        }


def parse_expected_articles(s: str) -> list[str]:
    """'第三条;第六条' → ['第三条', '第六条']"""
    if not s or not s.strip():
        return []
    return [x.strip() for x in s.replace("，", ";").replace(",", ";").split(";") if x.strip()]


def evaluate_retrieval_row(
    expected_articles: list[str],
    retrieved_articles: list[str],
) -> tuple[bool, float, bool]:
    """单题检索评估。

    返回 (是否命中任一, reciprocal rank, 是否全部命中)

    匹配规则：expected 是"第三条"，retrieved 是"第三条"→ 命中。
    用**子串包含**而不是相等，是为了兼容 retrieved 里带产品名的情况
    （如"安心保百万医疗险 第三条"）。
    """
    if not expected_articles:
        # 拒答题没有标准条款 —— 不参与检索层评分
        return False, 0.0, False

    rr = 0.0
    found_first = -1
    for exp in expected_articles:
        for rank, got in enumerate(retrieved_articles, 1):
            if exp in got:
                if found_first < 0 or rank < found_first:
                    found_first = rank
                break
    if found_first > 0:
        rr = 1.0 / found_first

    hit_any = found_first > 0
    full = all(
        any(exp in got for got in retrieved_articles) for exp in expected_articles
    )
    return hit_any, rr, full


JUDGE_PROMPT = """你在评估一个保险条款问答系统的回答质量。

【问题】
{question}

【标准答案】
{expected}

【系统回答】
{actual}

请判断系统回答是否正确。判定标准：
- 关键事实与标准答案一致即为正确（措辞不同不算错）
- 系统回答包含标准答案没有的、且条款中不存在的信息 → 不正确（幻觉）
- 标准答案要求"无法确定"时，系统只要给出了肯定性的具体答案 → 不正确

只输出 JSON：{{"correct": true/false, "reason": "一句话理由", "hallucination": true/false}}"""


def judge_with_llm(llm, question: str, expected: str, actual: str) -> dict:
    """用 LLM 当裁判。

    ⚠️ 诚实提醒：LLM 评审本身有噪声（尤其"事实一致性"判断）。
    做法上应该：LLM 评审跑一遍 → 人工抽查 20% → 报告里注明评审方式。
    面试时这么讲比"我用了 LLM-as-judge"更有说服力。
    """
    import json as _json
    import re

    prompt = JUDGE_PROMPT.format(question=question, expected=expected, actual=actual)
    try:
        raw = llm.complete("你是一个严格的评分员，只输出 JSON。", prompt)
    except Exception as e:                                  # noqa: BLE001
        return {"correct": False, "reason": f"评审调用失败：{e}", "hallucination": False}

    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", (raw or "").strip(), flags=re.S)
    try:
        return _json.loads(text)
    except _json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            try:
                return _json.loads(m.group(0))
            except _json.JSONDecodeError:
                pass
    return {"correct": False, "reason": f"评审输出无法解析：{text[:80]}", "hallucination": False}
