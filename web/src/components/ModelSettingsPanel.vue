<script setup>
import { onMounted, reactive, ref } from 'vue'

const emit = defineEmits(['saved'])

const draft = reactive({
  embedding_provider: 'hash',
  embedding_api_base: 'https://api.siliconflow.cn/v1',
  embedding_api_key: '',
  embedding_api_key_configured: false,
  embedding_model: 'BAAI/bge-m3',
  clear_embedding_key: false,
  llm_provider: 'mock',
  llm_api_base: 'https://api.deepseek.com/v1',
  llm_api_key: '',
  llm_api_key_configured: false,
  llm_model: 'deepseek-chat',
  clear_llm_key: false,
})

const loading = ref(true)
const saving = ref(false)
const error = ref('')
const message = ref('')
const reindexRequired = ref(false)

async function loadSettings() {
  loading.value = true
  error.value = ''
  try {
    const response = await fetch('/api/settings')
    const data = await response.json()
    if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`)
    Object.assign(draft, data)
  } catch (e) {
    error.value = `读取模型配置失败：${e.message}`
  } finally {
    loading.value = false
  }
}

async function saveSettings() {
  saving.value = true
  error.value = ''
  message.value = ''
  reindexRequired.value = false
  try {
    const response = await fetch('/api/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json; charset=utf-8' },
      body: JSON.stringify(draft),
    })
    const data = await response.json()
    if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`)
    draft.embedding_api_key = ''
    draft.llm_api_key = ''
    draft.clear_embedding_key = false
    draft.clear_llm_key = false
    draft.embedding_api_key_configured = data.embedding_api_key_configured
    draft.llm_api_key_configured = data.llm_api_key_configured
    reindexRequired.value = data.embedding_reindex_required
    message.value = '配置已保存并应用到当前服务。'
    emit('saved', data)
  } catch (e) {
    error.value = `保存失败：${e.message}`
  } finally {
    saving.value = false
  }
}

onMounted(loadSettings)
</script>

<template>
  <section class="model-panel" aria-labelledby="model-panel-title">
    <div class="panel-head">
      <div>
        <p class="eyebrow">LOCAL MODEL CONFIGURATION</p>
        <h2 id="model-panel-title">模型设置</h2>
        <p class="intro">填写兼容 OpenAI API 的地址、模型名和密钥，让问答使用真实模型。</p>
      </div>
      <span class="local-badge">仅本机</span>
    </div>

    <p class="privacy-note">
      密钥会写入本机忽略文件（本地运行写入 <code>.env</code>，Docker 写入 <code>.runtime/settings.env</code>），不会回显到网页，也不会进入 Git。
      这个设置接口只允许本机访问；远程 Docker 部署请配置服务器的 <code>.runtime/settings.env</code>。
    </p>

    <div v-if="loading" class="state">正在读取当前配置…</div>
    <form v-else class="settings-form" @submit.prevent="saveSettings">
      <section class="model-block">
        <div class="block-title">
          <div>
            <span class="step">01</span>
            <h3>Embedding 向量模型</h3>
          </div>
          <span class="key-state" :class="{ ready: draft.embedding_api_key_configured }">
            {{ draft.embedding_api_key_configured ? '密钥已保存' : '尚未配置密钥' }}
          </span>
        </div>

        <div class="fields">
          <label class="field">
            <span>运行方式</span>
            <select v-model="draft.embedding_provider">
              <option value="hash">离线演示（hash）</option>
              <option value="api">API 服务</option>
              <option value="local">本地模型</option>
            </select>
          </label>
          <label class="field">
            <span>模型名称</span>
            <input v-model="draft.embedding_model" required maxlength="200" placeholder="BAAI/bge-m3" />
          </label>
          <label class="field full">
            <span>API 地址</span>
            <input v-model="draft.embedding_api_base" required type="url" maxlength="2048" placeholder="https://api.siliconflow.cn/v1" />
          </label>
          <label class="field full">
            <span>API Key</span>
            <input
              v-model="draft.embedding_api_key"
              type="password"
              autocomplete="new-password"
              maxlength="4096"
              :placeholder="draft.embedding_api_key_configured ? '已保存；留空表示保持现有密钥' : '粘贴 Embedding API Key'"
              @input="draft.clear_embedding_key = false"
            />
          </label>
          <label v-if="draft.embedding_api_key_configured" class="clear-key">
            <input v-model="draft.clear_embedding_key" type="checkbox" />
            清除已保存的 Embedding 密钥
          </label>
        </div>
      </section>

      <section class="model-block">
        <div class="block-title">
          <div>
            <span class="step">02</span>
            <h3>LLM 对话模型</h3>
          </div>
          <span class="key-state" :class="{ ready: draft.llm_api_key_configured }">
            {{ draft.llm_api_key_configured ? '密钥已保存' : '尚未配置密钥' }}
          </span>
        </div>

        <div class="fields">
          <label class="field">
            <span>运行方式</span>
            <select v-model="draft.llm_provider">
              <option value="mock">离线演示（mock）</option>
              <option value="api">API 服务</option>
            </select>
          </label>
          <label class="field">
            <span>模型名称</span>
            <input v-model="draft.llm_model" required maxlength="200" placeholder="deepseek-chat" />
          </label>
          <label class="field full">
            <span>API 地址</span>
            <input v-model="draft.llm_api_base" required type="url" maxlength="2048" placeholder="https://api.deepseek.com/v1" />
          </label>
          <label class="field full">
            <span>API Key</span>
            <input
              v-model="draft.llm_api_key"
              type="password"
              autocomplete="new-password"
              maxlength="4096"
              :placeholder="draft.llm_api_key_configured ? '已保存；留空表示保持现有密钥' : '粘贴 LLM API Key'"
              @input="draft.clear_llm_key = false"
            />
          </label>
          <label v-if="draft.llm_api_key_configured" class="clear-key">
            <input v-model="draft.clear_llm_key" type="checkbox" />
            清除已保存的 LLM 密钥
          </label>
        </div>
      </section>

      <div class="form-foot">
        <div class="feedback" aria-live="polite">
          <p v-if="error" class="error">{{ error }}</p>
          <p v-else-if="message" class="success">{{ message }}</p>
          <p v-if="reindexRequired" class="reindex-hint">
            Embedding 配置已变更。请打开「管理语料」并重建索引后再提问。
          </p>
        </div>
        <button class="save-btn" type="submit" :disabled="saving">
          {{ saving ? '保存中…' : '保存并应用' }}
        </button>
      </div>
    </form>
  </section>
</template>

<style scoped>
.model-panel {
  margin: 0 0 18px;
  padding: 24px;
  border: 1px solid var(--line-strong);
  border-radius: var(--r-md);
  background: linear-gradient(145deg, rgba(20, 27, 33, 0.98), rgba(13, 17, 21, 0.98));
}

.panel-head,
.block-title,
.form-foot {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
}

.eyebrow,
.step {
  color: var(--acc);
  font-family: var(--mono);
  font-size: 10px;
  letter-spacing: 0.12em;
}

.panel-head h2 {
  margin-top: 3px;
  font-size: 20px;
}

.intro,
.privacy-note {
  margin-top: 7px;
  color: var(--ink-mute);
  font-size: 12px;
}

.local-badge {
  padding: 3px 9px;
  border: 1px solid var(--acc-line);
  border-radius: var(--r-pill);
  color: var(--acc);
  font-size: 11px;
  white-space: nowrap;
}

.privacy-note {
  margin: 18px 0 0;
  padding: 10px 12px;
  border-left: 2px solid var(--acc-dim);
  background: var(--acc-wash);
  line-height: 1.65;
}

.privacy-note code {
  color: var(--ink-soft);
}

.settings-form {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
  margin-top: 16px;
}

.model-block {
  padding: 16px;
  border: 1px solid var(--line);
  border-radius: var(--r-sm);
  background: rgba(7, 9, 11, 0.42);
}

.block-title > div {
  display: flex;
  align-items: center;
  gap: 9px;
}

.block-title h3 {
  font-size: 13px;
  letter-spacing: 0;
}

.key-state {
  color: var(--ink-faint);
  font-size: 10px;
  white-space: nowrap;
}

.key-state.ready {
  color: var(--acc);
}

.fields {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin-top: 16px;
}

.field {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 5px;
  color: var(--ink-mute);
  font-size: 11px;
}

.field.full,
.clear-key {
  grid-column: 1 / -1;
}

.field input,
.field select {
  width: 100%;
  height: 36px;
  padding: 0 10px;
  border: 1px solid var(--line-strong);
  border-radius: var(--r-sm);
  background: var(--bg-sunken);
  color: var(--ink);
  font: inherit;
  font-size: 12px;
  outline: none;
}

.field input:focus,
.field select:focus {
  border-color: var(--acc-dim);
  box-shadow: 0 0 0 2px var(--acc-wash);
}

.field input::placeholder {
  color: var(--ink-faint);
}

.clear-key {
  display: flex;
  align-items: center;
  gap: 7px;
  color: var(--ink-mute);
  font-size: 11px;
}

.clear-key input {
  accent-color: var(--acc);
}

.form-foot {
  grid-column: 1 / -1;
  align-items: flex-end;
  min-height: 42px;
}

.feedback {
  color: var(--ink-mute);
  font-size: 11px;
}

.success {
  color: var(--acc);
}

.error {
  color: var(--danger);
}

.reindex-hint {
  margin-top: 3px;
  color: var(--warn);
}

.save-btn {
  min-width: 126px;
  height: 36px;
  padding: 0 14px;
  border: 1px solid var(--acc-dim);
  border-radius: var(--r-sm);
  background: var(--acc-wash);
  color: var(--acc);
  font: inherit;
  font-size: 12px;
  cursor: pointer;
}

.save-btn:disabled {
  cursor: wait;
  opacity: 0.65;
}

.state {
  margin-top: 16px;
  color: var(--ink-mute);
  font-size: 12px;
}

@media (max-width: 760px) {
  .model-panel {
    padding: 17px;
  }
  .settings-form {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 460px) {
  .fields {
    grid-template-columns: 1fr;
  }
  .field.full,
  .clear-key {
    grid-column: auto;
  }
  .block-title {
    align-items: flex-start;
    flex-direction: column;
    gap: 6px;
  }
  .form-foot {
    align-items: stretch;
    flex-direction: column;
  }
}
</style>
