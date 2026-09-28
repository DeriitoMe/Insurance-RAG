"""FastAPI 服务层。

这一层直接对应 360 JD 的第 3 条：
  "参与产品前后端开发，基于主流框架完成 AI 应用界面交互、接口联调、模块功能开发，
   保障产品功能稳定、响应高效，实现 AI 能力可视化、可落地使用。"

架构：**API 挂在 /api 前缀下，同时托管 Vue 构建产物**。
为什么这样安排：
  - 前端开发时跑 `npm run dev`（5173），Vite 把 /api 代理到 8000 → 避开 CORS
  - 生产环境 FastAPI 直接托管 dist/ → 同源，也不需要 CORS
  **两种情况都不需要开 CORS 中间件**，这是比"到处 allow_origins=['*']"更干净的做法。

里面有两个"看起来简单但容易翻车"的点：
  1. **SSE 流式**：必须 `media_type="text/event-stream"` + `X-Accel-Buffering: no`，
     否则 nginx 会缓冲整个响应，前端的"打字机效果"完全消失。
  2. **同步阻塞调用要放线程池**：embedding / LLM 调用是阻塞 IO，
     直接在 async 函数里调会卡住事件循环，让服务失去并发能力。
     这里用 `run_in_threadpool` 解决。

启动：
    npm --prefix web run build                     # 先构建前端（可选）
    uvicorn policyrag.api:app --app-dir src --port 8000
"""

from __future__ import annotations

import json
import os
import shutil
from ipaddress import ip_address
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import APIRouter, FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import PROJECT_ROOT, get_env_path, get_settings
from .pipeline import Pipeline

settings = get_settings()
WEB_DIST = PROJECT_ROOT / "web" / "dist"
RAW_DIR = PROJECT_ROOT / "data" / "raw"

ALLOWED_UPLOAD_SUFFIXES = {".pdf", ".json", ".txt", ".text"}
MAX_UPLOAD_BYTES = 80 * 1024 * 1024        # 80 MB，够放一份几百页的条款

app = FastAPI(
    title="保险条款 RAG",
    description="条款问答 / 跨条款聚合 / 引用溯源",
    version="0.2.0",
)

_pipeline: Pipeline | None = None


def get_pipeline() -> Pipeline:
    """懒加载单例：避免每次请求都重新加载索引。"""
    global _pipeline
    if _pipeline is None:
        _pipeline = Pipeline(settings=settings)
    return _pipeline


def _require_index() -> Pipeline:
    p = get_pipeline()
    if not p.index_ready:
        raise HTTPException(503, "索引未就绪，先运行 python scripts/build_index.py")
    return p


# --------------------------------------------------------------------------
# 请求 / 响应模型
# --------------------------------------------------------------------------

class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=500, description="用户问题")
    mode: str = Field("hybrid", pattern="^(hybrid|vector|keyword)$")
    top_k: int | None = Field(None, ge=1, le=100, description="召回数量")
    top_n: int | None = Field(None, ge=1, le=20, description="送进模型的数量")
    doc_ids: list[str] | None = Field(None, description="限定产品（多产品对比时用）")
    use_cache: bool = True


class ModelSettingsRequest(BaseModel):
    embedding_provider: str = Field("hash", pattern="^(hash|api|local)$")
    embedding_api_base: str = Field(..., min_length=1, max_length=2048)
    embedding_api_key: str | None = Field(None, max_length=4096)
    embedding_model: str = Field(..., min_length=1, max_length=200)
    clear_embedding_key: bool = False
    llm_provider: str = Field("mock", pattern="^(mock|api)$")
    llm_api_base: str = Field(..., min_length=1, max_length=2048)
    llm_api_key: str | None = Field(None, max_length=4096)
    llm_model: str = Field(..., min_length=1, max_length=200)
    clear_llm_key: bool = False


# --------------------------------------------------------------------------
# API 路由（全部挂在 /api 下，与前端约定一致）
# --------------------------------------------------------------------------

api = APIRouter(prefix="/api")


def _require_local_settings_access(request: Request) -> None:
    """Keep the API-key editor limited to a local app instance."""
    # Reverse proxies commonly forward public traffic with these headers. The
    # settings editor is intentionally unsupported through a public proxy.
    if request.headers.get("x-forwarded-for") or request.headers.get("forwarded"):
        raise HTTPException(403, "模型设置只允许从本机打开")

    client_host = request.client.host if request.client else ""
    try:
        local_client = ip_address(client_host.split("%", 1)[0]).is_loopback
    except ValueError:
        local_client = False

    host = request.headers.get("host", "")
    hostname = urlsplit(f"//{host}").hostname or ""
    try:
        local_host = hostname.lower() == "localhost" or ip_address(hostname).is_loopback
    except ValueError:
        local_host = hostname.lower() == "localhost"

    # Docker's published localhost port reaches the container through its
    # bridge gateway, so a localhost Host header is also accepted. Compose
    # binds that published port to 127.0.0.1 by default.
    if not local_client and not local_host:
        raise HTTPException(403, "模型设置只允许从本机打开")

    origin = request.headers.get("origin")
    if origin:
        origin_host = urlsplit(origin).hostname or ""
        try:
            local_origin = origin_host.lower() == "localhost" or ip_address(origin_host).is_loopback
        except ValueError:
            local_origin = origin_host.lower() == "localhost"
        if not local_origin:
            raise HTTPException(403, "模型设置只允许从本机页面提交")


def _write_project_env(updates: dict[str, str]) -> None:
    """Update selected keys in the ignored project .env, preserving comments."""
    env_path = get_env_path()
    env_path.parent.mkdir(parents=True, exist_ok=True)
    lines = env_path.read_text(encoding="utf-8-sig").splitlines() if env_path.exists() else []
    replaced: set[str] = set()
    output: list[str] = []
    for line in lines:
        key, sep, _ = line.partition("=")
        normalized = key.strip()
        if sep and normalized in updates:
            output.append(f"{normalized}={updates[normalized]}")
            replaced.add(normalized)
        else:
            output.append(line)
    for key, value in updates.items():
        if key not in replaced:
            output.append(f"{key}={value}")

    temp_path = env_path.with_name(".env.settings.tmp")
    try:
        temp_path.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")
        if os.name != "nt":
            temp_path.chmod(0o600)
        os.replace(temp_path, env_path)
        if os.name != "nt":
            env_path.chmod(0o600)
    finally:
        temp_path.unlink(missing_ok=True)


def _validate_api_base(name: str, value: str) -> None:
    parsed = urlsplit(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise HTTPException(422, f"{name} 必须是 http:// 或 https:// 开头的完整地址")
    if "\n" in value or "\r" in value:
        raise HTTPException(422, f"{name} 格式无效")


@api.get("/settings")
def read_model_settings(request: Request) -> dict:
    """Return model settings without ever returning API-key values."""
    _require_local_settings_access(request)
    return {
        "embedding_provider": settings.embedding.provider,
        "embedding_api_base": settings.embedding.api_base,
        "embedding_api_key_configured": bool(settings.embedding.api_key),
        "embedding_model": settings.embedding.model_name,
        "llm_provider": settings.llm.provider,
        "llm_api_base": settings.llm.api_base,
        "llm_api_key_configured": bool(settings.llm.api_key),
        "llm_model": settings.llm.model_name,
    }


@api.post("/settings")
def update_model_settings(request: Request, req: ModelSettingsRequest) -> dict:
    """Save API settings locally and apply them to the running process."""
    global settings, _pipeline
    _require_local_settings_access(request)
    _validate_api_base("Embedding API 地址", req.embedding_api_base)
    _validate_api_base("LLM API 地址", req.llm_api_base)

    text_values = {
        "PR_EMB_MODEL": req.embedding_model.strip(),
        "PR_LLM_MODEL": req.llm_model.strip(),
    }
    if not all(text_values.values()):
        raise HTTPException(422, "模型名称不能为空")
    for value in (*text_values.values(), req.embedding_api_key or "", req.llm_api_key or ""):
        if "\n" in value or "\r" in value:
            raise HTTPException(422, "配置项不能包含换行符")

    previous_embedding = (
        settings.embedding.provider,
        settings.embedding.api_base,
        settings.embedding.model_name,
    )
    updates = {
        "PR_EMB_PROVIDER": req.embedding_provider,
        "PR_EMB_API_BASE": req.embedding_api_base.strip(),
        "PR_EMB_MODEL": text_values["PR_EMB_MODEL"],
        "PR_LLM_PROVIDER": req.llm_provider,
        "PR_LLM_API_BASE": req.llm_api_base.strip(),
        "PR_LLM_MODEL": text_values["PR_LLM_MODEL"],
    }
    if req.clear_embedding_key:
        updates["PR_EMB_API_KEY"] = ""
    elif (req.embedding_api_key or "").strip():
        updates["PR_EMB_API_KEY"] = req.embedding_api_key.strip()
    if req.clear_llm_key:
        updates["PR_LLM_API_KEY"] = ""
    elif (req.llm_api_key or "").strip():
        updates["PR_LLM_API_KEY"] = req.llm_api_key.strip()

    _write_project_env(updates)
    # Explicit UI values take effect immediately and override process variables.
    for key, value in updates.items():
        os.environ[key] = value
    settings = get_settings(reload=True)
    _pipeline = None
    from . import pipeline as _pl

    _pl._ANSWER_CACHE.clear()

    current_embedding = (
        settings.embedding.provider,
        settings.embedding.api_base,
        settings.embedding.model_name,
    )
    return {
        "ok": True,
        "embedding_reindex_required": current_embedding != previous_embedding,
        "embedding_api_key_configured": bool(settings.embedding.api_key),
        "llm_api_key_configured": bool(settings.llm.api_key),
    }


@api.get("/health")
def health() -> dict:
    try:
        p = get_pipeline()
        return {
            "status": "ok",
            "index_ready": p.index_ready,
            "index_size": p.index_size,
            "embedding": p.embedder.signature,
            "llm": p.llm.name,
            "mode_default": "hybrid",
            "web_dist": WEB_DIST.exists(),
        }
    except Exception as e:                              # noqa: BLE001
        return {"status": "degraded", "error": f"{type(e).__name__}: {e}"}


@api.get("/products")
def products() -> dict:
    p = _require_index()
    return {"products": p.list_products()}


@api.post("/ask")
async def ask(req: AskRequest) -> dict:
    """非流式问答。返回完整 JSON，便于评测脚本和第三方批量调用。"""
    p = _require_index()
    try:
        # 注意：阻塞调用放线程池，否则会卡住事件循环
        answer = await run_in_threadpool(
            p.ask,
            req.question,
            req.mode,
            req.top_k,
            req.top_n,
            req.doc_ids,
            req.use_cache,
        )
    except Exception as e:                              # noqa: BLE001
        raise HTTPException(500, f"{type(e).__name__}: {e}") from e
    return answer.to_dict()


@api.get("/ask/stream")
async def ask_stream(
    question: str = Query(..., min_length=1, max_length=500),
    mode: str = Query("hybrid", pattern="^(hybrid|vector|keyword)$"),
    top_n: int | None = Query(None, ge=1, le=20),
    doc_ids: str | None = Query(None, description="逗号分隔的产品 doc_id"),
) -> StreamingResponse:
    """SSE 流式问答。

    事件序列：
        {"type":"sources", "sources":[...]}   检索到的条款（前端立刻渲染来源）
        {"type":"delta",   "text":"..."}      token 分片（多次）
        {"type":"final",   "answer":...}      解析好的完整结果
        {"type":"error",   "message":"..."}   出错时
    """
    p = _require_index()
    doc_filter = [d.strip() for d in doc_ids.split(",") if d.strip()] if doc_ids else None

    def event_gen():
        try:
            for evt in p.stream(question, mode=mode, top_n=top_n, doc_ids=doc_filter):
                # SSE 格式：data: <json>\n\n
                yield f"data: {json.dumps(evt, ensure_ascii=False)}\n\n"
        except Exception as e:                          # noqa: BLE001
            err = {"type": "error", "message": f"{type(e).__name__}: {e}"}
            yield f"data: {json.dumps(err, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # 关键：没有这个头，nginx 会缓冲整个响应，流式效果消失
            "X-Accel-Buffering": "no",
        },
    )


app.include_router(api)


# --------------------------------------------------------------------------
# 语料管理：网页上传 + 重建索引
#
# 为什么要有这两个接口：
# 原来看条款必须放进 data/raw/ 再敲命令行。对不熟命令行的人这是最大的一道坎。
# 有这两个接口后，在网页上直接拖 PDF 进来就行。
#
# 为什么分成两步（上传 / 重建）而不是上传即入库：
# 重建索引可能要几十秒（要跑 embedding）。上传即重建会让用户面对一个
# 长时间无响应的请求。分开之后前端可以先显示"已上传，点重建"。
# --------------------------------------------------------------------------

def _rebuild_index() -> dict:
    """重建索引并重载 pipeline。阻塞操作，调用方负责放线程池。"""
    global _pipeline

    from .embedding.base import build_embedder
    from .index.bm25 import BM25Index
    from .index.vector_store import NumpyVectorStore
    from .ingest.chunker import chunk_document
    from .ingest.loaders import load_documents

    docs, warnings = load_documents(RAW_DIR)
    if not docs:
        return {"ok": False, "error": "没有加载到任何语料", "warnings": warnings}

    chunks = []
    per_doc = []
    for d in docs:
        cs = chunk_document(d, settings.chunk)
        chunks.extend(cs)
        per_doc.append(
            {"doc_id": d.doc_id, "product_name": d.display_name, "chunks": len(cs)}
        )

    embedder = build_embedder(settings.embedding)
    matrix = embedder.embed_documents([c.text for c in chunks])

    store = NumpyVectorStore()
    store.build(chunks, matrix, signature=embedder.signature)
    store.save(settings.index_dir)

    bm25 = BM25Index()
    bm25.build(chunks)
    bm25.save(settings.index_dir)

    # 索引换了，pipeline 必须重建（否则还拿着旧的内存索引）
    _pipeline = Pipeline(settings=settings)

    # 答案缓存也失效了
    from . import pipeline as _pl

    _pl._ANSWER_CACHE.clear()

    return {
        "ok": True,
        "documents": len(docs),
        "chunks": len(chunks),
        "per_doc": per_doc,
        "embedding": embedder.signature,
        "warnings": warnings,
    }


@api.get("/documents")
def list_documents() -> dict:
    """列出 data/raw 里的文件，标注哪些能被识别为语料。"""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    items = []
    for p in sorted(RAW_DIR.iterdir()):
        if not p.is_file() or p.name.startswith("."):
            continue
        suffix = p.suffix.lower()
        items.append(
            {
                "name": p.name,
                "size_kb": round(p.stat().st_size / 1024, 1),
                "loadable": suffix in ALLOWED_UPLOAD_SUFFIXES,
                "suffix": suffix,
            }
        )
    return {"dir": str(RAW_DIR), "files": items, "allowed": sorted(ALLOWED_UPLOAD_SUFFIXES)}


@api.post("/upload")
async def upload_document(file: UploadFile = File(...)) -> dict:
    """上传条款文件到 data/raw/。**不会自动重建索引** —— 需要再调 /reindex。

    上传后顺手做一次识别预检，让用户立刻知道文件能不能用，
    而不是等重建完了才发现"识别出 0 条条款"。
    """
    filename = Path(file.filename or "unnamed").name        # 去掉路径，防目录穿越
    suffix = Path(filename).suffix.lower()

    if suffix not in ALLOWED_UPLOAD_SUFFIXES:
        raise HTTPException(
            400,
            f"不支持的文件类型 {suffix!r}。"
            f"只接受：{', '.join(sorted(ALLOWED_UPLOAD_SUFFIXES))}",
        )

    raw = await file.read()
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            413, f"文件太大（{len(raw) / 1024 / 1024:.1f} MB），上限 {MAX_UPLOAD_BYTES // 1024 // 1024} MB"
        )
    if not raw:
        raise HTTPException(400, "文件是空的")

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    dest = RAW_DIR / filename
    dest.write_bytes(raw)

    # 预检：能不能识别出条款
    preview: dict = {"recognized": None, "note": ""}
    try:
        from .ingest.chunker import sections_from_plain_text
        from .ingest.loaders import (
            load_json_document,
            load_pdf_document,
            load_text_document,
        )

        if suffix == ".json":
            doc = load_json_document(dest)
        elif suffix == ".pdf":
            doc = load_pdf_document(dest, doc_id=dest.stem)
        else:
            doc = load_text_document(dest, doc_id=dest.stem)

        from .ingest.chunker import chunk_document

        n = len(chunk_document(doc, settings.chunk))
        preview["recognized"] = n
        preview["doc_id"] = doc.doc_id
        preview["product_name"] = doc.display_name
        if n == 0:
            preview["note"] = "没识别出可检索条款，检查标题格式"
        else:
            preview["note"] = f"可切分成 {n} 个块"
    except Exception as e:                                  # noqa: BLE001
        preview["note"] = f"预检失败：{type(e).__name__}: {e}"

    return {
        "ok": True,
        "saved_as": filename,
        "size_kb": round(len(raw) / 1024, 1),
        "preview": preview,
        "next": "调用 POST /api/reindex 让新语料生效",
    }


@api.post("/reindex")
async def reindex() -> dict:
    """重建索引，让 data/raw 里的新语料生效。"""
    try:
        result = await run_in_threadpool(_rebuild_index)
    except Exception as e:                                  # noqa: BLE001
        raise HTTPException(500, f"重建失败：{type(e).__name__}: {e}") from e

    if not result.get("ok"):
        raise HTTPException(400, result.get("error", "重建失败"))
    return result


@api.delete("/documents/{name}")
def delete_document(name: str) -> dict:
    """删除 data/raw 里的一个语料文件。**不会自动重建索引。**"""
    safe = Path(name).name
    target = RAW_DIR / safe
    if not target.exists() or not target.is_file():
        raise HTTPException(404, f"文件不存在：{safe}")
    target.unlink()
    return {"ok": True, "deleted": safe, "next": "调用 POST /api/reindex 生效"}


@app.get("/health", include_in_schema=False)
def health_legacy() -> dict:
    return health()


@app.post("/ask", include_in_schema=False)
async def ask_legacy(req: AskRequest) -> dict:
    return await ask(req)


# --------------------------------------------------------------------------
# 托管前端构建产物
# --------------------------------------------------------------------------

if WEB_DIST.exists():
    # 静态资源（js/css/字体）直接由 StaticFiles 处理，带缓存头
    app.mount("/assets", StaticFiles(directory=str(WEB_DIST / "assets")), name="assets")


@app.get("/", include_in_schema=False)
def index_page():
    index = WEB_DIST / "index.html"
    if index.exists():
        return FileResponse(str(index))
    raise HTTPException(
        404,
        "前端未构建。执行：npm --prefix web install && npm --prefix web run build",
    )


@app.get("/{full_path:path}", include_in_schema=False)
def spa_fallback(full_path: str):
    """SPA 兜底路由。

    前端用的是 history 模式，/app 是**前端路由**，磁盘上没有对应文件。
    如果只托管静态文件，用户直接访问或刷新 /app 会 404 —— 分享出去的链接全是坏的。

    所以：所有没被前面路由匹配到的 GET 请求，都返回 index.html，
    交给前端路由去解析。

    注意顺序：这个路由必须**定义在所有 API 路由和静态挂载之后**，
    否则它会抢先匹配 /api/* 把接口全部吃掉。
    FastAPI 按注册顺序匹配，所以这里的位置是有意的。

    另外要排除 /api 前缀：万一将来有没定义的 API 路径，
    应该返回 404 而不是悄悄返回一个 HTML 页面（那会让调试非常困惑）。
    """
    if full_path.startswith("api/"):
        raise HTTPException(404, "接口不存在")

    index = WEB_DIST / "index.html"
    if index.exists():
        return FileResponse(str(index))

    # 没构建前端时给一个明确的提示，而不是空白 404
    raise HTTPException(
        404,
        "前端未构建。执行：npm --prefix web install && npm --prefix web run build",
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
