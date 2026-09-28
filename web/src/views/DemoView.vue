<script setup>
/**
 * 演示页：真正的问答工作区。
 *
 * 与落地页分开的原因：落地页是长滚动叙事，演示页是固定工作区，
 * 两者对滚动和视口的要求相反，塞进一页会互相打架。
 *
 * 业务逻辑全在 useChat 里，这里只管布局。
 */
import { onMounted, ref } from 'vue'

/**
 * Element Plus 只在这个路由里引入 —— 组件与样式都是。
 *
 * 为什么不在 main.js 全局注册：落地页完全不用 Element Plus，
 * 全局注册会把整个组件库拉进入口 chunk，落地页首屏被迫加载 338 KB。
 * 在这里按需深层导入 + 局部注册后，Vite 自动把 element-plus
 * 拆成独立 chunk，只有进入 /app 时才请求。
 *
 * 深层导入（element-plus/es/components/xxx/index.mjs）而不是
 * `import { ElButton } from 'element-plus'`：
 * 后者是 barrel 入口，有副作用，tree-shaking 摇不掉，
 * 实测会让 element-plus 分块从 1.09 MB 涨到无法优化的体积。
 * JS 总量从 1.19 MB 降到 436 KB 就是这么来的。
 */
import { ElAlert } from 'element-plus/es/components/alert/index.mjs'
import { ElButton } from 'element-plus/es/components/button/index.mjs'
import { ElInput } from 'element-plus/es/components/input/index.mjs'
import { ElInputNumber } from 'element-plus/es/components/input-number/index.mjs'
import { ElOption } from 'element-plus/es/components/select/index.mjs'
import { ElRadioButton, ElRadioGroup } from 'element-plus/es/components/radio/index.mjs'
import { ElSelect } from 'element-plus/es/components/select/index.mjs'
import { ElTag } from 'element-plus/es/components/tag/index.mjs'
import 'element-plus/dist/index.css'

import { useChat } from '@/composables/useChat'
import QuestionPanel from '@/components/QuestionPanel.vue'
import MessageCard from '@/components/MessageCard.vue'
import CorpusPanel from '@/components/CorpusPanel.vue'
import ModelSettingsPanel from '@/components/ModelSettingsPanel.vue'

const {
  health,
  products,
  messages,
  options,
  isStreaming,
  statusText,
  statusType,
  loadHealth,
  ask,
  abort,
} = useChat()

// 语料管理面板默认收起：日常用不到，但需要时一眼能找到
const showCorpus = ref(false)
const showSettings = ref(false)

/**
 * 重建索引后必须重新拉一次 health 和 products ——
 * 否则顶栏还显示旧的 chunk 数、产品下拉框里还是旧产品。
 */
async function onReindexed() {
  await loadHealth()
  options.docIds = []      // 旧的产品筛选可能已经不存在了，清空避免报错
}

async function onSettingsSaved() {
  await loadHealth()
}

onMounted(loadHealth)
</script>

<template>
  <div class="demo">
    <header class="bar">
      <RouterLink to="/" class="back">
        <span aria-hidden="true">←</span>
        <span>返回首页</span>
      </RouterLink>

      <div class="title">
        <span class="nm">保险条款 RAG</span>
        <span class="sb">演示</span>
      </div>

      <div class="bar-right">
        <button
          class="ghost-btn"
          type="button"
          :class="{ on: showSettings }"
          @click="showSettings = !showSettings"
        >
          {{ showSettings ? '收起设置' : '模型设置' }}
        </button>
        <button
          class="ghost-btn"
          type="button"
          :class="{ on: showCorpus }"
          @click="showCorpus = !showCorpus"
        >
          {{ showCorpus ? '收起语料' : '管理语料' }}
        </button>
        <el-tag :type="statusType" effect="dark" size="small">{{ statusText }}</el-tag>
        <el-tag v-if="health?.embedding" size="small" effect="plain">
          {{ health.embedding }}
        </el-tag>
        <el-tag v-if="health?.llm" size="small" effect="plain">{{ health.llm }}</el-tag>
      </div>
    </header>

    <main class="content">
      <ModelSettingsPanel v-if="showSettings" @saved="onSettingsSaved" />
      <CorpusPanel v-if="showCorpus" @reindexed="onReindexed" />
      <el-alert
        v-if="health?.error"
        type="error"
        show-icon
        :closable="false"
        title="服务配置异常"
        :description="health.error"
        style="margin-bottom: 16px"
      />
      <el-alert
        v-else-if="health && !health.index_ready"
        type="warning"
        show-icon
        :closable="false"
        title="索引未就绪"
        description="先运行 python scripts/build_index.py，然后刷新本页。"
        style="margin-bottom: 16px"
      />

      <el-alert
        v-if="health?.llm === 'MockLLM'"
        type="warning"
        show-icon
        :closable="false"
        title="当前使用离线演示模型，回答内容是占位文本"
        description="点击页面上方「模型设置」，填写 LLM API 地址、模型名称和密钥并保存。"
        style="margin-bottom: 16px"
      />

      <el-alert
        v-if="health?.embedding?.startsWith('hash-')"
        type="info"
        show-icon
        :closable="false"
        title="当前使用关键词/哈希兜底向量"
        description="点击页面上方「模型设置」配置 Embedding API，保存后在「管理语料」里重建索引。"
        style="margin-bottom: 16px"
      />

      <QuestionPanel
        :products="products"
        :options="options"
        :streaming="isStreaming"
        @ask="ask"
        @abort="abort"
      />

      <div v-if="!messages.length" class="empty">
        <p>按 Enter 提问，或点上面的示例问题开始。</p>
        <p class="hint">
          回答会标注依据的条款编号；如果条款里没有相关信息，
          系统会明确说无法确定，而不是编造。
          试试「这款产品的保费是多少钱？」这条，它会触发拒答。
        </p>
      </div>

      <MessageCard v-for="m in messages" :key="m.id" :message="m" />
    </main>
  </div>
</template>

<style scoped>
.demo {
  min-height: 100dvh;
  display: flex;
  flex-direction: column;
}

.bar {
  position: sticky;
  top: 0;
  z-index: 20;
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
  padding: 12px 28px;
  height: auto;
  min-height: 64px;
  background: rgba(11, 14, 17, 0.88);
  border-bottom: 1px solid var(--line);
  backdrop-filter: blur(14px) saturate(160%);
}

.back {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--ink-mute);
  flex: none;
  transition: color 0.15s ease;
}

.back:hover {
  color: var(--acc);
}

.title {
  display: flex;
  align-items: baseline;
  gap: 8px;
}

.nm {
  font-size: 14.5px;
  font-weight: 600;
}

.sb {
  font-family: var(--mono);
  font-size: 10.5px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--ink-faint);
  padding: 2px 7px;
  border: 1px solid var(--line);
  border-radius: var(--r-pill);
}

.bar-right {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  align-items: center;
  margin-left: auto;
}

.ghost-btn {
  appearance: none;
  height: 26px;
  padding: 0 11px;
  border-radius: var(--r-sm);
  border: 1px solid var(--line-strong);
  background: transparent;
  color: var(--ink-mute);
  font: inherit;
  font-size: 12px;
  cursor: pointer;
  white-space: nowrap;
  transition:
    color 0.15s ease,
    border-color 0.15s ease;
}

.ghost-btn:hover {
  color: var(--acc);
  border-color: var(--acc-line);
}

.ghost-btn.on {
  color: var(--acc);
  border-color: var(--acc-line);
  background: var(--acc-wash);
}

.ghost-btn:focus-visible {
  outline: 2px solid var(--acc);
  outline-offset: 2px;
}

.content {
  flex: 1;
  width: 100%;
  max-width: 880px;
  margin: 0 auto;
  padding: 24px 20px 64px;
}

.empty {
  text-align: center;
  color: var(--ink-mute);
  padding: 48px 16px;
  font-size: 14px;
}

.empty .hint {
  font-size: 13px;
  max-width: 540px;
  margin: 8px auto 0;
  line-height: 1.75;
  color: var(--ink-faint);
}

@media (max-width: 720px) {
  .bar {
    padding: 10px 14px;
    gap: 10px;
  }
  .title {
    display: none;
  }
  .content {
    padding: 16px 12px 48px;
  }
}
</style>
