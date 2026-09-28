<script setup>
/**
 * 落地页组装。
 *
 * 节序（叙事：问题 -> 实现 -> 接口 -> 评测 -> 行动）：
 *   1 Hero        非对称分栏（左文右数据）
 *   2 Problem     左右对照 + 编号列表
 *   3 Pipeline    粘性左标题 + 右侧纵向五段
 *   4 Api         标签页 + 代码面板
 *   5 Metrics     数据表 + 无效判定块 + 右侧清单
 *   6 DemoCta     单卡片内两栏
 *
 * 六个节用了六种不同的布局族，没有重复。
 * 全页只有一套圆角（6 / 12 / 胶囊仅标签）、一个强调色、一个主题。
 */
import { useReveal } from '@/composables/useReveal'

import SiteNav from '@/components/landing/SiteNav.vue'
import HeroSection from '@/components/landing/HeroSection.vue'
import ProblemSection from '@/components/landing/ProblemSection.vue'
import PipelineSection from '@/components/landing/PipelineSection.vue'
import ApiSection from '@/components/landing/ApiSection.vue'
import MetricsSection from '@/components/landing/MetricsSection.vue'
import DemoCta from '@/components/landing/DemoCta.vue'
import SiteFooter from '@/components/landing/SiteFooter.vue'

// 统一接管所有 .reveal 元素的入场时机
useReveal()
</script>

<template>
  <div class="landing">
    <SiteNav />
    <main>
      <HeroSection />
      <ProblemSection />
      <PipelineSection />
      <ApiSection />
      <MetricsSection />
      <DemoCta />
    </main>
    <SiteFooter />
  </div>
</template>

<style scoped>
.landing {
  min-height: 100dvh;
  /* 一层极淡的顶光，只为了给纯黑背景一点空间感。
     不用 mesh 渐变、不用彩色光斑 —— 那是 AI 默认款。 */
  background:
    radial-gradient(120% 60% at 50% -10%, rgba(52, 211, 153, 0.05), transparent 60%),
    var(--bg);
}
</style>
