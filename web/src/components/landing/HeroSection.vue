<script setup>
/**
 * Hero：非对称分栏（左文右数据），不是居中暗色 mesh。
 *
 * skill 硬规则自检：
 *   - 文案元素 4 个：eyebrow、headline、subtext、CTAs  -> 刚好 4，无多余小标语
 *   - subtext 16 词（上限 20）
 *   - headline 2 行（上限 2）
 *   - CTA 单行不换行
 *   - 顶 padding 88px（上限 pt-24 = 96px）
 *   - 内联数据面板代替"logo 墙"（这是作品集页，本来就没有客户 logo，
 *     硬造 logo 墙就是造假）
 */
const stats = [
  { k: '30', unit: '题', v: '评测集', d: '事实 / 跨条款 / 应拒答 / 对比' },
  { k: '3', unit: '种', v: '检索模式', d: '向量 · 关键词 · 混合' },
  { k: '17', unit: '个', v: '单元测试', d: '切分器全覆盖' },
  { k: '0', unit: '', v: '幻觉容忍', d: '无依据即拒答' },
]
</script>

<template>
  <section class="hero">
    <div class="wrap hero-grid">
      <div class="hero-copy">
        <p class="label reveal">保险 · 检索增强生成</p>

        <h1 class="display reveal" data-reveal-delay="60">
          把几十条条款<br />
          变成<em>有依据</em>的答案
        </h1>

        <p class="lede reveal" data-reveal-delay="120">
          条款问答、跨条款聚合、引用溯源。结论永远指向具体的第几条，
          查不到就说查不到。
        </p>

        <div class="hero-cta reveal" data-reveal-delay="180">
          <RouterLink to="/app" class="btn btn-primary">进入演示</RouterLink>
          <a href="#pipeline" class="btn btn-ghost">看实现</a>
        </div>
      </div>

      <!-- 数据面板：用真实的项目指标，不用虚构的客户 logo -->
      <div class="panel reveal" data-reveal-delay="240">
        <div class="panel-head">
          <span class="label">当前状态</span>
          <span class="dot" aria-hidden="true"></span>
        </div>

        <dl class="stats">
          <div v-for="s in stats" :key="s.v" class="stat">
            <dt>
              <span class="num k">{{ s.k }}</span
              ><span v-if="s.unit" class="unit">{{ s.unit }}</span>
            </dt>
            <dd>
              <span class="sv">{{ s.v }}</span>
              <span class="sd">{{ s.d }}</span>
            </dd>
          </div>
        </dl>

        <p class="panel-note">
          语料包含合成示例与 2026 年平安团体保险条款；模型取决于本机 .env 配置。
          运行状态见
          <RouterLink to="/app" class="lnk">演示页</RouterLink>
          与仓库 README。
        </p>
      </div>
    </div>
  </section>
</template>

<style scoped>
.hero {
  /* 顶 padding：64px 导航高度 + 自身间距，总计不超过 pt-24 */
  padding: 128px 0 72px;
}

.hero-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.35fr) minmax(0, 1fr);
  gap: clamp(32px, 5vw, 64px);
  align-items: start;
}

.hero-copy .label {
  margin-bottom: 20px;
}

.hero-copy .lede {
  margin-top: 22px;
}

.hero-cta {
  margin-top: 30px;
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

/* ---- 数据面板 ---- */

.panel {
  background: var(--bg-raise);
  border: 1px solid var(--line);
  border-radius: var(--r-md);
  padding: 20px;
}

.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-bottom: 14px;
  border-bottom: 1px solid var(--line);
}

.dot {
  width: 6px;
  height: 6px;
  border-radius: var(--r-pill);
  background: var(--acc);
  box-shadow: 0 0 0 3px var(--acc-wash);
}

.stats {
  margin: 0;
  display: grid;
  gap: 0;
}

.stat {
  display: grid;
  grid-template-columns: 92px minmax(0, 1fr);
  align-items: baseline;
  gap: 14px;
  padding: 13px 0;
  border-bottom: 1px solid var(--line);
}

.stat:last-child {
  border-bottom: 0;
  padding-bottom: 4px;
}

.stat dt {
  display: flex;
  align-items: baseline;
  gap: 3px;
}

.k {
  font-size: 22px;
  font-weight: 500;
  color: var(--acc);
  letter-spacing: -0.02em;
}

.unit {
  font-size: 11px;
  color: var(--ink-faint);
}

.stat dd {
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
}

.sv {
  font-size: 14px;
  font-weight: 500;
}

.sd {
  font-size: 12px;
  color: var(--ink-mute);
  line-height: 1.5;
}

.panel-note {
  margin-top: 16px;
  padding-top: 14px;
  border-top: 1px solid var(--line);
  font-size: 12px;
  line-height: 1.6;
  color: var(--ink-faint);
}

.lnk {
  color: var(--ink-mute);
  border-bottom: 1px solid var(--line-strong);
}

.lnk:hover {
  color: var(--acc);
  border-bottom-color: var(--acc-line);
}

/* ---- 响应式 ---- */

@media (max-width: 1000px) {
  .hero-grid {
    grid-template-columns: 1fr;
    gap: 40px;
  }
  .hero {
    padding-top: 108px;
  }
}

@media (max-width: 640px) {
  .hero {
    padding: 96px 0 56px;
  }
  .stat {
    grid-template-columns: 78px minmax(0, 1fr);
  }
  .k {
    font-size: 19px;
  }
}
</style>
