"""脚本公用引导：把 src 加进 sys.path，保证不用安装也能直接运行脚本。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# Windows 控制台默认 GBK，中文输出会乱码甚至抛异常
for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8")      # type: ignore[union-attr]
    except (AttributeError, ValueError):
        pass

__all__ = ["ROOT", "SRC"]
