<script setup>
/**
 * 顶栏。
 * 约束：桌面端单行、高度 64px（skill 规定 ≤80px，大导航条会吃掉视口）。
 * 只放一个 CTA 意图（进入演示），全页不出现第二个同义按钮文案。
 */
import { onMounted, onBeforeUnmount, ref } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const scrolled = ref(false)

// 顶栏加背景只在滚动后发生，用 passive 监听 + rAF 节流。
// 这里用 scroll 监听是合理的例外：它只切一个布尔值，且 passive 不阻塞滚动。
let ticking = false
function onScroll() {
  if (ticking) return
  ticking = true
  requestAnimationFrame(() => {
    scrolled.value = window.scrollY > 12
    ticking = false
  })
}

onMounted(() => window.addEventListener('scroll', onScroll, { passive: true }))
onBeforeUnmount(() => window.removeEventListener('scroll', onScroll))
</script>

<template>
  <header class="nav" :class="{ 'is-scrolled': scrolled }">
    <div class="wrap nav-inner">
      <RouterLink to="/" class="brand" aria-label="返回首页">
        <span class="mark" aria-hidden="true">
          <svg viewBox="0 0 24 24" width="18" height="18" fill="none">
            <path
              d="M12 3 4 6v6.2c0 4.4 3.3 7.6 8 8.8 4.7-1.2 8-4.4 8-8.8V6l-8-3Z"
              stroke="currentColor"
              stroke-width="1.6"
              stroke-linejoin="round"
            />
            <path
              d="M9 12.2l2.1 2.1L15.4 10"
              stroke="currentColor"
              stroke-width="1.6"
              stroke-linecap="round"
              stroke-linejoin="round"
            />
          </svg>
        </span>
        <span class="wordmark">保险条款 RAG</span>
      </RouterLink>

      <nav class="links" aria-label="页面导航">
        <a href="#problem">问题</a>
        <a href="#pipeline">实现</a>
        <a href="#api">接口</a>
        <a href="#metrics">评测</a>
      </nav>

      <RouterLink to="/app" class="btn btn-primary nav-cta">进入演示</RouterLink>
    </div>
  </header>
</template>

<style scoped>
.nav {
  position: fixed;
  inset: 0 0 auto;
  z-index: 50;
  height: 64px;
  border-bottom: 1px solid transparent;
  transition:
    background 0.25s ease,
    border-color 0.25s ease,
    backdrop-filter 0.25s ease;
}

.nav.is-scrolled {
  background: rgba(11, 14, 17, 0.82);
  border-bottom-color: var(--line);
  backdrop-filter: blur(14px) saturate(160%);
}

.nav-inner {
  height: 100%;
  display: flex;
  align-items: center;
  gap: 24px;
}

.brand {
  display: flex;
  align-items: center;
  gap: 9px;
  flex: none;
}

.mark {
  width: 28px;
  height: 28px;
  display: grid;
  place-items: center;
  color: var(--acc);
  border: 1px solid var(--acc-line);
  border-radius: var(--r-sm);
  background: var(--acc-wash);
}

.wordmark {
  font-size: 14.5px;
  font-weight: 600;
  letter-spacing: -0.01em;
}

.links {
  display: flex;
  align-items: center;
  gap: 22px;
  margin-left: auto;
  font-size: 13.5px;
  color: var(--ink-mute);
}

.links a {
  transition: color 0.15s ease;
  white-space: nowrap;
}

.links a:hover {
  color: var(--ink);
}

.nav-cta {
  height: 36px;
  padding: 0 16px;
  font-size: 13.5px;
  flex: none;
}

/* 桌面用链接导航；窄屏收起为只留品牌和 CTA，
   避免导航换行（skill 硬规则：桌面端导航必须单行） */
@media (max-width: 860px) {
  .links {
    display: none;
  }
  .nav-cta {
    margin-left: auto;
  }
}
</style>
