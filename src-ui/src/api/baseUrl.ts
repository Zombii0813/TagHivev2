// 通过 Tauri invoke 从 Rust 侧获取真实的 sidecar 端口；
// 多个 TagHive 实例（如开发版 + 生产版）并存时，端口可能不是默认的 8721，
// 必须查 Rust 才能避免前端连到错误的 sidecar，导致数据写入到错误的数据库。

import { invoke } from '@tauri-apps/api/core'

const DEFAULT_PORT = 8721
const FALLBACK_BASE_URL = `http://127.0.0.1:${DEFAULT_PORT}`

function isTauri(): boolean {
  return typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window
}

async function fetchSidecarPort(): Promise<number> {
  // sidecar 由 Rust 在 setup 中异步启动；这里轮询直到拿到端口
  // （上限 ~15s，避免冷启动竞速时前端直接报错）
  const deadline = Date.now() + 15000
  let delay = 100
  while (Date.now() < deadline) {
    try {
      const port = await invoke<number | null>('cmd_get_sidecar_port')
      if (port) return port
    } catch (e) {
      console.warn('[baseUrl] cmd_get_sidecar_port failed:', e)
    }
    await new Promise(r => setTimeout(r, delay))
    delay = Math.min(delay * 1.5, 500)
  }
  console.error(`[baseUrl] sidecar port not ready in time, falling back to ${DEFAULT_PORT}`)
  return DEFAULT_PORT
}

let cachedBaseUrl: string | null = null

/** 解析并缓存 API/WS 基础地址（同源协议，HTTP）。 */
export async function resolveApiBaseUrl(): Promise<string> {
  if (cachedBaseUrl) return cachedBaseUrl

  // 用户显式覆盖（构建期注入），优先级最高
  const envUrl = import.meta.env.VITE_API_URL as string | undefined
  if (envUrl) {
    cachedBaseUrl = envUrl
    return cachedBaseUrl
  }

  if (isTauri()) {
    const port = await fetchSidecarPort()
    cachedBaseUrl = `http://127.0.0.1:${port}`
    return cachedBaseUrl
  }

  // 纯浏览器（vite dev 直开 :5173）：使用空 baseURL 让 vite 代理生效
  cachedBaseUrl = ''
  return cachedBaseUrl
}

/** 同步获取已解析的 baseURL；必须在 resolveApiBaseUrl() 完成后调用。 */
export function getApiBaseUrl(): string {
  if (cachedBaseUrl === null) {
    console.warn('[baseUrl] getApiBaseUrl() before resolveApiBaseUrl(); using fallback')
    return isTauri() ? FALLBACK_BASE_URL : ''
  }
  return cachedBaseUrl
}
