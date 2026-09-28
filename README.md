# 保险条款 RAG

把一份或几份保险条款变成**可问答、可溯源、可评测**的知识库。

> 定位：不是"能跑起来的 RAG demo"，是一个**每个决策都能解释、效果有量化数据**的应用。

---

## 它解决什么

保险条款有两个特点：
1. 一份条款几十条，普通人读不完；
2. "赔不赔"这类问题**往往不能只看一条** —— 要同时看保险责任、责任免除、等待期、既往症定义。

所以目标不是"能聊天"，而是**给出有依据、能溯源的结论**。

---

## 快速开始

### 最省事：双击运行

| 文件 | 作用 |
|---|---|
| **`安装.bat`** | 第一次用，双击它。自动检查环境、装依赖、建索引 |
| **`启动.bat`** | 之后每天用，双击它。自动启动并打开浏览器 |

### 命令行方式

```bash
# 0. 依赖
pip install -r requirements.txt

# 1. 自检（不依赖任何外部服务，先确认能不能跑）
python scripts/selfcheck.py

# 2. 生成示例语料 + 30 题评测集
python scripts/make_sample_data.py
python scripts/make_testset.py

# 3. 建索引
python scripts/build_index.py --dump 1

# 4a. 前端（Vue3 + Vite）
cd web && npm install && npm run build && cd ..
uvicorn policyrag.api:app --app-dir src --port 8000
# 打开 http://127.0.0.1:8000

# 4b. 前端开发模式（热更新，走 /api 代理）
cd web && npm run dev     # http://127.0.0.1:5173（后端需另开终端跑着）

# 4c. 命令行问答
python scripts/cli.py ask "等待期是多少天"

# 5. 测试
python tests/test_chunker.py                              # 18 个单元测试
python scripts/test_api.py --base http://127.0.0.1:8000   # API + SSE 端到端
python scripts/test_upload.py --base http://127.0.0.1:8000 # 上传 + 重建

# 6. 评测
python scripts/eval.py --mode all
```

### Docker（发给别人用）

```bash
docker compose up -d
# 打开 http://localhost:8000
```

打开 `/app` 顶部的「模型设置」填写 Embedding 和 LLM API；Docker 会把设置保存到本机被忽略的 `.runtime/settings.env`。

GitHub 用于托管源码和自动构建镜像；本项目需要 FastAPI 后端，不能仅靠 GitHub Pages 提供问答服务。

对方**不需要装 Python、不需要装 Node**。用自己的条款就直接在网页上拖文件进去
（`/app` 页面右上角「管理语料」）。

**部署与分享的完整说明见 [`docs/08-部署与分享.md`](docs/08-部署与分享.md)**，
包含：一键脚本、Docker、nginx 反代（含 SSE 必须的三个配置）、
GitHub Actions 自动构建镜像、推送前必须检查的三件事。

---

## 在网页上管理语料

不用碰命令行。打开 http://127.0.0.1:8000/app ，点右上角「管理语料」：

1. **拖 PDF 进来** → 自动清理页眉页脚、识别「第X条」结构、预检报告识别出多少个块
2. **点「重建索引」** → 新语料生效
3. 想删就直接删，再重建一次

对应三个接口：

| 接口 | 作用 |
|---|---|
| `GET /api/documents` | 列出 `data/raw` 里的文件，标注哪些会被加载 |
| `POST /api/upload` | 上传文件（multipart），**顺手做一次识别预检** |
| `POST /api/reindex` | 重建索引 |
| `DELETE /api/documents/{name}` | 删除语料文件 |

> **上传和重建为什么分成两步**：重建要跑 embedding，可能几十秒。
> 合成一步会让用户面对一个长时间没反应的按钮。分开之后前端可以先说
> "已上传，点了重建才生效"。


---

## 前端技术栈

| 层 | 选择 | 说明 |
|---|---|---|
| 框架 | **Vue3**（`<script setup>`） | JD 要求"了解 Vue/React" |
| 构建 | **Vite 6** | 冷启动快，配置简单 |
| UI 库 | **Element Plus**（深层导入按需） | 打包产物 1.19 MB → **436 KB** |
| 流式 | **原生 `fetch` + `ReadableStream`** | 不用 `EventSource`：它只能 GET、不能自定义头、不能 abort |
| 部署 | FastAPI 托管 `dist/` | **同源，不需要 CORS** |

细节见 [`web/README.md`](web/README.md)——里面有"为什么不用 EventSource"、
"增量 SSE 解析器要处理哪三种分片情况"、"如何从半截 JSON 里提取答案"三个可讲的点。


---

## 换成真实语料（推荐优先做这件事）

**一条命令就够**，PDF / 文本都行：

```bash
# 先预览，看识别对不对（不写文件）
python scripts/ingest.py "你的条款.pdf" --dry-run

# 确认无误后入库
python scripts/ingest.py "你的条款.pdf" --product-name "平安e生保长期医疗险"

# 重建索引 + 验证
python scripts/build_index.py --rebuild
python scripts/cli.py products
python scripts/cli.py ask "等待期是多少天" --docs 你的doc_id
```

`ingest.py` 会自动清理 PDF 抽取的四类噪声：

| 噪声 | 为什么必须处理 |
|---|---|
| 页码、页脚 | 每页重复 → 让所有 chunk 共享高频词，稀释内容特征 |
| **跨页页眉（各页文字不同）** | 同上；按"位置"检测而非"重复次数"，因为真实 PDF 各页页眉常不一样 |
| **标题与正文挤在一行** | 不切开的话整行被当标题，**正文全丢** |
| **标题被换行拆开** | 不拼回来的话标题残缺、条号识别不全 |

**完整流程与排查手册见 [`docs/06-语料入库流程.md`](docs/06-语料入库流程.md)**。
本机测试 PDF 因体积较大不会上传 GitHub；新 clone 可在 Windows 上先生成：

```powershell
python scripts/make_test_pdf.py
python scripts/debug_pdf_text.py data/samples/测试条款.pdf   # 看原始抽取结果
python scripts/ingest.py data/samples/测试条款.pdf --dry-run  # 看清洗过程
python scripts/debug_headers.py data/samples/测试条款.pdf     # 看页眉检测内部状态
```

当前本机工作目录整理的四份平安 2026 团体保险条款、段落数和表格处理记录见
[`docs/09-平安2026团体条款入库记录.md`](docs/09-平安2026团体条款入库记录.md)。为避免未经确认分发真实条款，四份 JSON 默认由 Git 忽略；新 clone 只附带合成示例语料。

真实条款获取路径见 [`docs/05-真实语料获取指南.md`](docs/05-真实语料获取指南.md)：
保险公司官网「公开信息披露」、中国保险行业协会产品信息库。

> **扫描件不支持**：整页是图片、没有文字层的 PDF 抽不出文本。
> 脚本会明确报错并提示你先做 OCR，不会静默产生空语料。



---

## 接入真实模型（拿到有效评测数字的前提）

### 方案 A：API（最快）

打开 `/app` 页面顶部的「模型设置」，填写 Embedding 与 LLM 的 API 地址、模型名和 API Key，点「保存并应用」即可；Embedding 设置变化后还需在「管理语料」里重建索引。配置会写入本机忽略文件（本地运行写入根目录 `.env`，Docker 写入 `.runtime/settings.env`），密钥不会回显。这个配置接口只允许本机访问；远程服务器请在服务端配置环境变量或 `.runtime/settings.env`。

也可以手动编辑 `.env`。本机启动时，项目会自动读取根目录 `.env`（系统环境变量优先）：

```powershell
Copy-Item .env.example .env
notepad .env
```

在 `.env` 中填入真实服务的 API key、地址和模型名，保存后重启 `启动.bat`。模板默认是安全的离线模式；API key 留空时不会调用真实服务。`.env` 已被忽略，不要把密钥提交到仓库。

若想在当前 PowerShell 窗口临时设置，可复制下面模板，把尖括号内容换成自己的配置。这些变量只对当前窗口及其启动的进程生效：

```powershell
$env:PR_EMB_PROVIDER = "api"
$env:PR_EMB_API_BASE = "https://api.siliconflow.cn/v1"
$env:PR_EMB_API_KEY = "<填你的 embedding API key>"
$env:PR_EMB_MODEL = "BAAI/bge-m3"

$env:PR_LLM_PROVIDER = "api"
$env:PR_LLM_API_BASE = "https://api.deepseek.com/v1"
$env:PR_LLM_API_KEY = "<填你的 LLM API key>"
$env:PR_LLM_MODEL = "deepseek-chat"

python scripts/build_index.py --rebuild
uvicorn policyrag.api:app --app-dir src --port 8000
```

不要把填好 key 的命令保存到会提交的 `.ps1` 文件；长期配置请写在已忽略的 `.env` 中。换 embedding 模型后必须重建索引。

### 方案 B：本地模型（数据不出内网）

```bash
pip install sentence-transformers
$env:PR_EMB_PROVIDER="local"
$env:PR_EMB_MODEL="BAAI/bge-large-zh-v1.5"
$env:PR_RERANK_MODEL="BAAI/bge-reranker-base"
$env:PR_USE_RERANK="1"
```

**⚠️ 换 embedding 模型必须 `--rebuild`。** 不同模型的向量不在同一空间，
索引文件里存了 signature，不匹配会直接报错，而不是静默返回垃圾结果。

---

## 全部环境变量

| 变量 | 默认 | 说明 |
|---|---|---|
| `PR_EMB_PROVIDER` | `hash` | `hash`（零依赖兜底）/ `api` / `local` |
| `PR_EMB_MODEL` | `BAAI/bge-large-zh-v1.5` | embedding 模型 |
| `PR_EMB_API_BASE` / `PR_EMB_API_KEY` | — | API 方案的地址与密钥 |
| `PR_LLM_PROVIDER` | `mock` | `mock`（离线）/ `api` |
| `PR_LLM_MODEL` / `PR_LLM_API_BASE` / `PR_LLM_API_KEY` | — | 生成模型配置 |
| `PR_MAX_CHARS` | `800` | 单块最大字数，超出按列表项二次切 |
| `PR_MIN_CHARS` | `60` | 单块最小字数，不足与相邻同级条款合并 |
| `PR_INJECT_PATH` | `1` | 是否把层级路径注入文本（**核心主张，别关**） |
| `PR_TOP_K` | `20` | 一阶段召回数量 |
| `PR_TOP_N` | `5` | 送进模型的数量 |
| `PR_USE_BM25` | `1` | 是否启用混合检索 |
| `PR_USE_RERANK` | `0` | 是否启用重排序 |

---

## 目录结构

```
insurance-rag/
├─ docs/          01 技术方案 · 03 迭代日志 · 04 面试话术 · 05 真实语料获取指南
├─ data/raw/      本地语料；Git 默认只跟踪合成示例
├─ data/index/    索引产物（可重建，不入 git）
├─ eval/          testset.csv（30 题）+ results/（本地评测输出，不入 git）
├─ src/policyrag/ schema config ingest embedding index retrieval generation pipeline api
├─ scripts/       selfcheck / make_sample_data / make_testset / build_index / cli / eval / test_api
├─ tests/         单元测试（切分器是重点）
└─ web/           Vue3 + Vite + Element Plus 前端
```

---

## 设计要点（面试会问的）

| 决策 | 选择 | 为什么 |
|---|---|---|
| 切分 | **按条款层级** | 按字数切会把"等待期"和"保险责任"切开，检索出半句话 |
| 检索 | **向量 + BM25 混合** | 纯向量不擅长编号匹配，纯 BM25 不擅长同义表达 |
| 融合 | **RRF** | 只用排名不用分数，绕开两个检索器量纲不同的问题 |
| 向量库 | **numpy 暴力检索** | 几百个 chunk 时 <10ms，上万条再换 HNSW |
| 输出 | **JSON + Pydantic 强校验** | 引用要被程序处理，不能靠正则从自然语言里抠 |
| 评测 | **检索层 / 生成层分开** | 分不开就无法定位"是没检索到还是模型胡说" |

---

## ⚠️ 已知限制（诚实写在这里，别装作没有）

1. **GitHub 仓库附带的语料是合成示例**，不是任何真实产品条款；本机真实条款默认不提交。
2. **PDF 只支持文本型**，扫描件需要 OCR（未实现）；普通表格可能被抽成乱序文本，已对本批伤残比例附表做了专门归一化。
3. **默认 hash 向量不是语义向量**，用它的评测数字没有意义（脚本会明确警告）。
4. **`mock` LLM 不调用真实模型**，只用于离线跑通链路和写测试。
5. **评测集目前偏简单**：21 个 chunk + 答案原词直接出现在正文里，
   导致基线全 100%，属于**评测失效**，详见 `docs/03-迭代日志.md`。
   **扩语料 + 加跨条款计算题**是下一步最重要的工作。
6. **本机未安装 Docker**，`Dockerfile` 已写好但未在本地验证。
7. **前端引用的条款原文来自合成语料**，换成真实条款后引用内容才真实。

---

## Docker（写好但未在本机验证）

```bash
docker build -t insurance-rag .
docker run -p 8000:8000 \
  -e PR_EMB_PROVIDER=api -e PR_EMB_API_KEY=sk-... \
  -e PR_LLM_PROVIDER=api -e PR_LLM_API_KEY=sk-... \
  insurance-rag
```

---

## 许可证 / 语料来源

代码 MIT。语料请自行确认来源合法性 —— 保险公司官网公开条款通常可用于个人学习研究，
**商用前需确认授权**。
