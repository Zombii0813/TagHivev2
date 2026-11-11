import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'

import App from './App.vue'
import router from './router'
import './styles/index.css'
import { resolveApiBaseUrl } from './api/baseUrl'
import { invoke } from '@tauri-apps/api/core'
import { installGlobalDragCleanup } from './utils/dragItems'

async function bootstrap() {
  const host = document.getElementById('app')!
  const panel = document.createElement('div')
  panel.style.cssText = 'max-width:560px;margin:12vh auto;padding:36px;border:1px solid #dfe6ed;border-radius:18px;background:#fff;box-shadow:0 12px 50px #21334d0d;font:15px/1.8 system-ui;color:#26344d'
  const title = document.createElement('h1')
  title.style.cssText = 'font-size:26px;font-weight:650;margin:0 0 12px'
  title.textContent = '正在启动 TagHive…'
  const message = document.createElement('p')
  message.style.cssText = 'margin:0 0 24px;color:#60718a;overflow-wrap:anywhere'
  message.textContent = '正在连接本机服务，请稍候。'
  panel.append(title, message)
  host.replaceChildren(panel)
  try {
    await resolveApiBaseUrl()
  } catch (error) {
    title.textContent = 'TagHive 启动未完成'
    message.textContent = error instanceof Error ? error.message : String(error)
    const retry = document.createElement('button')
    retry.textContent = '重试连接'
    retry.style.cssText = 'padding:9px 20px;border:1px solid #5149df;border-radius:9px;background:#5149df;color:#fff;font:inherit;cursor:pointer;margin-right:12px'
    retry.onclick = () => { retry.disabled = true; void bootstrap() }
    panel.append(retry)
    if ('__TAURI_INTERNALS__' in window) {
      const logs = document.createElement('button')
      logs.textContent = '打开日志目录'
      logs.style.cssText = 'padding:9px 20px;border:1px solid #dfe6ed;border-radius:9px;background:#fff;color:#26344d;font:inherit;cursor:pointer'
      logs.onclick = () => { void invoke('open_logs_folder') }
      panel.append(logs)
    }
    return
  }

  const app = createApp(App)

  app.use(createPinia())
  app.use(router)
  app.use(ElementPlus)

  // 兜底清理拖拽状态：源卡片在拖拽中被卸载时 dragend 不会触发
  installGlobalDragCleanup()

  app.mount('#app')
}

bootstrap()


