import { createApp } from 'vue'

/**
 * 入口文件保持极简。
 *
 * 这里**不引入 Element Plus**（既不引组件也不引样式）。
 * 原因：落地页完全不用 Element Plus，如果在这里全局注册，
 * 整个组件库会被拉进入口 chunk，落地页首屏就要为它付费。
 * 实测差别：全局注册时入口 HTML 会 modulepreload 338 KB 的 element-plus。
 *
 * Element Plus 的组件与样式都注册在 views/DemoView.vue 里，
 * 只有真正进入 /app 时才加载。
 *
 * 字体：自托管 IBM Plex（只取 latin 子集）。
 * ⚠️ 只引 latin-*.css，不引 index.css / 400.css ——
 * 后者会把 greek / cyrillic / vietnamese 子集全部打包，
 * 产生几十个无用字体文件。中文不在字体包里，走系统栈
 * （见 styles/main.css 的说明）。
 */
import '@fontsource/ibm-plex-sans/latin-400.css'
import '@fontsource/ibm-plex-sans/latin-500.css'
import '@fontsource/ibm-plex-sans/latin-600.css'
import '@fontsource/ibm-plex-sans/latin-400-italic.css'
import '@fontsource/ibm-plex-mono/latin-400.css'
import '@fontsource/ibm-plex-mono/latin-500.css'

import App from './App.vue'
import router from './router'
import './styles/main.css'

createApp(App).use(router).mount('#app')
