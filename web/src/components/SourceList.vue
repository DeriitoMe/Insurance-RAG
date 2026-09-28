<script setup>
/**
 * 引用来源展示。
 *
 * 这是整个演示页最重要的组件 —— 可溯源就体现在这里。
 * 一个 AI 应用能不能被信任，取决于用户能不能一键核对它的依据。
 *
 * 两条渲染路径：
 *   - 流式中：显示 sources 事件给的检索片段（可能还不是最终引用）
 *   - 完成后：显示 final 事件给的正式引用（带原文 quotation）
 */
const props = defineProps({
  sources: { type: Array, default: () => [] },
  citations: { type: Array, default: () => [] },
  usedArticles: { type: Array, default: () => [] },
  streaming: { type: Boolean, default: false },
})

const hasContent = () =>
  props.citations.length > 0 || props.sources.length > 0
</script>

<template>
  <div v-if="hasContent()" class="sources">
    <div class="head">
      <span class="label">引用来源</span>
      <span v-if="usedArticles.length" class="pill ok">依据 {{ usedArticles.join('、') }}</span>
      <span v-else-if="streaming" class="pill">检索中</span>
    </div>

    <!-- 正式引用（带原文） -->
    <template v-if="citations.length">
      <div v-for="(c, i) in citations" :key="i" class="item">
        <div class="labelrow">
          <span class="idx num">{{ i + 1 }}</span>
          <span class="name">{{ c.label || `${c.product_name} ${c.article_no}` }}</span>
        </div>
        <blockquote v-if="c.quote" class="quote">{{ c.quote }}</blockquote>
      </div>
    </template>

    <!-- 检索阶段来源（生成完成前的预览） -->
    <template v-else>
      <div v-for="(s, i) in sources" :key="i" class="item">
        <div class="labelrow">
          <span class="idx num">{{ i + 1 }}</span>
          <span class="name">{{ s.label }}</span>
        </div>
        <p v-if="s.preview" class="preview">{{ s.preview }}…</p>
      </div>
    </template>
  </div>
</template>

<style scoped>
.sources {
  margin-top: 14px;
  padding: 14px 16px;
  background: var(--bg-sunken);
  border: 1px solid var(--line);
  border-radius: var(--r-md);
}

.head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}

.pill {
  font-family: var(--mono);
  font-size: 10.5px;
  letter-spacing: 0.06em;
  color: var(--ink-faint);
  padding: 1px 8px;
  border: 1px solid var(--line);
  border-radius: var(--r-pill);
}

.pill.ok {
  color: var(--acc);
  border-color: var(--acc-line);
}

.item {
  padding: 9px 0;
  border-bottom: 1px solid var(--line);
}

.item:last-child {
  border-bottom: none;
  padding-bottom: 0;
}

.labelrow {
  display: flex;
  align-items: baseline;
  gap: 9px;
}

.idx {
  flex: none;
  width: 17px;
  height: 17px;
  border-radius: 4px;
  background: var(--acc-wash);
  color: var(--acc);
  font-size: 10.5px;
  display: grid;
  place-items: center;
}

.name {
  color: var(--acc);
  font-weight: 600;
  font-size: 13.5px;
}

.quote {
  margin: 7px 0 0 26px;
  padding-left: 11px;
  border-left: 2px solid var(--line-strong);
  color: var(--ink-soft);
  font-size: 13px;
  line-height: 1.7;
}

.preview {
  margin: 5px 0 0 26px;
  color: var(--ink-mute);
  font-size: 12.5px;
  line-height: 1.6;
}
</style>
