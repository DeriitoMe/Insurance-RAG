"""验证落地页托管与资源可达（前端构建产物检查）。

用法：
    python scripts/check_web.py --base http://127.0.0.1:8000
"""

from __future__ import annotations

import argparse
import re
import sys
import urllib.error
import urllib.request


def get(base: str, path: str) -> tuple[int, bytes]:
    with urllib.request.urlopen(base + path, timeout=25) as r:
        return r.status, r.read()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    args = ap.parse_args()
    base = args.base.rstrip("/")
    failed = 0

    print("=" * 68)

    # 1) 落地页 HTML
    try:
        st, body = get(base, "/")
        html = body.decode("utf-8")
        title = re.search(r"<title>(.*?)</title>", html)
        print(f"[ok]   GET /                {st}  {len(html)} bytes")
        print(f"       title: {title.group(1) if title else '<无>'}")
    except Exception as e:                                  # noqa: BLE001
        print(f"[FAIL] GET /  {e}")
        print("       提示：先构建前端  npm --prefix web run build")
        return 1

    has_app = 'id="app"' in html
    refs = re.findall(r'(?:src|href)="(/assets/[^"]+)"', html)
    print(f"       #app 挂载点: {has_app}    引用构建资源: {len(refs)} 个")
    if not has_app:
        print("[FAIL] 页面里没有 #app，可能托管到了旧版 index.html")
        failed += 1
    if not refs:
        print("[FAIL] 页面没有引用任何构建资源")
        failed += 1

    # 2) 逐个请求资源，确认可访问
    print("-" * 68)
    print("静态资源可达性：")
    for ref in refs:
        try:
            st, b = get(base, ref)
            kind = ref.rsplit(".", 1)[-1]
            print(f"       {st}  {len(b):>9,} B  [{kind}]  {ref}")
        except Exception as e:                              # noqa: BLE001
            print(f"       FAIL  {ref}  {e}")
            failed += 1

    # 3) SPA 深链：/app 是前端路由，直连后端会 404
    print("-" * 68)
    try:
        st, _ = get(base, "/app")
        print(f"[ok]   GET /app              {st}")
    except urllib.error.HTTPError as e:
        print(f"[warn] GET /app 直连后端返回 {e.code}")
        print("       原因：/app 是前端路由，后端没有对应文件。")
        print("       影响：直接刷新或分享 /app 链接会 404。")
        print("       开发时用 npm run dev 不受影响（Vite 自带 history fallback）。")
        print("       生产修复方案：在 api.py 加一条兜底路由，把未知路径都返回 index.html。")
    except Exception as e:                                  # noqa: BLE001
        print(f"[FAIL] GET /app  {e}")
        failed += 1

    # 4) API 仍然可用
    print("-" * 68)
    try:
        st, b = get(base, "/api/health")
        print(f"[ok]   GET /api/health      {st}  {b.decode()[:96]}")
    except Exception as e:                                  # noqa: BLE001
        print(f"[FAIL] GET /api/health  {e}")
        failed += 1

    print("=" * 68)
    print("通过 ✓" if failed == 0 else f"{failed} 项失败 ✗")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
