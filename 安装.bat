@echo off
REM ===================================================================
REM  保险条款 RAG —— 一键安装
REM  双击运行即可。做三件事：
REM    1. 检查 Python / Node 版本
REM    2. 装 Python 依赖
REM    3. 装前端依赖并构建
REM  装完之后用 启动.bat 打开系统。
REM ===================================================================
setlocal
chcp 65001 >nul
cd /d "%~dp0"

echo.
echo ======================================================
echo   保险条款 RAG - 安装
echo ======================================================
echo.

REM ---------- 1. 检查 Python ----------
echo [1/4] 检查 Python...
where python >nul 2>nul
if errorlevel 1 (
  echo.
  echo   [失败] 没找到 python。
  echo   请先安装 Python 3.10 或更高版本：https://www.python.org/downloads/
  echo   安装时记得勾选 "Add Python to PATH"
  echo.
  pause
  exit /b 1
)
python -c "import sys; sys.exit(0 if sys.version_info>=(3,10) else 1)" >nul 2>nul
if errorlevel 1 (
  echo.
  echo   [失败] Python 版本太低，需要 3.10 或更高。
  python --version
  echo.
  pause
  exit /b 1
)
for /f "delims=" %%v in ('python --version 2^>^&1') do echo   OK  %%v

REM ---------- 2. 检查 Node ----------
echo.
echo [2/4] 检查 Node.js...
where npm >nul 2>nul
if errorlevel 1 (
  echo.
  echo   [警告] 没找到 npm，前端将无法构建。
  echo   想用网页界面的话，请安装 Node.js：https://nodejs.org/
  echo   不装也能用命令行问答。
  echo.
  set NO_NODE=1
) else (
  for /f "delims=" %%v in ('node --version 2^>^&1') do echo   OK  Node %%v
  set NO_NODE=0
)

REM ---------- 3. Python 依赖 ----------
echo.
echo [3/4] 安装 Python 依赖...
python -m pip install --upgrade pip -q 2>nul
python -m pip install -r requirements.txt -q
if errorlevel 1 (
  echo.
  echo   [失败] Python 依赖安装失败。
  echo   如果是网络问题，试试国内镜像：
  echo     python -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
  echo.
  pause
  exit /b 1
)
echo   OK  依赖装好了

REM ---------- 4. 前端 ----------
if "%NO_NODE%"=="0" (
  echo.
  echo [4/4] 构建前端（第一次会慢一点）...
  pushd web
  if not exist node_modules (
    call npm.cmd install --no-audit --no-fund
    if errorlevel 1 (
      echo   [警告] 前端依赖安装失败，可以稍后重试
      popd
      goto after_frontend
    )
  )
  call npm.cmd run build
  if errorlevel 1 (
    echo   [警告] 前端构建失败，可以稍后重试
  ) else (
    echo   OK  前端构建完成
  )
  popd
) else (
  echo.
  echo [4/4] 跳过前端构建
)
:after_frontend

REM ---------- 初始化数据 ----------
echo.
echo 初始化示例数据...
if not exist "data\raw\sample-anxin-2024.json" (
  python scripts\make_sample_data.py
)
if not exist "eval\testset.csv" (
  python scripts\make_testset.py
)
python scripts\build_index.py --rebuild

echo.
echo ======================================================
echo   安装完成
echo ======================================================
echo.
echo   下一步：双击 启动.bat
echo.
echo   想换成真实保险条款：
echo     python scripts\ingest.py "你的条款.pdf"
echo     python scripts\build_index.py --rebuild
echo.
pause
