import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

// 开发时前端跑在 5173，后端 FastAPI 跑在 8000。
// 用 proxy 而不是让前端写死后端地址：
//   1. 避开 CORS —— 浏览器看到的是同源请求
//   2. 换后端地址只改这里一处，不用重新构建前端
// 生产构建后由 FastAPI 托管 dist/，同样是同源，不需要 CORS。
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    port: 5173,
    proxy: {
      // 前端统一请求 /api/xxx。
      // 开发时：Vite 把 /api 前缀 rewrite 掉再转发给 8000 —— 所以后端收到的是 /xxx。
      //         这里必须 rewrite，否则会变成 /api/api/health 而 404。
      // 生产时：FastAPI 自己挂着 /api 路由，前端不用改任何代码。
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
        // SSE 流式：不能在代理层缓冲
        configure: (proxy) => {
          proxy.on('proxyRes', (proxyRes) => {
            proxyRes.headers['cache-control'] = 'no-cache'
          })
        },
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
    // 手动分包：把 vue 和 element-plus 拆出来，
    // 这样业务代码改动时用户不用重新下载整个 vendor 包。
    // 代价是请求数变多，对内部系统来说缓存收益更大。
    rollupOptions: {
      output: {
        manualChunks: {
          vue: ['vue'],
          'element-plus': ['element-plus', '@element-plus/icons-vue'],
        },
      },
    },
    // 分包后单块仍可能超过默认 500KB 告警阈值，放宽到 900
    chunkSizeWarningLimit: 900,
  },
})
