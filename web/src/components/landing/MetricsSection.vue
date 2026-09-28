<script setup>
/**
 * 评测节。
 *
 * 这一节的核心不是"我指标多好"，而是**主动说明指标为什么不成立**。
 * 对技术读者来说，一个敢标自己数据无效的项目，可信度远高于一堆漂亮数字。
 * 所以这节的信息层级是：先给数据，紧接着给无效判定，再给待做实验。
 *
 * 这是全页唯一信任敏感的位置，所以在数据表下方用了 warning 色的提示块。
 */
const rows = [
  { mode: 'vector', hr: '100.00%', mrr: '0.8584', full: '100.00%' },
  { mode: 'keyword', hr: '100.00%', mrr: '0.9583', full: '100.00%' },
  { mode: 'hybrid', hr: '100.00%', mrr: '0.9236', full: '100.00%', on: true },
]

const reasons = [
  {
    t: '语料太小',
    d: '只有 2 个产品共 21 个 chunk，30 道题的答案几乎一一对应到某个块。top-20 召回等于把库里大半内容都捞回来。',
  },
  {
    t: '答案等于原词',
    d: '题目里的「90 日」「1 万元」「120 种」直接出现在正文，连字符 n-gram 都能命中，测不出语义检索能力。',
  },
  {
    t: '占位向量',
    d: '默认 provider 是字形哈希，不是语义向量。它能区分「等待期」和「保险责任」，但识别不了「理赔要多久」与「赔付时效」同义。',
  },
]

const todo = [
  '扩到 3 至 5 份真实条款，chunk 数上到 150 以上',
  '题目改为需要跨条款计算的形式，例如社保抵扣后还能赔多少',
  '换真实 embedding 模型并重建索引',
  '加入无关条款作为干扰项，检验检索是否被带偏',
]
</script>

<template>
  <section id="metrics" class="sec">
    <div class="wrap">
      <div class="head reveal">
        <p class="label">评测</p>
        <h2 class="h2">先承认这组数字不算数</h2>
        <p class="lede">
          30 道题分四类：10 道单条事实、8 道跨条款聚合、6 道应拒答、6 道多产品对比。
          检索层自动算 Hit Rate 与 MRR，生成层用模型评审加人工抽查。
          下面是当前基线的真实输出。
        </p>
      </div>

      <div class="layout">
        <div class="reveal">
          <div class="table-wrap card">
            <table>
              <caption class="mono">
                scripts/eval.py --mode all · 30 题 · top_k=20
              </caption>
              <thead>
                <tr>
                  <th scope="col">模式</th>
                  <th scope="col">Hit Rate</th>
                  <th scope="col">MRR</th>
                  <th scope="col">全部命中</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="r in rows" :key="r.mode" :class="{ on: r.on }">
                  <td class="mode">
                    <span class="mono">{{ r.mode }}</span>
                    <span v-if="r.on" class="pill">默认</span>
                  </td>
                  <td class="num">{{ r.hr }}</td>
                  <td class="num">{{ r.mrr }}</td>
                  <td class="num">{{ r.full }}</td>
                </tr>
              </tbody>
            </table>
          </div>

          <div class="invalid">
            <p class="iv-t">这组数字不构成效果结论</p>
            <ul class="iv-list">
              <li v-for="r in reasons" :key="r.t">
                <span class="iv-k">{{ r.t }}</span>
                <span class="iv-d">{{ r.d }}</span>
              </li>
            </ul>
            <p class="iv-f">
              当前配置只证明链路是通的：加载、切分、向量化、检索、生成、评测全部跑通。
              评测脚本本身也会在读到这里时打印显式警告。
            </p>
          </div>
        </div>

        <div class="side reveal" data-reveal-delay="80">
          <p class="col-title">待做的实验</p>
          <ol class="todo">
            <li v-for="(t, i) in todo" :key="t">
              <span class="n num">{{ String(i + 1).padStart(2, '0') }}</span>
              <span>{{ t }}</span>
            </li>
          </ol>

          <p class="col-title second">记录方式</p>
          <p class="small">
            每次改配置都重跑评测并把数字写进迭代日志，包括这次失败的一轮。
            没有记录就等于没发生过。
          </p>
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
  max-width: 680px;
  margin-bottom: 40px;
}

.head .label {
  margin-bottom: 14px;
}

.head .lede {
  margin-top: 16px;
}

.layout {
  display: grid;
  grid-template-columns: minmax(0, 1.5fr) minmax(0, 1fr);
  gap: clamp(28px, 4vw, 52px);
  align-items: start;
}

/* ---- 数据表 ---- */

.table-wrap {
  overflow-x: auto;
}

table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13.5px;
}

caption {
  caption-side: top;
  text-align: left;
  padding: 14px 18px;
  font-size: 11.5px;
  color: var(--ink-faint);
  border-bottom: 1px solid var(--line);
}

th,
td {
  padding: 12px 18px;
  text-align: left;
  white-space: nowrap;
}

thead th {
  font-family: var(--mono);
  font-size: 10.5px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--ink-faint);
  font-weight: 400;
  border-bottom: 1px solid var(--line);
}

tbody tr {
  border-bottom: 1px solid var(--line);
}

tbody tr:last-child {
  border-bottom: 0;
}

tbody td {
  color: var(--ink-soft);
}

tr.on td {
  color: var(--ink);
  background: var(--acc-wash);
}

.mode {
  display: flex;
  align-items: center;
  gap: 8px;
}

.num {
  font-family: var(--mono);
  font-variant-numeric: tabular-nums;
}

tr.on .num {
  color: var(--acc);
}

.pill {
  font-size: 10px;
  padding: 1px 7px;
  border-radius: var(--r-pill);
  border: 1px solid var(--acc-line);
  color: var(--acc);
}

/* ---- 无效判定 ---- */

.invalid {
  margin-top: 18px;
  border: 1px solid var(--line-strong);
  border-left: 2px solid var(--warn);
  border-radius: var(--r-sm);
  padding: 18px 20px;
  background: rgba(217, 164, 65, 0.045);
}

.iv-t {
  font-size: 14px;
  font-weight: 600;
  color: var(--warn);
}

.iv-list {
  list-style: none;
  margin: 12px 0 0;
  padding: 0;
  display: grid;
  gap: 9px;
}

.iv-list li {
  display: grid;
  grid-template-columns: 76px minmax(0, 1fr);
  gap: 12px;
  font-size: 13px;
  line-height: 1.65;
}

.iv-k {
  color: var(--ink);
  font-weight: 500;
}

.iv-d {
  color: var(--ink-mute);
  max-width: 60ch;
}

.iv-f {
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px solid var(--line);
  font-size: 12.5px;
  line-height: 1.65;
  color: var(--ink-faint);
}

/* ---- 右侧 ---- */

.col-title {
  font-family: var(--mono);
  font-size: 11px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--ink-faint);
  padding-bottom: 12px;
  border-bottom: 1px solid var(--line);
}

.col-title.second {
  margin-top: 32px;
}

.todo {
  list-style: none;
  margin: 0;
  padding: 0;
}

.todo li {
  display: grid;
  grid-template-columns: 26px minmax(0, 1fr);
  gap: 10px;
  padding: 12px 0;
  border-bottom: 1px solid var(--line);
  font-size: 13.5px;
  line-height: 1.6;
  color: var(--ink-soft);
}

.todo .n {
  font-size: 11px;
  color: var(--acc);
  padding-top: 3px;
}

.small {
  margin-top: 12px;
}

@media (max-width: 900px) {
  .layout {
    grid-template-columns: 1fr;
    gap: 36px;
  }
  .sec {
    padding: 64px 0;
  }
  th,
  td {
    padding: 11px 14px;
  }
}
</style>
