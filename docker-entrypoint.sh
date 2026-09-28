#!/bin/sh
# ===================================================================
#  容器入口：先确保索引存在，再启动服务
#
#  为什么不在构建镜像时就建索引：
#    构建时如果用了 API embedding，会把密钥烤进镜像层；
#    而且用户挂载自己的语料后，构建时的索引就过期了。
#    所以在容器启动时判断，没有索引才建。
# ===================================================================
set -e

echo "======================================================"
echo "  保险条款 RAG"
echo "======================================================"

# 语料目录为空 → 生成示例数据，保证容器起来就能用
if [ -z "$(ls -A /app/data/raw 2>/dev/null | grep -v README || true)" ]; then
  echo "[init] data/raw 是空的，生成示例语料..."
  python /app/scripts/make_sample_data.py || true
fi

if [ ! -f /app/eval/testset.csv ]; then
  echo "[init] 生成评测题..."
  python /app/scripts/make_testset.py || true
fi

# 索引不存在 → 构建
if [ ! -f /app/data/index/meta.json ]; then
  echo "[init] 首次启动，构建索引..."
  python /app/scripts/build_index.py --rebuild || {
    echo "[warn] 索引构建失败，服务仍会启动，但问答会返回 503"
  }
fi

echo "[init] embedding = ${PR_EMB_PROVIDER:-hash}"
echo "[init] llm       = ${PR_LLM_PROVIDER:-mock}"
echo "------------------------------------------------------"
echo "  打开 http://localhost:8000"
echo "------------------------------------------------------"

exec "$@"
