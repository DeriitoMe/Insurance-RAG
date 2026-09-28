<script setup>
/**
 * 接口节：标签页 + 代码面板。
 *
 * 这是落地页上唯一"像文档"的一节，用等宽字体和深色代码面，
 * 与其它节形成材质差异（skill 要求拒绝"卡片装一切"）。
 *
 * 内容全部是真实接口，不是编的：这些 endpoint 在实际服务里都存在，
 * 用 python scripts/test_api.py 可以直接验证。
 */
import { ref } from 'vue'

const tabs = [
  {
    id: 'stream',
    label: '流式问答',
    note: '浏览器只用一次 GET，就能拿到「来源 -> token 流 -> 完整结果」三段结构。',
    // ⚠️ 注意：这里的 {{ }} 在 Vue 模板里是插值语法。
    // 代码示例中的 JSON 大括号必须转义成 \u007b / \u007d，
    // 否则 Vite 编译时会报 "invalid expression" 直接构建失败。
    code: `GET /api/ask/stream?question=甲状腺结节能赔吗&mode=hybrid

# 事件序列（SSE，data: <json> + 空行分隔）
\u007b"type":"sources","sources":[
  \u007b"label":"安心保百万医疗险（2024版） 第十一条", ...\u007d,
  \u007b"label":"安心保百万医疗险（2024版） 第六条", ...\u007d
]\u007d
\u007b"type":"delta","text":"根据第十一条"\u007d
\u007b"type":"delta","text":"，标准体承保的结节"\u007d
...
\u007b"type":"final","answer":"...","answerable":true,
 "citations":[\u007b"label":"... 第十一条","quote":"..."\u007d],
 "debug":\u007b"recall_ms":3.5,"cache_hit":false\u007d\u007d

data: [DONE]`,
  },
  {
    id: 'ask',
    label: '非流式',
    note: '评测脚本和第三方系统走这条，返回完整 JSON，便于批量调用与落盘。',
    code: `POST /api/ask
Content-Type: application/json; charset=utf-8

\u007b
  "question": "安心保的等待期是多少天？",
  "mode": "hybrid",        // hybrid | vector | keyword
  "top_k": 20,             // 一阶段召回数量
  "top_n": 5,              // 送进模型的条款数
  "doc_ids": null,         // 限定产品，多产品对比时使用
  "use_cache": true
\u007d

# 200
\u007b
  "question": "安心保的等待期是多少天？",
  "answer": "自合同生效之日起 90 日为等待期【安心保百万医疗险 第三条】",
  "answerable": true,
  "citations": [\u007b"product_name":"...","article_no":"第三条","quote":"..."\u007d],
  "used_articles": ["第三条"],
  "retrieved": [\u007b"chunk_id":"...","score":0.0164,"source":"hybrid"\u007d],
  "latency_ms": 12,
  "debug": \u007b"mode":"hybrid","recall_count":21,"recall_ms":3.5\u007d
\u007d`,
  },
  {
    id: 'citation',
    label: '引用结构',
    note: '引用是结构化字段，不是从自然语言里正则抠出来的。这样前端才能渲染成可核对的来源列表。',
    code: `# 引用从检索到的块反查，带上原文片段
Citation(
  doc_id       = "sample-anxin-2024",
  product_name = "安心保百万医疗险（2024版）",
  article_no   = "第三条",
  article_title= "等待期",
  chunk_id     = "sample-anxin-2024#0003-1acc19c8",
  quote        = "自本合同生效之日起90日为等待期。"
)

# chunk 元数据（溯源链路的末端）
\u007b
  "chunk_id": "sample-anxin-2024#0003-...",
  "section_path": ["第一部分 总则", "第三条 等待期"],
  "article_no": "第三条",
  "text": "【安心保百万医疗险（2024版） > 第一部分 总则 > 第三条 等待期】\\n...",
  "raw_text": "自本合同生效之日起90日为等待期。...",
  "char_len": 268
\u007d`,
  },
  {
    id: 'ops',
    label: '运维',
    note: '部署相关的两个细节：索引签名校验，以及流式响应必须关掉代理缓冲。',
    code: `GET /api/health
\u007b
  "status": "ok",
  "index_ready": true,
  "index_size": 21,
  "embedding": "hash-v1-dim512",   // 换模型后与索引不匹配会直接报错
  "llm": "MockLLM",
  "web_dist": true
\u007d

# 流式响应的响应头（缺一个，打字机效果就会消失）
Content-Type: text/event-stream; charset=utf-8
Cache-Control: no-cache
X-Accel-Buffering: no      # nginx 不加这个会缓冲整个响应`,
  },
]

const active = ref('stream')
const current = () => tabs.find((t) => t.id === active.value)
</script>

<template>
  <section id="api" class="sec">
    <div class="wrap">
      <div class="head reveal">
        <p class="label">接口</p>
        <h2 class="h2">四个端点，一次联调</h2>
        <p class="lede">
          前后端之间传的不是普通 JSON，而是 token 流。所以流式这条协议的细节
          单独列出来，它是"能演示"和"能上线"的分界。
        </p>
      </div>

      <div class="panel reveal">
        <div class="tabs" role="tablist" aria-label="接口示例">
          <button
            v-for="t in tabs"
            :key="t.id"
            role="tab"
            class="tab"
            :class="{ on: active === t.id }"
            :aria-selected="active === t.id"
            @click="active = t.id"
          >
            {{ t.label }}
          </button>
        </div>

        <div class="body">
          <p class="note">{{ current().note }}</p>
          <pre class="code"><code>{{ current().code }}</code></pre>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.sec {
  padding: 88px 0;
  border-top: 1px solid var(--line);
}

.head {
  max-width: 660px;
  margin-bottom: 36px;
}

.head .label {
  margin-bottom: 14px;
}

.head .lede {
  margin-top: 16px;
}

.panel {
  border: 1px solid var(--line);
  border-radius: var(--r-md);
  overflow: hidden;
  background: var(--bg-sunken);
}

.tabs {
  display: flex;
  gap: 0;
  border-bottom: 1px solid var(--line);
  background: var(--bg-raise);
  overflow-x: auto;
  scrollbar-width: none;
}

.tabs::-webkit-scrollbar {
  display: none;
}

.tab {
  appearance: none;
  border: 0;
  background: transparent;
  color: var(--ink-mute);
  font: inherit;
  font-size: 13px;
  padding: 13px 18px;
  cursor: pointer;
  white-space: nowrap;
  border-bottom: 2px solid transparent;
  transition:
    color 0.15s ease,
    border-color 0.15s ease,
    background 0.15s ease;
}

.tab:hover {
  color: var(--ink);
  background: rgba(255, 255, 255, 0.02);
}

.tab.on {
  color: var(--acc);
  border-bottom-color: var(--acc);
}

.tab:focus-visible {
  outline: 2px solid var(--acc);
  outline-offset: -2px;
}

.body {
  padding: 20px clamp(16px, 2.4vw, 24px) 24px;
}

.note {
  font-size: 13px;
  color: var(--ink-mute);
  max-width: 68ch;
  margin-bottom: 14px;
}

.code {
  margin: 0;
  overflow-x: auto;
  font-size: 12.5px;
  line-height: 1.75;
  color: var(--ink-soft);
  tab-size: 2;
}

.code code {
  font-family: var(--mono);
}

/* 底部给代码面板一点渐隐，避免长行硬切 */
.panel::after {
  content: '';
  display: block;
  height: 0;
}

@media (max-width: 860px) {
  .sec {
    padding: 64px 0;
  }
  .code {
    font-size: 11.5px;
  }
}
</style>
