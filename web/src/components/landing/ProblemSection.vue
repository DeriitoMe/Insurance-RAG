<script setup>
/**
 * 问题陈述。
 * 布局族：左右对照（非对称，左 5 右 6）。
 * 这一节不用卡片承载信息，用编号 + 排版分组，避免"什么都装进卡片"。
 */
const manual = [
  { t: '翻条款', d: '一份条款几十条，加上释义与附表，动辄上万字。' },
  { t: '找依据', d: '同一个结论往往写在保险责任、责任免除、等待期三处。' },
  { t: '判冲突', d: '通则与特别约定不一致时，以哪一条为准需要判断。' },
  { t: '留痕迹', d: '结论必须能回溯到具体条款，否则事后无法复核。' },
]

const system = [
  { t: '结构对齐', d: '按条款编号切分，每块自带产品与章节路径，检索不会串条。' },
  { t: '双路召回', d: '向量负责语义，关键词负责编号与数字，RRF 融合两路排名。' },
  { t: '聚合判断', d: '是否赔付类问题强制跨条款取证，不足即拒答，不猜。' },
]
</script>

<template>
  <section id="problem" class="sec">
    <div class="wrap">
      <div class="head reveal">
        <p class="label">问题</p>
        <h2 class="h2">难点不在模型，在取证</h2>
        <p class="lede">
          大模型本身读得懂条款。真正难的是让它在正确的条款上作答，
          并且在答不出时明确说答不出。
        </p>
      </div>

      <div class="split">
        <div class="col reveal">
          <p class="col-title">人工流程</p>
          <ol class="list manual">
            <li v-for="(m, i) in manual" :key="m.t">
              <span class="idx num">{{ String(i + 1).padStart(2, '0') }}</span>
              <div>
                <span class="t">{{ m.t }}</span>
                <span class="d">{{ m.d }}</span>
              </div>
            </li>
          </ol>
        </div>

        <div class="col reveal" data-reveal-delay="80">
          <p class="col-title accent">系统流程</p>
          <ol class="list system">
            <li v-for="s in system" :key="s.t">
              <span class="bar" aria-hidden="true"></span>
              <div>
                <span class="t">{{ s.t }}</span>
                <span class="d">{{ s.d }}</span>
              </div>
            </li>
          </ol>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.sec {
  padding: 88px 0;
  border-top: 1px solid var(--line);
}

.head {
  max-width: 660px;
  margin-bottom: 48px;
}

.head .label {
  margin-bottom: 14px;
}

.head .lede {
  margin-top: 16px;
}

/* 非对称：右列更宽，因为系统流程文字更长 */
.split {
  display: grid;
  grid-template-columns: minmax(0, 5fr) minmax(0, 6fr);
  gap: clamp(28px, 4vw, 56px);
  align-items: start;
}

.col-title {
  font-family: var(--mono);
  font-size: 11px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--ink-faint);
  padding-bottom: 14px;
  border-bottom: 1px solid var(--line);
  margin-bottom: 4px;
}

.col-title.accent {
  color: var(--acc);
  border-bottom-color: var(--acc-line);
}

.list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.list li {
  display: grid;
  grid-template-columns: 34px minmax(0, 1fr);
  gap: 14px;
  padding: 16px 0;
  border-bottom: 1px solid var(--line);
}

.list li:last-child {
  border-bottom: 0;
}

.idx {
  font-size: 12px;
  color: var(--ink-faint);
  padding-top: 3px;
}

.list .t {
  display: block;
  font-size: 14.5px;
  font-weight: 500;
}

.list .d {
  display: block;
  margin-top: 3px;
  font-size: 13px;
  line-height: 1.65;
  color: var(--ink-mute);
  max-width: 46ch;
}

/* 系统侧用一条竖线作为视觉锚点，代替图标 */
.list.system li {
  grid-template-columns: 3px minmax(0, 1fr);
  gap: 16px;
}

.bar {
  width: 3px;
  border-radius: var(--r-pill);
  background: var(--acc-dim);
  margin-top: 3px;
}

.list.system .t {
  color: var(--ink);
}

@media (max-width: 860px) {
  .split {
    grid-template-columns: 1fr;
    gap: 36px;
  }
  .sec {
    padding: 64px 0;
  }
  .head {
    margin-bottom: 32px;
  }
}
</style>
