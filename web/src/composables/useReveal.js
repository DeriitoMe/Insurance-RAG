/**
 * 入场动效：基于 IntersectionObserver，不用 window.addEventListener('scroll')。
 *
 * 为什么不用 scroll 事件：滚动回调在主线程高频触发，会让长页面的 INP 变差。
 * IntersectionObserver 由浏览器在合成线程调度，零主线程开销。
 *
 * 用法：
 *   const { observe } = useReveal()
 *   onMounted(() => observe(rootEl.value))
 * 或直接给容器加 data-reveal 属性，observe() 会一次性接管所有子元素。
 */
import { onBeforeUnmount, onMounted } from 'vue'

export function useReveal() {
  let observer = null

  function setup(root) {
    if (!root) return

    const targets = root.querySelectorAll('.reveal')
    if (!targets.length) return

    // 尊重系统偏好：用户要减动效，就直接全部显示
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    if (reduce) {
      targets.forEach((el) => el.classList.add('is-in'))
      return
    }

    observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (!entry.isIntersecting) continue
          // stagger：同一批进入视口的元素依次错开，制造阅读节奏
          const delay = Number(entry.target.dataset.revealDelay || 0)
          window.setTimeout(() => entry.target.classList.add('is-in'), delay)
          observer.unobserve(entry.target) // 只播一次
        }
      },
      { rootMargin: '0px 0px -8% 0px', threshold: 0.12 },
    )

    targets.forEach((el) => observer.observe(el))
  }

  onMounted(() => {
    // 等一帧，确保子组件已挂载
    requestAnimationFrame(() => setup(document.querySelector('main, #app')))
  })

  onBeforeUnmount(() => {
    observer?.disconnect()
    observer = null
  })

  return { setup }
}
