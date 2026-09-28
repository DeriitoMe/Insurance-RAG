<script setup>
/**
 * 提问面板：输入框 + 检索参数 + 示例问题。
 *
 * 把"检索模式"和"召回数量"暴露给用户，看起来是产品功能，
 * 实际上是**调试入口** —— 调参时不用改代码重启服务。
 * 这也是评测脚本之外最实用的验证手段。
 */
import { ref } from 'vue'

const props = defineProps({
  products: { type: Array, default: () => [] },
  options: { type: Object, required: true },
  streaming: { type: Boolean, default: false },
})

const emit = defineEmits(['ask', 'abort'])

const question = ref('')

const examples = [
  '疾病住院的等待期是多少天？',
  '甲状腺结节能赔吗？',
  '安心保和康健人生哪款对结节更友好？',
  '投保前有症状但没诊断，之后确诊能赔吗？',
  '这款产品的保费是多少钱？',
]

function submit() {
  const q = question.value.trim()
  if (!q || props.streaming) return
  emit('ask', q)
  question.value = ''
}

function useExample(text) {
  question.value = text
  submit()
}
</script>

<template>
  <section class="panel">
    <div class="row">
      <el-input
        v-model="question"
        size="large"
        placeholder="例如：甲状腺结节能赔吗？"
        :disabled="streaming"
        clearable
        @keyup.enter="submit"
      />
      <el-button
        v-if="!streaming"
        type="primary"
        size="large"
        :disabled="!question.trim()"
        @click="submit"
      >
        提问
      </el-button>
      <el-button v-else type="danger" size="large" plain @click="emit('abort')">
        停止
      </el-button>
    </div>

    <div class="params">
      <span class="plabel">检索模式</span>
      <el-radio-group v-model="options.mode" size="small" :disabled="streaming">
        <el-radio-button value="hybrid">混合</el-radio-button>
        <el-radio-button value="vector">向量</el-radio-button>
        <el-radio-button value="keyword">关键词</el-radio-button>
      </el-radio-group>

      <span class="plabel">送模型条款数</span>
      <el-input-number
        v-model="options.topN"
        :min="1"
        :max="20"
        size="small"
        controls-position="right"
        style="width: 104px"
        :disabled="streaming"
      />

      <template v-if="products.length">
        <span class="plabel">限定产品</span>
        <el-select
          v-model="options.docIds"
          multiple
          collapse-tags
          collapse-tags-tooltip
          placeholder="全部"
          size="small"
          style="min-width: 210px"
          :disabled="streaming"
        >
          <el-option
            v-for="p in products"
            :key="p.doc_id"
            :label="p.product_name"
            :value="p.doc_id"
          />
        </el-select>
      </template>
    </div>

    <div class="examples">
      <button
        v-for="e in examples"
        :key="e"
        type="button"
        class="chip"
        :disabled="streaming"
        @click="useExample(e)"
      >
        {{ e }}
      </button>
    </div>
  </section>
</template>

<style scoped>
.panel {
  background: var(--bg-raise);
  border: 1px solid var(--line);
  border-radius: var(--r-md);
  padding: 16px;
}

.row {
  display: flex;
  gap: 10px;
}

.params {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-top: 14px;
  padding-top: 14px;
  border-top: 1px solid var(--line);
}

.plabel {
  font-family: var(--mono);
  font-size: 10.5px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--ink-faint);
}

.examples {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 14px;
}

.chip {
  appearance: none;
  font: inherit;
  font-size: 12.5px;
  padding: 5px 11px;
  border-radius: var(--r-pill);
  background: transparent;
  border: 1px solid var(--line-strong);
  color: var(--ink-mute);
  cursor: pointer;
  transition:
    color 0.15s ease,
    border-color 0.15s ease;
}

.chip:hover:not(:disabled) {
  color: var(--acc);
  border-color: var(--acc-line);
}

.chip:active:not(:disabled) {
  transform: translateY(1px);
}

.chip:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.chip:focus-visible {
  outline: 2px solid var(--acc);
  outline-offset: 2px;
}

@media (max-width: 720px) {
  .row {
    flex-direction: column;
  }
}
</style>
