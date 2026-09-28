<script setup>
/**
 * 页脚。
 *
 * skill 自检：不放版本号、不放构建号、不放"v1.4.2"这类页脚。
 * 只保留技术栈、仓库入口和不夸大的说明。
 */
const stack = ['Python', 'FastAPI', 'Vue 3', 'Vite', 'Element Plus', 'numpy', 'jieba']
const year = new Date().getFullYear()
</script>

<template>
  <footer class="ft">
    <div class="wrap">
      <div class="top">
        <div class="brandcol">
          <p class="nm">保险条款 RAG</p>
          <p class="dc">
            条款问答、跨条款聚合与引用溯源。示例语料为合成数据，
            向量与生成模型处于占位配置，评测基线不构成效果结论。
          </p>
        </div>

        <div class="linkscol">
          <p class="col-title">页面</p>
          <RouterLink to="/">首页</RouterLink>
          <RouterLink to="/app">进入演示</RouterLink>
          <a href="#metrics">评测详情</a>
        </div>

        <div class="linkscol">
          <p class="col-title">技术栈</p>
          <span class="mono stack">{{ stack.join(' · ') }}</span>
        </div>
      </div>

      <div class="bottom">
        <span class="mono">MIT · {{ year }}</span>
        <span class="mono">条款语料请自行确认来源合法性，商用前需确认授权</span>
      </div>
    </div>
  </footer>
</template>

<style scoped>
.ft {
  border-top: 1px solid var(--line);
  padding: 56px 0 40px;
  background: var(--bg-sunken);
}

.top {
  display: grid;
  grid-template-columns: minmax(0, 1.6fr) minmax(0, 1fr) minmax(0, 1.2fr);
  gap: clamp(24px, 4vw, 48px);
  padding-bottom: 32px;
  border-bottom: 1px solid var(--line);
}

.nm {
  font-size: 15px;
  font-weight: 600;
}

.dc {
  margin-top: 8px;
  font-size: 12.5px;
  line-height: 1.7;
  color: var(--ink-mute);
  max-width: 46ch;
}

.col-title {
  font-family: var(--mono);
  font-size: 10.5px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--ink-faint);
  margin-bottom: 12px;
}

.linkscol {
  display: flex;
  flex-direction: column;
  gap: 8px;
  font-size: 13px;
}

.linkscol a {
  color: var(--ink-soft);
  width: fit-content;
  transition: color 0.15s ease;
}

.linkscol a:hover {
  color: var(--acc);
}

.stack {
  font-size: 12px;
  line-height: 1.8;
  color: var(--ink-mute);
  word-break: break-word;
}

.bottom {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
  padding-top: 22px;
  font-size: 11.5px;
  color: var(--ink-faint);
}

@media (max-width: 860px) {
  .top {
    grid-template-columns: 1fr;
    gap: 28px;
  }
}
</style>
