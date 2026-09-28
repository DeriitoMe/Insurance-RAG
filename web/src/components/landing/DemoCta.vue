<script setup>
/**
 * 结尾 CTA + 约束说明。
 *
 * skill 自检：
 *   - 全页 CTA 意图只有两个 —— "进入演示"（导航 / Hero / 这里）和 "看实现"（Hero，锚点）。
 *     "看实现"是页面内导航，不是同义意图，允许。
 *     所以这里仍然用"进入演示"，文案与其它位置完全一致。
 *   - 不使用 h-screen，用 min-h-[100dvh] 之类会跳动的写法一律避免
 */
const constraints = [
  { k: '只依据片段', d: '不得使用模型自身的保险知识，不得推测' },
  { k: '必须标注来源', d: '每条结论后附产品名与条款号' },
  { k: '无信息即拒答', d: '返回无法确定，并说明缺哪类信息' },
  { k: '赔付类多条款取证', d: '责任、免责、等待期、既往症需综合判断' },
]
</script>

<template>
  <section class="cta">
    <div class="wrap">
      <div class="box reveal">
        <div class="left">
          <p class="label">现在</p>
          <h2 class="h2">直接问它几个问题</h2>
          <p class="lede">
            演示页可以切换检索模式、限定产品、查看每个结论引用了哪一条。
            其中一个示例问题会触发拒答，那是最值得看的一条。
          </p>
          <div class="acts">
            <RouterLink to="/app" class="btn btn-primary">进入演示</RouterLink>
          </div>
        </div>

        <div class="right">
          <p class="col-title">生成层的四条硬约束</p>
          <ul class="cons">
            <li v-for="c in constraints" :key="c.k">
              <span class="ck">{{ c.k }}</span>
              <span class="cd">{{ c.d }}</span>
            </li>
          </ul>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.cta {
  padding: 88px 0 96px;
  border-top: 1px solid var(--line);
}

.box {
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) minmax(0, 1fr);
  gap: clamp(32px, 5vw, 64px);
  align-items: start;
  background: var(--bg-raise);
  border: 1px solid var(--line);
  border-radius: var(--r-md);
  padding: clamp(28px, 4vw, 44px);
}

.left .label {
  margin-bottom: 14px;
}

.left .lede {
  margin-top: 16px;
}

.acts {
  margin-top: 26px;
}

.col-title {
  font-family: var(--mono);
  font-size: 11px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--ink-faint);
  padding-bottom: 12px;
  border-bottom: 1px solid var(--line);
}

.cons {
  list-style: none;
  margin: 0;
  padding: 0;
}

.cons li {
  padding: 12px 0;
  border-bottom: 1px solid var(--line);
}

.cons li:last-child {
  border-bottom: 0;
}

.ck {
  display: block;
  font-size: 13.5px;
  font-weight: 500;
  color: var(--acc);
}

.cd {
  display: block;
  margin-top: 2px;
  font-size: 12.5px;
  line-height: 1.6;
  color: var(--ink-mute);
}

@media (max-width: 900px) {
  .box {
    grid-template-columns: 1fr;
    gap: 30px;
  }
  .cta {
    padding: 64px 0 72px;
  }
}
</style>
