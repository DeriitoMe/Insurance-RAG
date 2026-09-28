<script setup>
/**
 * 实现链路：粘性左标题 + 右侧五段。
 *
 * 布局族与其它节都不同（其它是左右对照 / 分栏 / 表格 / 单列）。
 * 左侧用 position: sticky 固定，右侧滚动时形成"说明书"阅读感。
 * 粘性是纯 CSS，没有 JS 滚动劫持，也没有 GSAP pin。
 *
 * ⚠️ 注意：这里刻意**不写自造 SVG 图标**。
 * 需要视觉锚点时用编号与竖线，不用画的图标。
 */
const stages = [
  {
    n: '01',
    t: '解析',
    d: '将条款 PDF 或结构化 JSON 载入，重建层级树。',
    points: [
      '标题识别区分 部分 / 章 / 条 / 数字编号',
      '列表项不作为切分边界，避免丢主语',
      '页眉页脚过滤，去掉每页重复的高频噪声',
    ],
    tag: 'pypdf · 自研标题识别',
  },
  {
    n: '02',
    t: '切分',
    d: '以「条」为最小完整单元，不按固定字数切。',
    points: [
      '固定字数会把等待期与保险责任切进不同的块',
      '每块头部注入产品与章节路径，补回结构信息',
      '超 800 字按列表项二次切，不足 60 字与相邻同级合并',
    ],
    tag: '层次感知 · 800 / 60 / 分离',
  },
  {
    n: '03',
    t: '索引',
    d: '双索引并行：向量表 + BM25 倒排表。',
    points: [
      '向量表用 numpy 暴力检索，千级语料下耗时低于毫秒',
      '关键词表自写 BM25，中文走 jieba 切词，少一个依赖',
      '索引文件记录向量模型签名，换模型不匹配直接报错',
    ],
    tag: 'numpy · 自写 BM25 · 签名校验',
  },
  {
    n: '04',
    t: '检索',
    d: '两路召回后用 RRF 融合，可选重排序。',
    points: [
      '向量擅长同义表达，弱于编号与数字的精确匹配',
      'BM25 相反，两者互补而非替代',
      'RRF 只用排名不用分数，绕开两路分数量纲不同的问题',
    ],
    tag: 'RRF k=60 · 混合检索',
  },
  {
    n: '05',
    t: '生成',
    d: '约束输出形状，校验失败则重试，仍失败则降级。',
    points: [
      '提示词四条硬约束：只依据片段、必须标注来源、无信息即拒答、赔付类多条款取证',
      '要求返回 JSON，用 Pydantic 强校验，不信任模型输出',
      '引用与正文分两条 SSE 消息传输，前端不必解析半截 JSON',
    ],
    tag: 'JSON Schema · 重试 · 降级',
  },
]
</script>

<template>
  <section id="pipeline" class="sec">
    <div class="wrap grid">
      <div class="aside">
        <p class="label reveal">实现</p>
        <h2 class="h2 reveal" data-reveal-delay="60">五个阶段，<br />每步都有取舍</h2>
        <p class="lede reveal" data-reveal-delay="120">
          链路是常规 RAG 的形状。真正决定效果的是切分与检索这两步，
          所以它们的细节写得比其他三步长。
        </p>
      </div>

      <ol class="stages">
        <li v-for="(s, i) in stages" :key="s.n" class="stage reveal" :data-reveal-delay="i * 40">
          <div class="stage-head">
            <span class="n num">{{ s.n }}</span>
            <h3 class="st">{{ s.t }}</h3>
            <span class="tag mono">{{ s.tag }}</span>
          </div>
          <p class="sd">{{ s.d }}</p>
          <ul class="pts">
            <li v-for="p in s.points" :key="p">{{ p }}</li>
          </ul>
        </li>
      </ol>
    </div>
  </section>
</template>

<style scoped>
.sec {
  padding: 88px 0;
  border-top: 1px solid var(--line);
}

.grid {
  display: grid;
  grid-template-columns: minmax(0, 340px) minmax(0, 1fr);
  gap: clamp(32px, 5vw, 72px);
  align-items: start;
}

.aside {
  position: sticky;
  top: 104px;
}

.aside .label {
  margin-bottom: 14px;
}

.aside .lede {
  margin-top: 16px;
  font-size: 14.5px;
}

.stages {
  list-style: none;
  margin: 0;
  padding: 0;
}

.stage {
  padding: 24px 0 26px;
  border-top: 1px solid var(--line);
}

.stage:first-child {
  border-top: 0;
  padding-top: 0;
}

.stage-head {
  display: flex;
  align-items: baseline;
  gap: 12px;
  flex-wrap: wrap;
}

.n {
  font-size: 12px;
  color: var(--acc);
}

.st {
  font-size: 17px;
  letter-spacing: -0.01em;
}

.tag {
  font-size: 11px;
  color: var(--ink-faint);
  padding: 2px 8px;
  border: 1px solid var(--line);
  border-radius: var(--r-pill);
}

.sd {
  margin-top: 8px;
  font-size: 14px;
  color: var(--ink-soft);
  max-width: 58ch;
}

.pts {
  margin: 12px 0 0;
  padding: 0;
  list-style: none;
  display: grid;
  gap: 7px;
}

.pts li {
  position: relative;
  padding-left: 16px;
  font-size: 13px;
  line-height: 1.65;
  color: var(--ink-mute);
  max-width: 62ch;
}

/* 用一条短横线做项目符号，不用图标 */
.pts li::before {
  content: '';
  position: absolute;
  left: 0;
  top: 10px;
  width: 7px;
  height: 1px;
  background: var(--line-strong);
}

@media (max-width: 960px) {
  .grid {
    grid-template-columns: 1fr;
    gap: 32px;
  }
  .aside {
    position: static;
  }
  .sec {
    padding: 64px 0;
  }
}
</style>
