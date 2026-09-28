@echo off
REM ===================================================================
REM  保险条款 RAG —— 一键启动
REM  双击运行。会自动打开浏览器。
REM  关掉这个黑窗口 = 关闭系统。
REM ===================================================================
setlocal
chcp 65001 >nul
cd /d "%~dp0"

set PORT=8000

echo.
echo ======================================================
echo   保险条款 RAG
echo ======================================================
echo.

REM ---------- 检查索引 ----------
if not exist "data\index\meta.json" (
  echo   索引不存在，先构建...
  python scripts\build_index.py --rebuild
  if errorlevel 1 (
    echo.
    echo   [失败] 索引构建失败。先跑一次 安装.bat 看看。
    echo.
    pause
    exit /b 1
  )
)

REM ---------- 检查前端 ----------
if not exist "web\dist\index.html" (
  echo   前端还没构建，正在构建...
  pushd web
  if not exist node_modules call npm.cmd install --no-audit --no-fund
  call npm.cmd run build
  popd
)

REM ---------- 启动 ----------
echo   地址：http://127.0.0.1:%PORT%
echo.
echo   按 Ctrl+C 可以停止
echo   ------------------------------------------------------
echo.

REM 延迟 2 秒打开浏览器，给服务一点启动时间
start "" /b cmd /c "timeout /t 2 >nul & start http://127.0.0.1:%PORT%"

set PYTHONPATH=%~dp0src
python -m uvicorn policyrag.api:app --host 127.0.0.1 --port %PORT%

echo.
echo   服务已停止。
pause
