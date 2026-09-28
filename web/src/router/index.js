import { createRouter, createWebHistory } from 'vue-router'

/**
 * 两个路由，职责分明：
 *   /     落地页  —— 解释这个系统是什么、凭什么可信、怎么跑起来
 *   /app  演示页  —— 真正的问答界面（就是之前那个 Vue3 应用）
 *
 * 分开而不是"一页塞下"的原因：落地页要的是**叙事节奏**（长滚动、分段），
 * 演示页要的是**工作区**（固定视口、不滚动）。塞进一页会互相打架。
 */
const routes = [
  {
    path: '/',
    name: 'landing',
    component: () => import('@/views/LandingView.vue'),
    meta: { title: '保险条款 RAG' },
  },
  {
    path: '/app',
    name: 'app',
    component: () => import('@/views/DemoView.vue'),
    meta: { title: '演示 · 保险条款 RAG' },
  },
  { path: '/:pathMatch(.*)*', redirect: '/' },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior(to, from, saved) {
    if (saved) return saved
    if (to.hash) return { el: to.hash, behavior: 'smooth', top: 80 }
    return { top: 0 }
  },
})

router.afterEach((to) => {
  if (to.meta?.title) document.title = to.meta.title
})

export default router
