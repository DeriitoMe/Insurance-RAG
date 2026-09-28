"""API 端到端测试（用 Python 客户端，避开 PowerShell 的编码坑）。

用法：先起服务，再运行
    python scripts/test_api.py --base http://127.0.0.1:8811
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request

import _bootstrap  # noqa: F401


def _post(url: str, payload: dict) -> dict:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json; charset=utf-8"}
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _get(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    args = ap.parse_args()
    base = args.base.rstrip("/")
    api = f"{base}/api"
    failed = 0

    # ---------------- /api/health ----------------
    print("=" * 66)
    try:
        h = _get(f"{api}/health")
        print(f"[ok]   /api/health  status={h['status']} index_ready={h['index_ready']} "
              f"size={h['index_size']} emb={h['embedding']} llm={h['llm']}")
        print(f"       web_dist 已构建={h.get('web_dist')}")
    except Exception as e:                                  # noqa: BLE001
        print(f"[FAIL] /api/health  {e}")
        return 1

    # ---------------- 前端托管 ----------------
    try:
        with urllib.request.urlopen(f"{base}/", timeout=20) as resp:
            html = resp.read().decode("utf-8")
        ok = 'id="app"' in html and "/assets/" in html
        print(f"[{'ok' if ok else 'FAIL'}]   GET /  返回 {len(html)} 字节的前端页面"
              f"{'（Vue 构建产物）' if ok else '（不是构建产物）'}")
        if not ok:
            print("       提示：cd web && npm run build")
            failed += 1
    except Exception as e:                                  # noqa: BLE001
        print(f"[FAIL] GET /  {e}")
        failed += 1

    # ---------------- /api/products（中文编码检查） ----------------
    try:
        p = _get(f"{api}/products")
        names = [x["product_name"] for x in p["products"]]
        print(f"[ok]   /api/products  {names}")
        if any("\u00e5" in n or "\u00e7" in n for n in names):
            print("[FAIL] 产品名出现 UTF-8 被按 Latin-1 解码的痕迹（ç/å 类字符）")
            failed += 1
        if not any("安心保" in n for n in names):
            print("[FAIL] 产品名中文丢失")
            failed += 1
    except Exception as e:                                  # noqa: BLE001
        print(f"[FAIL] /api/products  {e}")
        failed += 1

    # ---------------- /api/ask（中文请求体检查） ----------------
    try:
        r = _post(f"{api}/ask", {"question": "安心保的等待期是多少天？", "mode": "hybrid"})
        print(f"[ok]   POST /api/ask  可答={r['answerable']} 引用={len(r['citations'])} 条")
        print(f"       回显问题：{r['question']}")
        if "?" in r["question"] or not r["question"].startswith("安心保"):
            print("[FAIL] 请求体中文未正确解码")
            failed += 1
        if r["citations"]:
            c = r["citations"][0]
            print(f"       首个引用：{c['product_name']} / {c['article_no']}")
            if not c["product_name"]:
                print("[FAIL] 引用缺少 product_name")
                failed += 1
        print(f"       召回：{r['debug'].get('recall_count')} 个块，"
              f"检索 {r['debug'].get('recall_ms')}ms")
    except Exception as e:                                  # noqa: BLE001
        print(f"[FAIL] POST /api/ask  {e}")
        failed += 1

    # ---------------- /api/ask/stream（SSE 流式） ----------------
    print("-" * 66)
    print("SSE 流式检查（这是 JD 里『接口联调』的核心）：")
    try:
        # 注意：这里不再写 `import urllib.parse`。
        # 函数内出现任何 `import urllib.xxx` 都会让 urllib 整个变成**局部名**，
        # 于是函数前面用 urllib.request 的地方会报 UnboundLocalError。
        # 模块顶部已经 `import urllib.request`，它会连带把 urllib.parse 也导入。
        q = urllib.parse.quote("甲状腺结节能赔吗")
        url = f"{api}/ask/stream?question={q}"
        types: list[str] = []
        deltas: list[str] = []
        final_seen = False
        with urllib.request.urlopen(url, timeout=60) as resp:
            ctype = resp.headers.get("Content-Type", "")
            buffering = resp.headers.get("X-Accel-Buffering", "")
            print(f"       Content-Type={ctype!r}  X-Accel-Buffering={buffering!r}")
            if "text/event-stream" not in ctype:
                print("[FAIL] Content-Type 不是 text/event-stream")
                failed += 1
            if buffering != "no":
                print("[warn] 缺少 X-Accel-Buffering: no —— 上 nginx 后流式会被缓冲掉")

            buf = ""
            for raw in resp:
                buf += raw.decode("utf-8")
                while "\n\n" in buf:
                    evt, buf = buf.split("\n\n", 1)
                    line = next((l for l in evt.split("\n") if l.startswith("data:")), None)
                    if not line:
                        continue
                    payload = line[5:].strip()
                    if payload == "[DONE]":
                        continue
                    msg = json.loads(payload)
                    types.append(msg["type"])
                    if msg["type"] == "delta":
                        deltas.append(msg["text"])
                    elif msg["type"] == "sources":
                        print(f"       sources: {[s['label'] for s in msg['sources']][:3]}")
                    elif msg["type"] == "final":
                        final_seen = True
                        print(f"       final: answerable={msg['answerable']} "
                              f"引用={len(msg['citations'])} 条")

        print(f"       delta 分片数：{len(deltas)}")
        if "sources" not in types:
            print("[FAIL] 没有收到 sources 事件")
            failed += 1
        if "delta" not in types:
            print("[FAIL] 没有收到 delta 事件（流式失效）")
            failed += 1
        if not final_seen:
            print("[FAIL] 没有收到 final 事件")
            failed += 1
        if len(deltas) < 3:
            print(f"[warn] delta 只有 {len(deltas)} 片，流式粒度偏粗")
    except Exception as e:                                  # noqa: BLE001
        print(f"[FAIL] /api/ask/stream  {e}")
        failed += 1

    print("=" * 66)
    print("全部通过 ✓" if failed == 0 else f"{failed} 项失败 ✗")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
