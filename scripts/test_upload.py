"""测试网页上传语料的两个接口：/api/upload 和 /api/reindex。

用法：先起服务，再运行
    python scripts/test_upload.py --base http://127.0.0.1:8000
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import sys
import urllib.request
import uuid
from pathlib import Path

import _bootstrap  # noqa: F401

ROOT = _bootstrap.ROOT


def multipart(field: str, filename: str, data: bytes) -> tuple[bytes, str]:
    """手写 multipart/form-data，避免为测试额外装 requests。"""
    boundary = f"----dsh{uuid.uuid4().hex}"
    ctype = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    body = b"".join([
        f"--{boundary}\r\n".encode(),
        f'Content-Disposition: form-data; name="{field}"; filename="{filename}"\r\n'.encode(),
        f"Content-Type: {ctype}\r\n\r\n".encode(),
        data,
        f"\r\n--{boundary}--\r\n".encode(),
    ])
    return body, f"multipart/form-data; boundary={boundary}"


def post_file(base: str, path: str, file_path: Path) -> dict:
    body, ctype = multipart("file", file_path.name, file_path.read_bytes())
    req = urllib.request.Request(
        base + path, data=body, headers={"Content-Type": ctype}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode("utf-8"))


def post_json(base: str, path: str, payload: dict | None = None) -> dict:
    data = json.dumps(payload or {}).encode("utf-8")
    req = urllib.request.Request(
        base + path,
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read().decode("utf-8"))


def get(base: str, path: str) -> dict:
    with urllib.request.urlopen(base + path, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument(
        "--file",
        default=str(ROOT / "data" / "samples" / "测试条款.pdf"),
        help="要上传的文件",
    )
    args = ap.parse_args()

    base = args.base.rstrip("/")
    src = Path(args.file)
    if not src.exists():
        print(f"[fail] 待上传文件不存在：{src}")
        return 1

    failed = 0
    print("=" * 68)

    # ---- 1. 列出当前语料 ----
    try:
        d = get(base, "/api/documents")
        print(f"[ok]   GET  /api/documents  （{len(d['files'])} 个文件）")
        for f in d["files"]:
            mark = "语料" if f["loadable"] else "忽略"
            print(f"       [{mark}] {f['name']}  {f['size_kb']} KB")
    except Exception as e:                                  # noqa: BLE001
        print(f"[FAIL] GET /api/documents  {e}")
        return 1

    # ---- 2. 上传 ----
    print("-" * 68)
    try:
        r = post_file(base, "/api/upload", src)
        r_saved = r["saved_as"]
        pv = r["preview"]
        print(f"[ok]   POST /api/upload  → {r_saved}（{r['size_kb']} KB）")
        print(f"       预检：识别出 {pv.get('recognized')} 个块")
        print(f"       doc_id = {pv.get('doc_id')}")
        print(f"       note   = {pv.get('note')}")
        if pv.get("recognized") == 0:
            print("[FAIL] 预检识别出 0 条，文件格式可能有问题")
            failed += 1
    except Exception as e:                                  # noqa: BLE001
        print(f"[FAIL] POST /api/upload  {e}")
        return 1

    # ---- 3. 重建索引 ----
    print("-" * 68)
    try:
        r = post_json(base, "/api/reindex")
        print(f"[ok]   POST /api/reindex")
        print(f"       文档 {r['documents']} 份，切分 {r['chunks']} 个块")
        for d_ in r["per_doc"]:
            print(f"         - {d_['doc_id']:34s} {d_['product_name']:28s} {d_['chunks']} 块")
    except Exception as e:                                  # noqa: BLE001
        print(f"[FAIL] POST /api/reindex  {e}")
        return 1

    # ---- 4. 确认接口仍正常 ----
    print("-" * 68)
    try:
        h = get(base, "/api/health")
        print(f"[ok]   GET  /api/health  index_size={h['index_size']} emb={h['embedding']}")
    except Exception as e:                                  # noqa: BLE001
        print(f"[FAIL] GET /api/health  {e}")
        failed += 1

    # ---- 5. 清理：删掉刚上传的文件 ----
    print("-" * 68)
    try:
        name = r_saved
        req = urllib.request.Request(
            f"{base}/api/documents/{urllib.parse.quote(name)}", method="DELETE"
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            json.loads(resp.read().decode("utf-8"))
        print(f"[ok]   DELETE /api/documents/{name}  → 已清理")
        post_json(base, "/api/reindex")
        print("       （已重建索引，恢复原状）")
    except Exception as e:                                  # noqa: BLE001
        print(f"[warn] 清理失败（不影响功能）：{e}")

    print("=" * 68)
    print("全部通过 ✓" if failed == 0 else f"{failed} 项失败 ✗")
    return 1 if failed else 0


if __name__ == "__main__":
    import urllib.parse  # noqa: E402

    sys.exit(main())
