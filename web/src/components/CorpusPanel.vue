<script setup>
/**
 * 语料管理面板：在网页上直接上传条款、重建索引、删除语料。
 *
 * 为什么需要它：
 * 原来看条款必须放进 data/raw/ 再敲命令行。对不熟命令行的人是最大的一道坎。
 * 有了这个面板，拖一个 PDF 进来点两下就完事。
 *
 * 设计要点：
 *  - **上传和重建分成两步**，不是一个按钮。因为重建要跑 embedding，可能几十秒，
 *    合成一步会让用户面对一个长时间没反应的按钮。
 *  - **上传后立刻预检**，马上告诉用户"识别出多少个块"，
 *    而不是等他重建完才发现"识别出 0 条"。
 *  - 重建期间显示进度状态，按钮禁用，避免重复点击。
 */
import { computed, onMounted, ref } from 'vue'

const props = defineProps({
  apiBase: { type: String, default: '/api' },
})
const emit = defineEmits(['reindexed'])

const files = ref([])
const busy = ref('')          // '' | 'upload' | 'reindex' | 'delete'
const message = ref(null)     // { type, text }
const lastUpload = ref(null)
const inputEl = ref(null)

const canReindex = computed(() => !busy.value)

async function loadFiles() {
  try {
    const r = await fetch(`${props.apiBase}/documents`)
    if (!r.ok) throw new Error(`HTTP ${r.status}`)
    const d = await r.json()
    files.value = d.files || []
  } catch (e) {
    message.value = { type: 'error', text: `读取语料列表失败：${e.message}` }
  }
}

async function doUpload(file) {
  if (!file) return
  busy.value = 'upload'
  message.value = null
  lastUpload.value = null

  const fd = new FormData()
  fd.append('file', file)

  try {
    const r = await fetch(`${props.apiBase}/upload`, { method: 'POST', body: fd })
    const d = await r.json()
    if (!r.ok) throw new Error(d.detail || `HTTP ${r.status}`)

    lastUpload.value = d
    const pv = d.preview || {}
    const n = pv.recognized
    if (n === 0) {
      message.value = {
        type: 'warning',
        text: `${d.saved_as} 已上传，但没识别出条款（${pv.note}）。检查标题是否独占一行、是否以「第X条」开头。`,
      }
    } else {
      message.value = {
        type: 'success',
        text: `${d.saved_as} 已上传，预检识别出 ${n} 个块。点「重建索引」让它生效。`,
      }
    }
    await loadFiles()
  } catch (e) {
    message.value = { type: 'error', text: `上传失败：${e.message}` }
  } finally {
    busy.value = ''
    if (inputEl.value) inputEl.value.value = ''
  }
}

function onPick(e) {
  doUpload(e.target.files?.[0])
}

function onDrop(e) {
  const f = e.dataTransfer?.files?.[0]
  if (f) doUpload(f)
}

async function doReindex() {
  busy.value = 'reindex'
  message.value = null
  try {
    const r = await fetch(`${props.apiBase}/reindex`, { method: 'POST' })
    const d = await r.json()
    if (!r.ok) throw new Error(d.detail || `HTTP ${r.status}`)
    message.value = {
      type: 'success',
      text: `重建完成：${d.documents} 份语料，共 ${d.chunks} 个块。现在可以提问了。`,
    }
    lastUpload.value = null
    emit('reindexed', d)
  } catch (e) {
    message.value = { type: 'error', text: `重建失败：${e.message}` }
  } finally {
    busy.value = ''
  }
}

async function doDelete(name) {
  if (!confirm(`确定删除 ${name}？删完要重建索引才会生效。`)) return
  busy.value = 'delete'
  message.value = null
  try {
    const r = await fetch(`${props.apiBase}/documents/${encodeURIComponent(name)}`, {
      method: 'DELETE',
    })
    const d = await r.json()
    if (!r.ok) throw new Error(d.detail || `HTTP ${r.status}`)
    message.value = { type: 'info', text: `${name} 已删除。点「重建索引」让它从系统里消失。` }
    await loadFiles()
  } catch (e) {
    message.value = { type: 'error', text: `删除失败：${e.message}` }
  } finally {
    busy.value = ''
  }
}

onMounted(loadFiles)

defineExpose({ loadFiles })
</script>

<template>
  <section class="corpus">
    <div class="head">
      <span class="label">语料管理</span>
      <span class="hint">支持 PDF / JSON / TXT</span>
    </div>

    <!-- 上传区 -->
    <div
      class="drop"
      :class="{ busy: busy === 'upload' }"
      @dragover.prevent
      @drop.prevent="onDrop"
      @click="inputEl?.click()"
    >
      <input
        ref="inputEl"
        type="file"
        accept=".pdf,.json,.txt,.text"
        hidden
        @change="onPick"
      />
      <p v-if="busy === 'upload'" class="drop-main">正在上传…</p>
      <template v-else>
        <p class="drop-main">把条款文件拖到这里，或点一下选择</p>
        <p class="drop-sub">PDF 会自动清理页眉页脚并识别「第X条」结构</p>
      </template>
    </div>

    <!-- 提示 -->
    <div v-if="message" class="msg" :class="message.type">
      {{ message.text }}
    </div>

    <!-- 文件列表 -->
    <div class="files">
      <div class="files-head">
        <span class="label">data/raw</span>
        <span class="count">{{ files.length }} 个文件</span>
      </div>

      <div v-if="!files.length" class="empty">还没有语料文件</div>

      <ul v-else>
        <li v-for="f in files" :key="f.name">
          <span class="kind" :class="{ ok: f.loadable }" :title="f.loadable ? '会被加载' : '不会被加载'">
            {{ f.loadable ? '语料' : '忽略' }}
          </span>
          <span class="name">{{ f.name }}</span>
          <span class="size num">{{ f.size_kb }} KB</span>
          <button
            class="del"
            type="button"
            :disabled="!!busy"
            title="删除"
            @click.stop="doDelete(f.name)"
          >
            删除
          </button>
        </li>
      </ul>
    </div>

    <!-- 重建 -->
    <div class="actions">
      <button class="btn" type="button" :disabled="!canReindex" @click="doReindex">
        <span v-if="busy === 'reindex'">重建中…可能要几十秒</span>
        <span v-else>重建索引</span>
      </button>
      <span class="tip">加了或删了语料后，必须重建才会生效</span>
    </div>
  </section>
</template>

<style scoped>
.corpus {
  background: var(--bg-raise);
  border: 1px solid var(--line);
  border-radius: var(--r-md);
  padding: 16px;
  margin-top: 16px;
}

.head {
  display: flex;
  align-items: baseline;
  gap: 10px;
  margin-bottom: 12px;
}

.label {
  font-family: var(--mono);
  font-size: 10.5px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--ink-faint);
}

.hint {
  font-size: 11.5px;
  color: var(--ink-faint);
}

/* ---- 拖放区 ---- */

.drop {
  border: 1px dashed var(--line-strong);
  border-radius: var(--r-sm);
  padding: 22px 16px;
  text-align: center;
  cursor: pointer;
  transition:
    border-color 0.15s ease,
    background 0.15s ease;
}

.drop:hover {
  border-color: var(--acc-line);
  background: var(--acc-wash);
}

.drop.busy {
  cursor: wait;
  opacity: 0.7;
}

.drop-main {
  font-size: 14px;
  color: var(--ink-soft);
}

.drop-sub {
  margin-top: 5px;
  font-size: 12px;
  color: var(--ink-faint);
}

/* ---- 提示条 ---- */

.msg {
  margin-top: 12px;
  padding: 10px 12px;
  border-radius: var(--r-sm);
  font-size: 13px;
  line-height: 1.6;
  border-left: 2px solid var(--line-strong);
  background: rgba(255, 255, 255, 0.02);
  color: var(--ink-soft);
}

.msg.success {
  border-left-color: var(--acc);
  color: var(--acc);
}

.msg.warning {
  border-left-color: var(--warn);
  color: var(--warn);
}

.msg.error {
  border-left-color: var(--danger);
  color: var(--danger);
}

/* ---- 文件列表 ---- */

.files {
  margin-top: 16px;
  padding-top: 14px;
  border-top: 1px solid var(--line);
}

.files-head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 8px;
}

.count {
  font-size: 11.5px;
  color: var(--ink-faint);
}

.empty {
  font-size: 13px;
  color: var(--ink-faint);
  padding: 12px 0;
}

.files ul {
  list-style: none;
  margin: 0;
  padding: 0;
}

.files li {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 0;
  border-bottom: 1px solid var(--line);
  font-size: 13px;
}

.files li:last-child {
  border-bottom: 0;
}

.kind {
  flex: none;
  font-family: var(--mono);
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 3px;
  border: 1px solid var(--line-strong);
  color: var(--ink-faint);
}

.kind.ok {
  color: var(--acc);
  border-color: var(--acc-line);
  background: var(--acc-wash);
}

.name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--ink-soft);
}

.size {
  flex: none;
  font-size: 11.5px;
  color: var(--ink-faint);
}

.del {
  flex: none;
  appearance: none;
  background: transparent;
  border: 1px solid var(--line-strong);
  border-radius: 4px;
  color: var(--ink-faint);
  font: inherit;
  font-size: 11.5px;
  padding: 2px 8px;
  cursor: pointer;
  transition:
    color 0.15s ease,
    border-color 0.15s ease;
}

.del:hover:not(:disabled) {
  color: var(--danger);
  border-color: var(--danger);
}

.del:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

/* ---- 重建 ---- */

.actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin-top: 14px;
  padding-top: 14px;
  border-top: 1px solid var(--line);
}

.btn {
  appearance: none;
  height: 38px;
  padding: 0 18px;
  border-radius: var(--r-sm);
  border: 1px solid var(--acc-line);
  background: var(--acc-wash);
  color: var(--acc);
  font: inherit;
  font-size: 13.5px;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
  transition: background 0.15s ease;
}

.btn:hover:not(:disabled) {
  background: rgba(52, 211, 153, 0.16);
}

.btn:active:not(:disabled) {
  transform: translateY(1px);
}

.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn:focus-visible {
  outline: 2px solid var(--acc);
  outline-offset: 2px;
}

.tip {
  font-size: 12px;
  color: var(--ink-faint);
}
</style>
