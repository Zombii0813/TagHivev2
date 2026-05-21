import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'

import App from './App.vue'
import router from './router'
import './styles/index.css'
import { resolveApiBaseUrl } from './api/baseUrl'

async function bootstrap() {
  // 在挂载 UI 前向 Tauri 查询真实 sidecar 端口；
  // 多实例并存时端口可能不是 8721，必须先解析以避免数据写入到错误的进程。
  await resolveApiBaseUrl()

  const app = createApp(App)

  // 注册所有图标
  for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
    app.component(key, component)
  }

  app.use(createPinia())
  app.use(router)
  app.use(ElementPlus)

  app.mount('#app')
}

bootstrap()


