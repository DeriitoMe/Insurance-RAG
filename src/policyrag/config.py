"""配置：全部可用环境变量覆盖，方便在服务器/Docker 里改而不动代码。"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
INDEX_DIR = DATA_DIR / "index"
EVAL_DIR = PROJECT_ROOT / "eval"


def get_env_path() -> Path:
    """Return the ignored local settings file used by this process."""
    configured_path = os.environ.get("PR_ENV_FILE", "").strip()
    return Path(configured_path).expanduser() if configured_path else PROJECT_ROOT / ".env"


def _load_project_env() -> None:
    """Load KEY=VALUE settings without overriding non-empty OS environment values."""
    env_path = get_env_path()
    if not env_path.is_file():
        return
    try:
        lines = env_path.read_text(encoding="utf-8-sig").splitlines()
    except OSError:
        return
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, sep, value = line.partition("=")
        key = key.strip()
        if not sep or not key or not key.replace("_", "").isalnum():
            continue
        if os.environ.get(key, "").strip():
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ[key] = value


_load_project_env()


def _env(key: str, default: str) -> str:
    v = os.environ.get(key, "").strip()
    return v or default


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, "").strip() or default)
    except ValueError:
        return default


def _env_float(key: str, default: float) -> float:
    try:
        return float(os.environ.get(key, "").strip() or default)
    except ValueError:
        return default


def _env_bool(key: str, default: bool) -> bool:
    v = os.environ.get(key, "").strip().lower()
    if not v:
        return default
    return v in {"1", "true", "yes", "on"}


@dataclass
class ChunkConfig:
    """切分参数。改这些值必须重建索引，并且要重跑评测。"""

    max_chars: int = field(default_factory=lambda: _env_int("PR_MAX_CHARS", 800))
    min_chars: int = field(default_factory=lambda: _env_int("PR_MIN_CHARS", 60))
    overlap_chars: int = field(default_factory=lambda: _env_int("PR_OVERLAP_CHARS", 80))
    # 是否把层级路径注入到 text 里（强烈建议 True）
    inject_section_path: bool = field(default_factory=lambda: _env_bool("PR_INJECT_PATH", True))


@dataclass
class EmbeddingConfig:
    """向量化配置。

    provider:
      - "hash"  : 零依赖兜底，**效果很差，仅用于跑通链路**
      - "api"   : OpenAI 兼容接口（DeepSeek/智谱/通义/硅基流动/vLLM 都行）
      - "local" : sentence-transformers 本地模型（需 torch）
    """

    provider: str = field(default_factory=lambda: _env("PR_EMB_PROVIDER", "hash"))
    model_name: str = field(default_factory=lambda: _env("PR_EMB_MODEL", "BAAI/bge-large-zh-v1.5"))
    api_base: str = field(default_factory=lambda: _env("PR_EMB_API_BASE", "https://api.siliconflow.cn/v1"))
    api_key: str = field(default_factory=lambda: _env("PR_EMB_API_KEY", ""))
    dim: int = field(default_factory=lambda: _env_int("PR_EMB_DIM", 1024))
    batch_size: int = field(default_factory=lambda: _env_int("PR_EMB_BATCH", 32))
    device: str = field(default_factory=lambda: _env("PR_EMB_DEVICE", "cpu"))


@dataclass
class LLMConfig:
    """生成模型配置。provider="mock" 时返回固定文本，用于离线跑通链路。"""

    provider: str = field(default_factory=lambda: _env("PR_LLM_PROVIDER", "mock"))   # mock | api
    model_name: str = field(default_factory=lambda: _env("PR_LLM_MODEL", "deepseek-chat"))
    api_base: str = field(default_factory=lambda: _env("PR_LLM_API_BASE", "https://api.deepseek.com/v1"))
    api_key: str = field(default_factory=lambda: _env("PR_LLM_API_KEY", ""))
    temperature: float = field(default_factory=lambda: _env_float("PR_LLM_TEMP", 0.0))
    max_tokens: int = field(default_factory=lambda: _env_int("PR_LLM_MAX_TOKENS", 1024))
    timeout_s: int = field(default_factory=lambda: _env_int("PR_LLM_TIMEOUT", 60))


@dataclass
class RetrievalConfig:
    """检索参数。top_k 管召回广度，top_n 管送进模型的精度。"""

    top_k: int = field(default_factory=lambda: _env_int("PR_TOP_K", 20))
    top_n: int = field(default_factory=lambda: _env_int("PR_TOP_N", 5))
    rrf_k: int = field(default_factory=lambda: _env_int("PR_RRF_K", 60))
    use_bm25: bool = field(default_factory=lambda: _env_bool("PR_USE_BM25", True))
    use_rerank: bool = field(default_factory=lambda: _env_bool("PR_USE_RERANK", False))
    rerank_model: str = field(default_factory=lambda: _env("PR_RERANK_MODEL", "BAAI/bge-reranker-base"))


@dataclass
class Settings:
    chunk: ChunkConfig = field(default_factory=ChunkConfig)
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    retrieval: RetrievalConfig = field(default_factory=RetrievalConfig)

    raw_dir: Path = RAW_DIR
    processed_dir: Path = PROCESSED_DIR
    index_dir: Path = INDEX_DIR

    def ensure_dirs(self) -> None:
        for p in (self.raw_dir, self.processed_dir, self.index_dir, EVAL_DIR):
            p.mkdir(parents=True, exist_ok=True)


_settings: Settings | None = None


def get_settings(reload: bool = False) -> Settings:
    global _settings
    if _settings is None or reload:
        _settings = Settings()
        _settings.ensure_dirs()
    return _settings
