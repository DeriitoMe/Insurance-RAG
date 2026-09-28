<script setup>
/**
 * 一条问答记录。
 *
 * 三种终态都要有视觉表达（skill 要求实现完整状态周期）：
 *   - 正常作答：正文 + 引用
 *   - 拒答（answerable = false）：正面展示，不是错误
 *   - 出错：红色提示
 */
import SourceList from '@/components/SourceList.vue'

defineProps({
  message: { type: Object, required: true },
})
</script>

<template>
  <article class="msg">
    <div class="q">
      <span class="qmark" aria-hidden="true">Q</span>
      <span>{{ message.question }}</span>
    </div>

    <div class="card">
      <div class="answer" :class="{ dim: message.streaming && !message.answer }">
        {{ message.answer }}
        <span v-if="message.streaming" class="caret" aria-hidden="true" />
      </div>

      <el-alert
        v-if="message.error"
        type="error"
        :title="message.error"
        show-icon
        :closable="false"
        style="margin-top: 12px"
      />

      <!-- 拒答是正确行为，用中性提示而不是错误样式 -->
      <el-alert
        v-else-if="message.answerable === false"
        type="info"
        show-icon
        :closable="false"
        title="条款中没有足够信息"
        description="系统按设计拒绝作答，而不是编造内容。这是可靠性指标，不是失败。"
        style="margin-top: 12px"
      />

      <SourceList
        :sources="message.sources"
        :citations="message.citations"
        :used-articles="message.usedArticles"
        :streaming="message.streaming"
      />

      <div v-if="message.meta" class="meta num">{{ message.meta }}</div>
    </div>
  </article>
</template>

<style scoped>
.msg {
  margin-top: 22px;
}

.q {
  display: flex;
  align-items: baseline;
  gap: 10px;
  font-weight: 600;
  font-size: 15px;
  margin-bottom: 11px;
}

.qmark {
  flex: none;
  font-family: var(--mono);
  font-size: 10.5px;
  color: var(--ink-faint);
  border: 1px solid var(--line-strong);
  border-radius: 4px;
  width: 18px;
  height: 18px;
  display: grid;
  place-items: center;
}

.card {
  background: var(--bg-raise);
  border: 1px solid var(--line);
  border-radius: var(--r-md);
  padding: 16px;
}

.answer {
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 14.5px;
  line-height: 1.8;
  min-height: 24px;
}

.answer.dim {
  color: var(--ink-faint);
}

.caret {
  display: inline-block;
  width: 7px;
  height: 16px;
  margin-left: 2px;
  background: var(--acc);
  vertical-align: text-bottom;
  animation: blink 1s steps(1) infinite;
}

@keyframes blink {
  50% {
    opacity: 0;
  }
}

.meta {
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px solid var(--line);
  font-size: 11.5px;
  color: var(--ink-faint);
}

@media (max-width: 720px) {
  .card {
    padding: 13px;
  }
}
</style>
