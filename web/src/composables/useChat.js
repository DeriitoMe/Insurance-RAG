import { computed, onBeforeUnmount, reactive, ref } from 'vue'
import { askStream, fetchHealth, fetchProducts } from '@/api/client'

/**
 * 对话状态与流式处理。
 *
 * 把流式逻辑放进 composable 而不是组件里，是为了：
 *   1. 组件只负责渲染，不掺业务
 *   2. 以后要加"多轮对话历史"只改这里
 *   3. 可单独测试（不需要挂载组件）
 */

/**
 * 从**流式过程中**的原始文本里增量提取 answer 字段。
 *
 * 为什么要这个函数：SSE 传的是完整 JSON，而 JSON 生成到一半时
 * JSON.parse 一定失败。但用户需要看到"打字机效果"，
 * 所以要能从半截 JSON 里把 answer 的值抠出来。
 *
 * 处理三种情况：
 *   1. `{"answer":"还没写完`        → 取到结尾
 *   2. `{"answer":"写完了","cita`   → 在引号处停
 *   3. 还没出现 answer 字段          → 返回空
 */
export function extractPartialAnswer(raw) {
  const key = '"answer"'
  const i = raw.indexOf(key)
  if (i === -1) return ''

  // 找到冒号后的第一个引号
  let j = raw.indexOf(':', i + key.length)
  if (j === -1) return ''
  j = raw.indexOf('"', j + 1)
  if (j === -1) return ''

  let out = ''
  for (let k = j + 1; k < raw.length; k++) {
    const ch = raw[k]
    if (ch === '\\') {
      const next = raw[k + 1]
      if (next === undefined) break // 转义序列被截断，等下一块
      if (next === 'n') out += '\n'
      else if (next === 't') out += '\t'
      else if (next === '"') out += '"'
      else if (next === '\\') out += '\\'
      else if (next === 'u') {
        const hex = raw.slice(k + 2, k + 6)
        if (hex.length < 4) break
        out += String.fromCharCode(parseInt(hex, 16))
        k += 4
      }
      k += 1
      continue
    }
    if (ch === '"') break // answer 值结束
    out += ch
  }
  return out
}

export function useChat() {
  const health = ref(null)
  const products = ref([])
  const messages = ref([])

  const options = reactive({
    mode: 'hybrid',
    topN: 5,
    docIds: [],
  })

  const controller = ref(null)
  const isStreaming = computed(() => controller.value !== null)
  const statusText = computed(() => {
    if (!health.value) return '连接中…'
    if (health.value.error) return '服务配置异常'
    if (!health.value.index_ready) return '索引未就绪'
    return `已就绪 · ${health.value.index_size} chunks`
  })
  const statusType = computed(() => {
    if (!health.value) return 'info'
    if (health.value.error) return 'danger'
    return health.value.index_ready ? 'success' : 'warning'
  })

  async function loadHealth() {
    try {
      health.value = await fetchHealth()
      if (health.value.index_ready) {
        const p = await fetchProducts()
        products.value = p.products ?? []
      }
    } catch (e) {
      health.value = { index_ready: false, error: String(e) }
    }
  }

  function abort() {
    controller.value?.abort()
  }

  async function ask(question) {
    const q = question.trim()
    if (!q || isStreaming.value) return

    const message = reactive({
      id: Date.now(),
      question: q,
      answer: '',
      raw: '',
      sources: [],
      citations: [],
      usedArticles: [],
      answerable: null,
      debug: {},
      meta: '',
      error: '',
      streaming: true,
      firstTokenMs: null,
      startedAt: performance.now(),
    })
    messages.value.push(message)

    const ac = new AbortController()
    controller.value = ac

    const updateMeta = () => {
      const total = Math.round(performance.now() - message.startedAt)
      const ttft = message.firstTokenMs ? `${Math.round(message.firstTokenMs)}ms` : '-'
      message.meta = `首字 ${ttft} · 总耗时 ${total}ms`
      if (message.debug.recall_ms != null) {
        message.meta += ` · 检索 ${message.debug.recall_ms}ms`
      }
      if (message.debug.cache_hit) message.meta += ' · 命中缓存'
    }

    try {
      await askStream({
        question: q,
        mode: options.mode,
        topN: options.topN,
        docIds: options.docIds.length ? options.docIds : undefined,
        signal: ac.signal,
        onEvent: (evt) => {
          if (evt.type === 'sources') {
            message.sources = evt.sources ?? []
          } else if (evt.type === 'delta') {
            if (message.firstTokenMs === null) {
              message.firstTokenMs = performance.now() - message.startedAt
            }
            message.raw += evt.text
            // 流式过程中用宽松提取，让用户看到逐字出现
            message.answer = extractPartialAnswer(message.raw) || message.raw
          } else if (evt.type === 'final') {
            // final 是权威结果，覆盖流式过程中的猜测
            message.answer = evt.answer
            message.answerable = evt.answerable
            message.citations = evt.citations ?? []
            message.usedArticles = evt.used_articles ?? []
            message.debug = evt.debug ?? {}
            updateMeta()
          } else if (evt.type === 'error') {
            message.error = evt.message
          }
        },
      })
    } catch (e) {
      if (e.name === 'AbortError') {
        message.error = ''
        message.meta += ' · 已中断'
      } else {
        message.error = `请求失败：${e.message}`
      }
    } finally {
      message.streaming = false
      controller.value = null
      if (!message.meta) updateMeta()
    }
  }

  onBeforeUnmount(() => abort())

  return {
    health,
    products,
    messages,
    options,
    isStreaming,
    statusText,
    statusType,
    loadHealth,
    ask,
    abort,
  }
}
