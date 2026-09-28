/**
 * 后端接口封装。
 *
 * 关键设计：**引用与正文分开两条消息**。
 * 后端先发 `sources`（检索到的条款，用于立即渲染来源），
 * 再逐块发 `delta`（token 流），最后发 `final`（含解析好的引用）。
 * 这样前端不用边收流边解析半截 JSON —— 那是流式 UI 最常见的翻车点。
 *
 * 开发环境走 Vite 代理（/api → http://127.0.0.1:8000），避开 CORS。
 * 生产环境由 FastAPI 托管构建产物，同源，也不需要 CORS。
 */

const BASE = '/api'

export async function fetchHealth() {
  const resp = await fetch(`${BASE}/health`)
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
  return resp.json()
}

export async function fetchProducts() {
  const resp = await fetch(`${BASE}/products`)
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
  return resp.json()
}

export async function askOnce(payload) {
  const resp = await fetch(`${BASE}/ask`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json; charset=utf-8' },
    body: JSON.stringify(payload),
  })
  if (!resp.ok) throw new Error(`HTTP ${resp.status}: ${await resp.text()}`)
  return resp.json()
}

/**
 * 流式解析器 —— 这一版比"收到什么就 JSON.parse 什么"可靠得多。
 *
 * 需要处理三个真实情况：
 *   1. 一个 SSE 事件可能被 TCP 分片切成两半
 *   2. 一次 read() 可能拿到多个完整事件
 *   3. `data:` 行之间可能有空行、可能有注释行（`: ping`）
 *
 * 所以用一个带缓冲的增量解析器，而不是在 read 回调里直接 parse。
 */
function createSSEParser(onEvent) {
  let buffer = ''

  return function feed(text) {
    buffer += text
    // SSE 事件以空行分隔；\r\n\r\n 和 \n\n 都要兼容
    const normalized = buffer.replace(/\r\n/g, '\n')
    const chunks = normalized.split('\n\n')
    // 最后一段可能是不完整的事件，留在缓冲里等下一个 chunk
    buffer = chunks.pop() ?? ''

    for (const raw of chunks) {
      const dataLines = raw
        .split('\n')
        .filter((l) => l.startsWith('data:'))
        .map((l) => l.slice(5).trimStart())
      if (!dataLines.length) continue

      const payload = dataLines.join('\n')
      if (payload === '[DONE]') {
        onEvent({ type: 'done' })
        continue
      }
      try {
        onEvent(JSON.parse(payload))
      } catch {
        // 半截 JSON 直接丢弃，等后续补全 —— 不抛异常、不中断流
      }
    }
  }
}

/**
 * 发起流式问答。
 *
 * @param {object} opts
 * @param {string} opts.question
 * @param {string} [opts.mode]
 * @param {number} [opts.topN]
 * @param {string[]} [opts.docIds]
 * @param {AbortSignal} [opts.signal]
 * @param {(evt: object) => void} opts.onEvent  收到事件时回调
 */
export async function askStream({ question, mode = 'hybrid', topN, docIds, signal, onEvent }) {
  const params = new URLSearchParams({ question, mode })
  if (topN) params.set('top_n', String(topN))
  if (docIds?.length) params.set('doc_ids', docIds.join(','))

  const resp = await fetch(`${BASE}/ask/stream?${params.toString()}`, { signal })
  if (!resp.ok) {
    throw new Error(`HTTP ${resp.status}: ${await resp.text()}`)
  }
  if (!resp.body) {
    throw new Error('当前环境不支持流式响应（resp.body 为空）')
  }

  const reader = resp.body.getReader()
  const decoder = new TextDecoder('utf-8')
  const feed = createSSEParser(onEvent)

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      // stream: true 很关键 —— 一个中文字符可能被切成两个字节分两次到达
      feed(decoder.decode(value, { stream: true }))
    }
    feed(decoder.decode()) // 冲刷残留
  } finally {
    reader.releaseLock()
  }
}
