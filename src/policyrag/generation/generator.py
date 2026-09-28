"""生成层：提示词 + LLM 调用 + 结构化输出校验。

这一层要防住的四件事（面试可以直接讲）：

1. **幻觉** → 提示词硬约束 + 强制引用 + 检索片段没有就说不知道
2. **格式不稳** → JSON schema + Pydantic 强校验 + 失败重试 + 降级
3. **长上下文浪费** → 只送 top_n 个块，且带来源标签
4. **无法调试** → 每次问答都记录用了哪些 chunk

provider：
  mock : 不发网络请求，返回固定结构。**离线跑通链路 + 写单元测试用**
  api  : OpenAI 兼容 /chat/completions（DeepSeek / 智谱 / 通义 / vLLM 都能用）
"""

from __future__ import annotations

import json
import re
import time
from abc import ABC, abstractmethod
from collections.abc import Iterator

from ..config import LLMConfig
from ..schema import Answer, Citation, RetrievedChunk

# --------------------------------------------------------------------------
# 系统提示词：四条硬约束，逐条对应一个真实的失败模式
# --------------------------------------------------------------------------

SYSTEM_PROMPT = """你是一个严谨的保险条款解读助手。你的回答将被用于核保与理赔场景，必须做到可溯源。

【硬性规则】
1. 只依据【条款片段】中提供的内容回答。不得使用你自己的保险知识，不得推测，不得补充条款中没有的内容。
2. 每个结论后面必须标注来源，格式为：【产品名 第X条】。没有标注来源的结论视为无效回答。
3. 如果【条款片段】中没有足够信息回答问题，必须回答"根据现有条款无法确定"，并在 answer 中说明缺少哪类信息（例如：缺少费率表、缺少投保须知）。
4. 如果问题涉及"是否赔付""能否理赔"这类判断，必须综合考虑保险责任、责任免除、等待期、既往症定义等多个条款，逐一列出依据，不能只引用单独一条。

【输出格式】
必须输出严格的 JSON，不要输出任何 JSON 之外的文字：
{
  "answer": "你的回答，包含【产品名 第X条】形式的引用标注",
  "citations": [{"product_name": "产品名", "article_no": "第X条", "quote": "被引用的原文片段，不超过50字"}],
  "answerable": true,
  "used_articles": ["第X条", "第Y条"]
}
answerable 为 false 时表示条款中没有足够信息，此时 citations 可以为空数组。"""

USER_TEMPLATE = """【条款片段】
{context}

【问题】
{question}

请严格按 JSON 格式输出。"""


class LLMError(RuntimeError):
    pass


# --------------------------------------------------------------------------
# Provider
# --------------------------------------------------------------------------

class BaseLLM(ABC):
    @abstractmethod
    def complete(self, system: str, user: str) -> str:
        """返回模型原始文本输出。"""

    def stream(self, system: str, user: str) -> Iterator[str]:
        """默认实现：不支持流式就一次性吐出。子类应覆盖。"""
        yield self.complete(system, user)

    @property
    def name(self) -> str:
        return type(self).__name__


class MockLLM(BaseLLM):
    """离线占位实现。

    ⚠️ 它不是"能用的模型"，只保证链路可跑、可测试。
    评测数据必须用真实模型跑。
    """

    def __init__(self) -> None:
        self.model = "mock"

    def complete(self, system: str, user: str) -> str:
        m = re.search(r"【条款片段】\n(.*?)\n\n【问题】", user, re.S)
        context = m.group(1) if m else ""
        q = re.search(r"【问题】\n(.*?)\n\n请严格", user, re.S)
        question = q.group(1).strip() if q else ""

        first_label = ""
        mm = re.search(r"\[来源: (.+?)\]", context)
        if mm:
            first_label = mm.group(1)

        has_ctx = bool(context.strip())
        if not has_ctx:
            payload = {
                "answer": "根据现有条款无法确定。检索未获得任何条款片段。",
                "citations": [],
                "answerable": False,
                "used_articles": [],
            }
        else:
            payload = {
                "answer": (
                    f"[MOCK 模式回答] 针对问题「{question}」，检索到 {context.count('[来源:')} 个条款片段，"
                    f"最高相关来源为【{first_label}】。接入真实模型后此处为正式回答。"
                ),
                "citations": (
                    [{"product_name": first_label, "article_no": "", "quote": context.strip()[:50]}]
                    if first_label else []
                ),
                "answerable": True,
                "used_articles": [],
            }
        return json.dumps(payload, ensure_ascii=False)

    def stream(self, system: str, user: str) -> Iterator[str]:
        text = self.complete(system, user)
        for i in range(0, len(text), 8):
            yield text[i:i + 8]


class ApiLLM(BaseLLM):
    """OpenAI 兼容接口。"""

    def __init__(self, cfg: LLMConfig) -> None:
        if not cfg.api_key:
            raise LLMError(
                "PR_LLM_PROVIDER=api 但没有设置 PR_LLM_API_KEY。"
                "离线跑通请用 PR_LLM_PROVIDER=mock。"
            )
        try:
            import requests  # noqa: F401
        except ImportError as e:
            raise LLMError("需要 requests：pip install requests") from e
        self.cfg = cfg

    @property
    def name(self) -> str:
        return self.cfg.model_name

    def _payload(self, system: str, user: str, stream: bool) -> dict:
        return {
            "model": self.cfg.model_name,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": self.cfg.temperature,
            "max_tokens": self.cfg.max_tokens,
            "stream": stream,
            # 让模型走 JSON 模式：从解码层面约束格式，比只靠提示词可靠得多
            "response_format": {"type": "json_object"},
        }

    def complete(self, system: str, user: str) -> str:
        import requests

        url = self.cfg.api_base.rstrip("/") + "/chat/completions"
        resp = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {self.cfg.api_key}",
                "Content-Type": "application/json",
            },
            json=self._payload(system, user, stream=False),
            timeout=self.cfg.timeout_s,
        )
        if resp.status_code != 200:
            raise LLMError(f"LLM 接口返回 {resp.status_code}: {resp.text[:300]}")
        return resp.json()["choices"][0]["message"]["content"]

    def stream(self, system: str, user: str) -> Iterator[str]:
        import requests

        url = self.cfg.api_base.rstrip("/") + "/chat/completions"
        with requests.post(
            url,
            headers={
                "Authorization": f"Bearer {self.cfg.api_key}",
                "Content-Type": "application/json",
            },
            json=self._payload(system, user, stream=True),
            timeout=self.cfg.timeout_s,
            stream=True,
        ) as resp:
            if resp.status_code != 200:
                raise LLMError(f"LLM 流式接口返回 {resp.status_code}: {resp.text[:300]}")
            for raw in resp.iter_lines(decode_unicode=False):
                if not raw:
                    continue
                line = raw.decode("utf-8", errors="replace").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    continue
                delta = chunk.get("choices", [{}])[0].get("delta", {})
                piece = delta.get("content")
                if piece:
                    yield piece


def build_llm(cfg: LLMConfig | None = None) -> BaseLLM:
    cfg = cfg or LLMConfig()
    if cfg.provider.lower() == "mock":
        return MockLLM()
    if cfg.provider.lower() == "api":
        return ApiLLM(cfg)
    raise LLMError(f"未知的 PR_LLM_PROVIDER={cfg.provider!r}，可选：mock / api")


# --------------------------------------------------------------------------
# 上下文组装
# --------------------------------------------------------------------------

def build_context(chunks: list[RetrievedChunk], max_chars: int = 12000) -> str:
    """把检索结果拼成上下文。

    关键细节：每个片段都带 [来源: xxx] 标签。
    这是模型能产出正确引用的前提 —— 不告诉它"这段话出自哪条"，
    它就只能编一个条款号出来。
    """
    parts: list[str] = []
    used = 0
    for i, rc in enumerate(chunks, 1):
        c = rc.chunk
        label = c.citation_label()
        block = f"--- 片段{i} [来源: {label}] ---\n{c.raw_text}"
        if used + len(block) > max_chars:      # 上下文预算保护
            break
        parts.append(block)
        used += len(block)
    return "\n\n".join(parts)


def build_user_prompt(question: str, chunks: list[RetrievedChunk]) -> str:
    return USER_TEMPLATE.format(context=build_context(chunks), question=question)


# --------------------------------------------------------------------------
# 输出解析：不信任模型的输出
# --------------------------------------------------------------------------

_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.S)


def parse_answer(raw: str, chunks: list[RetrievedChunk]) -> tuple[str, bool, list[Citation], list[str]]:
    """解析模型输出。失败则降级为纯文本，绝不抛异常给用户。

    返回 (answer, answerable, citations, used_articles)
    """
    text = (raw or "").strip()
    # 模型有时会包 ```json ``` 代码块
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.S).strip()

    payload = None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        m = _JSON_BLOCK_RE.search(text)
        if m:
            try:
                payload = json.loads(m.group(0))
            except json.JSONDecodeError:
                payload = None

    if not isinstance(payload, dict):
        # 降级：当纯文本用，但仍然把检索到的来源附上
        return text or "（模型未返回内容）", bool(text), [
            Citation.from_chunk(rc.chunk) for rc in chunks[:3]
        ], []

    answer = str(payload.get("answer", "")).strip()
    answerable = bool(payload.get("answerable", bool(answer)))

    citations: list[Citation] = []
    chunk_by_label = {c.chunk.citation_label(): c.chunk for c in chunks}
    for item in payload.get("citations") or []:
        if not isinstance(item, dict):
            continue
        product = str(item.get("product_name", "")).strip()
        article = str(item.get("article_no", "")).strip()
        label = f"{product} {article}".strip() or product
        src = chunk_by_label.get(label)
        citations.append(
            Citation(
                doc_id=src.doc_id if src else "",
                product_name=product or (src.product_name if src else ""),
                article_no=article or (src.article_no if src else ""),
                article_title=src.article_title if src else "",
                chunk_id=src.chunk_id if src else "",
                quote=str(item.get("quote", "")).strip(),
            )
        )

    if not citations:
        citations = [Citation.from_chunk(rc.chunk) for rc in chunks[:3]]

    used = [str(x) for x in (payload.get("used_articles") or [])]
    return answer, answerable, citations, used


# --------------------------------------------------------------------------
# 问答主流程
# --------------------------------------------------------------------------

class Generator:
    def __init__(self, llm: BaseLLM, max_retry: int = 1) -> None:
        self.llm = llm
        self.max_retry = max_retry

    def answer(self, question: str, chunks: list[RetrievedChunk], debug: dict | None = None) -> Answer:
        t0 = time.perf_counter()
        user = build_user_prompt(question, chunks)

        raw = ""
        last_err: Exception | None = None
        for attempt in range(self.max_retry + 1):
            try:
                prompt = user
                if attempt > 0:
                    prompt = (
                        user
                        + f"\n\n【重要】上一次你的输出无法解析为 JSON（{last_err}）。"
                        "这次请只输出 JSON 对象本身，不要有任何解释文字或代码块标记。"
                    )
                raw = self.llm.complete(SYSTEM_PROMPT, prompt)
                ans, answerable, cites, used = parse_answer(raw, chunks)
                if ans:
                    return Answer(
                        question=question,
                        answer=ans,
                        answerable=answerable,
                        citations=cites,
                        used_articles=used,
                        retrieved=chunks,
                        latency_ms=int((time.perf_counter() - t0) * 1000),
                        debug={**(debug or {}), "llm": self.llm.name, "retries": attempt},
                    )
                last_err = ValueError("空回答")
            except Exception as e:                      # noqa: BLE001
                last_err = e

        # 全部重试失败 → 降级，但要让用户知道发生了什么
        return Answer(
            question=question,
            answer=f"抱歉，生成回答时出现问题，请稍后重试。（{type(last_err).__name__}）",
            answerable=False,
            citations=[Citation.from_chunk(rc.chunk) for rc in chunks[:3]],
            retrieved=chunks,
            latency_ms=int((time.perf_counter() - t0) * 1000),
            debug={**(debug or {}), "llm": self.llm.name, "error": str(last_err)},
        )
