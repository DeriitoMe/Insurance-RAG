# 前端（Vue3 + Vite + Element Plus）

两个路由，职责分明：

| 路由 | 组件 | 作用 |
|---|---|---|
| `/` | `views/LandingView.vue` | **落地页**：解释系统是什么、凭什么可信、怎么跑起来 |
| `/app` | `views/DemoView.vue` | **演示页**：真正的问答工作区 |

**为什么分开**：落地页要的是叙事节奏（长滚动、分段），演示页要的是工作区
（固定视口、不滚动）。塞进一页会互相打架。

---

# 一、落地页的设计决策

## 设计读取

> 面向**技术面试官与工程评估者**的展示页，采用 **dark-tech editorial /
> engineered documentation** 语言，倾向**自托管 IBM Plex + 原生 CSS 设计令牌 +
> 克制动效**。

**拨盘**：`DESIGN_VARIANCE: 6` / `MOTION_INTENSITY: 5` / `VISUAL_DENSITY: 4`

- **VARIANCE 取 6 而不是 8**：这是合规与风控语义的产品，"依据可审计"要求秩序感，
  不是艺术感。用非对称布局，但不上 chaos。
- **MOTION 取 5**：动效只用于**层级、顺序、状态反馈**，不做 scroll-jack。
- **DENSITY 取 4**：偏空，但每个数字必须是真的，这是 showcase 不是 SaaS 营销页。

## 六个节，六种布局族

| 节 | 布局族 |
|---|---|
| Hero | 非对称分栏（左文右数据面板） |
| 问题 | 左右对照 + 编号列表 |
| 实现 | 粘性左标题 + 右侧纵向五段 |
| 接口 | 标签页 + 代码面板 |
| 评测 | 数据表 + 无效判定块 + 右侧待办清单 |
| 行动 | 单卡片内两栏 |

**没有一个布局族被重复使用两次。**

## 全页一致性锁

| 锁 | 值 |
|---|---|
| 主题 | 单暗色主题，**没有任何一节翻转成浅色** |
| 强调色 | 只有 `--acc: #34d399` 一个彩色。语义色（warn/danger）只在真状态里出现 |
| 圆角 | 6px（按钮/输入）/ 12px（容器）/ 胶囊（仅标签）。没有混用规则 |
| 字体 | IBM Plex Sans（拉丁）+ 系统中文字体栈 + IBM Plex Mono（数据） |

## 两处刻意的"反 AI 默认"

1. **Hero 右侧不是客户 logo 墙**，是**真实项目指标面板**。
   作品集页本来就没有客户，硬造 logo 墙就是造假。
2. **评测节先给数字，紧接着声明这组数字无效**。
   对技术读者来说，一个敢标自己数据无效的项目，可信度远高于一堆漂亮数字。

## 关于图标

落地页**没有使用任何图标库，也没有手画装饰性 SVG**。
需要视觉锚点时用编号（`01`–`05`）和竖线。

唯一的手写 SVG 是顶栏的品牌标记（盾牌 + 对勾）—— 品牌标识不属于装饰性图标，
不受"禁止手画 SVG"约束。

---

# 二、三个可量化的性能优化（面试素材）

## 优化 1：Element Plus 深层导入，JS 从 1.19 MB 降到 436 KB

**问题**：首版写的是 `import { ElButton } from 'element-plus'`。
看起来是按需引入，但打包后 `element-plus` 分块仍有 **1.09 MB**。

**原因**：`'element-plus'` 是 **barrel 入口**（re-export 全部组件），
这个文件的副作用让它**无法被 tree-shaking 摇掉**，所有组件都被打进包里。

**解决**：改成深层导入 `element-plus/es/components/xxx/index.mjs`。

| 版本 | JS 总量 |
|---|---|
| 主入口导入 | 1.19 MB |
| **深层导入** | **436 KB** |

## 优化 2：Element Plus 按路由加载，落地页首屏从 371 KB 降到 33 KB

**问题**：组件和样式在 `main.js` 全局注册，落地页虽然完全不用 Element Plus，
却要为它付费。实测入口 HTML 会 `modulepreload` 338 KB 的 element-plus。

**解决**：把组件的**深层导入 + 局部注册**全部移到 `DemoView.vue`。
Vite 自动把它拆成路由级 chunk，只有进入 `/app` 才请求。

| | 落地页首屏 | 演示页额外 |
|---|---|---|
| 优化前 | 28 KB JS + **358 KB CSS** + 338 KB preload | — |
| **优化后** | **28 KB JS + 4.8 KB CSS** | 20 KB JS + 358 KB CSS |

## 优化 3：字体只引 latin 子集

**问题**：引 `@fontsource/ibm-plex-sans/400.css` 会把
greek / cyrillic / cyrillic-ext / vietnamese 子集**全部打包**，
产生几十个无用 woff/woff2 文件。

**解决**：改引 `latin-400.css` 这类子集文件。字体文件从几十个降到 **12 个**。

**中文为什么不自托管**：`@fontsource/noto-sans-sc` 实测 **71 MB**，
单字重 3.4 MB（最大分片 1.1 MB），两个字重就要 7 MB。
为一个展示页背这个体积不划算，中文改走系统字体栈
（苹方 / 微软雅黑 / Noto Sans CJK）。**这是有意的性能取舍，不是遗漏。**

---

# 三、三个可以讲的技术点

## 1. 为什么不用 `EventSource`

它是浏览器原生 SSE 客户端，一行就能用，但在这个场景有三个硬伤：

| 限制 | 影响 |
|---|---|
| 只能发 GET | 问题文本只能塞 URL，长问题会撞长度限制 |
| 不能自定义请求头 | 以后加 token 认证做不了 |
| **不能主动 abort** | 用户点"停止"取消不了请求，后端还在烧 token |

所以用 `fetch` + `ReadableStream` 手写消费逻辑，代价是要自己处理分片。

## 2. 增量 SSE 解析器（`api/client.js`）

**这是流式 UI 最容易翻车的地方。** 看起来"收到一段就 `JSON.parse`"就够了，
实际有三个真实情况：

```
情况 1：一个 SSE 事件被 TCP 分片切成两半
   read() → 'data: {"type":"del'
   read() → 'ta","text":"你"}\n\n'

情况 2：一次 read() 拿到多个完整事件
   read() → 'data:{...}\n\ndata:{...}\n\ndata:{...}\n\n'

情况 3：中文 UTF-8 被切在字节边界上
   '你' = E4 BD A0，可能 E4 在前一个 chunk、BD A0 在后一个
```

对应三个处理：
1. **按 `\n\n` 分割 + 保留不完整尾部在缓冲区**（`createSSEParser`）
2. **循环处理所有完整事件**，而不是只处理第一个
3. **`TextDecoder({ stream: true })`** —— 专门处理跨 chunk 的多字节字符

## 3. 从半截 JSON 里提取 `answer`（`composables/useChat.js`）

SSE 传的是完整 JSON，但 JSON 生成到一半时 `JSON.parse` 一定失败，
而用户需要看到"打字机效果"。所以要能从半截文本里把 `answer` 抠出来：

```
流式中间态：{"answer":"根据第三条，等待期","citations":[...
                                     ↑ 要提取到这里为止
```

`extractPartialAnswer()` 逐字符扫描并处理转义序列（`\n` `\"` `\uXXXX`），
遇到未闭合的转义序列就停下等下一块。

**完成后用 `final` 事件覆盖** —— 流式过程中显示的是"猜测"，`final` 才是权威结果。
这个"先猜后覆盖"的模式是流式 UI 的标准做法。

---

# 四、开发与构建

```bash
cd web
npm install          # 已配 .npmrc 走 npmmirror
npm run dev          # http://127.0.0.1:5173
npm run build        # 产物在 web/dist，由 FastAPI 托管
```

**开发时后端要同时跑着**：
```bash
# 另开终端
uvicorn policyrag.api:app --app-dir src --port 8000
```

**`vite.config.js` 里的 proxy 必须带 `rewrite`**：
```js
'/api': {
  target: 'http://127.0.0.1:8000',
  rewrite: (path) => path.replace(/^\/api/, ''),   // 少了这行会变成 /api/api/health
}
```
原因：前端统一请求 `/api/xxx`，而后端自己挂着 `/api` 路由。
开发时走的是"去掉前缀再转发"，生产时走的是"同源直连"。两种都需要。

---

# 五、⚠️ 本机环境的两个限制

## 限制 1：`npm` 官方 registry 超时

本机实测 `registry.npmjs.org` 15 秒无响应。已在 `.npmrc` 里固定：
```
registry=https://registry.npmmirror.com
```

## 限制 2：沙箱禁止进程间管道通信 → `npm install` / `vite build` 报 `spawn EPERM`

**不是代码问题，是执行环境限制。** npm 11 会跑 `esbuild` 的 postinstall 子进程，
而 `vite build` 必须 spawn esbuild 进程做转换。

**两个解决办法**：

**（推荐）在普通终端里跑** —— 自己打开 PowerShell 就没有这个限制：
```powershell
cd "D:\ds harness\insurance-rag\web"
npm install
npm run build
npm run dev
```

**受管环境里**需要提升沙箱权限。本项目在验证阶段就是这样跑通的。

另外 **PowerShell 执行策略会禁止 `npm.ps1`**，报
"无法加载文件 D:\node\npm.ps1，因为在此系统上禁止运行脚本"。
两个解法：
1. **加 `.cmd` 后缀**：`npm.cmd run dev`（零风险，推荐）
2. **改策略**：`Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned`
   （开发者标准配置，需新开窗口生效）

---

# 六、目录结构

```
web/
├─ index.html                 Vite 入口
├─ vite.config.js             代理（含 rewrite）、别名、分包
├─ package.json
├─ .npmrc                     国内镜像
└─ src/
   ├─ main.js                 极简入口（不含 Element Plus）
   ├─ App.vue                 路由出口 + 页面过渡
   ├─ router/index.js         / 与 /app
   ├─ api/client.js           ★ 接口封装 + SSE 增量解析器
   ├─ composables/
   │  ├─ useChat.js           ★ 对话状态 + 流式处理 + 半截 JSON 提取
   │  └─ useReveal.js         IntersectionObserver 入场动效
   ├─ views/
   │  ├─ LandingView.vue      落地页组装
   │  └─ DemoView.vue         演示页（Element Plus 在这里注册）
   ├─ components/
   │  ├─ landing/             落地页六节 + 顶栏 + 页脚
   │  ├─ QuestionPanel.vue
   │  ├─ MessageCard.vue
   │  └─ SourceList.vue       ★ 引用溯源展示
   └─ styles/main.css         设计令牌 + 排版工具类 + 按钮
```
