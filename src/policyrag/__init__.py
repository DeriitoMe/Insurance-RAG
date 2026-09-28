"""policyrag —— 保险条款 RAG。

模块划分：
  schema      数据结构契约
  config      配置（全部可用环境变量覆盖）
  ingest      语料加载 + 层次感知切分
  embedding   向量化（hash / api / local 可插拔）
  index       向量索引 + BM25 索引
  retrieval   混合检索（RRF 融合）+ Rerank
  generation  提示词 + LLM 调用 + 结构化输出校验
  pipeline    编排（检索 → 生成）
  api         FastAPI 服务（含 SSE 流式）
"""

__version__ = "0.1.0"

__all__ = ["__version__"]
