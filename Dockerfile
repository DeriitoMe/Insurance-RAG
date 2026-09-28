# ===================================================================
#  保险条款 RAG —— 多阶段构建
#
#  为什么用多阶段：
#    Node 镜像有 1GB+，但只在构建前端时需要。
#    用多阶段可以把 Node 那一层完全丢掉，最终镜像只留 Python + 构建产物。
#
#  基础镜像用 3.12 而不是 3.14：
#    3.14 太新，sentence-transformers / chromadb 等还没有轮子。
#    本项目的默认实现零重依赖，但用户想换本地模型时需要这些库。
# ===================================================================

# ---------- 阶段 1：构建前端 ----------
FROM node:22-slim AS web-builder

WORKDIR /web

# 先只复制依赖清单，利用 Docker 层缓存：
# 只要 package.json 没变，改前端代码不会重装依赖
COPY web/package.json web/.npmrc ./
RUN npm ci --no-audit --no-fund

COPY web/ ./
RUN npm run build


# ---------- 阶段 2：运行环境 ----------
FROM python:3.12-slim AS runtime

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/src

# 系统依赖：pypdf 处理部分 PDF 需要
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY scripts/ ./scripts/
COPY eval/ ./eval/
COPY web/README.md ./web/README.md
COPY web/index.html ./web/index.html
COPY web/vite.config.js ./web/vite.config.js
COPY web/package.json ./web/package.json

# 从构建阶段拿前端产物
COPY --from=web-builder /web/dist ./web/dist

# 语料与索引放在卷里，方便挂载自己的条款
VOLUME ["/app/data"]

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8000/api/health || exit 1

# 入口脚本：没有索引就先建，再启动服务
COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["uvicorn", "policyrag.api:app", "--host", "0.0.0.0", "--port", "8000"]
