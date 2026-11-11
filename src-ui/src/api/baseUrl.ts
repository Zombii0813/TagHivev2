import { shallowRef } from 'vue'
import { invoke } from '@tauri-apps/api/core'

interface Session { port?: number; token: string; instance_id: string }
let cachedBaseUrl: string | null = null
const session = shallowRef<Session | null>(null)
let resolving: Promise<string> | null = null
const isTauri = () => typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window

/** 获取当前宿主的就绪实例，校验失败时禁止回退到其它端口。 */
export async function resolveApiBaseUrl(refresh = false): Promise<string> {
  if (resolving) return resolving
  if (!refresh && cachedBaseUrl !== null && session.value) return cachedBaseUrl
  resolving = (async () => {
    let candidate: Session
    let base: string
    if (isTauri()) {
      await invoke('cmd_start_sidecar')
      const result = await invoke<Session | null>('cmd_get_sidecar_session')
      if (!result?.port) throw new Error('后端尚未就绪，请查看 sidecar.log 后重试')
      candidate = result
      base = `http://127.0.0.1:${result.port}`
    } else {
      base = (import.meta.env.VITE_API_URL as string | undefined) || ''
      const response = await fetch(`${base}/api/session`, { cache: 'no-store', signal: AbortSignal.timeout(5000) })
      if (!response.ok) throw new Error(`无法获取开发会话 (${response.status})，请启动 Python 后端`)
      candidate = await response.json()
    }
    const response = await fetch(`${base}/api/health`, {
      headers: { Authorization: `Bearer ${candidate.token}` },
      cache: 'no-store', signal: AbortSignal.timeout(5000),
    })
    if (!response.ok || (await response.json()).instance_id !== candidate.instance_id) {
      throw new Error('后端实例校验失败，请重试')
    }
    session.value = candidate
    cachedBaseUrl = base
    return base
  })().finally(() => { resolving = null })
  return resolving
}

export function getApiBaseUrl(): string { return cachedBaseUrl ?? '' }
export function getSessionToken(): string { return session.value?.token ?? '' }
export function sessionHeaders(): Record<string, string> {
  return { Authorization: `Bearer ${getSessionToken()}` }
}
export function mediaUrl(path: string): string {
  return `${getApiBaseUrl()}${path}${path.includes('?') ? '&' : '?'}session=${encodeURIComponent(getSessionToken())}`
}
