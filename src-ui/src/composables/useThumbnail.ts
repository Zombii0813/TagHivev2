import { computed, onUnmounted, ref, watch, type Ref } from 'vue'
import { thumbnailApi } from '../api/thumbnails'
import { apiClient } from '../api/client'
import { wsClient } from '../api/websocket'
import type { FileSummary, ThumbnailReadyEvent } from '../types'

const consumers = new Map<string, number>()
let visibilityTimer: ReturnType<typeof setTimeout> | undefined
function updateVisibility(path: string | undefined, delta: number) {
  if (!path) return
  const count = (consumers.get(path) ?? 0) + delta
  if (count > 0) consumers.set(path, count)
  else consumers.delete(path)
  clearTimeout(visibilityTimer)
  visibilityTimer = setTimeout(() => {
    void apiClient.post('/api/thumbnails/async/visible', [...consumers.keys()]).catch(() => {})
  }, 150)
}

/** 卡片和详情共用缩略图状态；透明占位保持 pending，丢失通知后有限重试。 */
export function useThumbnail(file: Ref<FileSummary | undefined>, size: 'small' | 'medium' | 'large') {
  const status = ref<'pending' | 'ready' | 'error'>('pending')
  const version = ref(0)
  let attempts = 0
  let timer: ReturnType<typeof setTimeout> | undefined
  const url = computed(() => file.value
    ? `${thumbnailApi.getThumbnailUrl(file.value.id, size)}&v=${file.value.modified_at}-${file.value.size}&retry=${version.value}` : '')
  function retry() {
    clearTimeout(timer)
    status.value = 'pending'
    version.value++
  }
  function schedule() {
    clearTimeout(timer)
    if (++attempts > 4) { status.value = 'error'; return }
    timer = setTimeout(retry, 1500 * attempts)
  }
  function onLoad(event: Event) {
    const image = event.target as HTMLImageElement
    if (image.currentSrc !== new URL(url.value, location.href).href) return
    if (image.naturalWidth <= 1) { schedule(); return }
    clearTimeout(timer)
    status.value = 'ready'
  }
  function onError() { status.value = 'error'; clearTimeout(timer) }
  const off = wsClient.on<ThumbnailReadyEvent>('thumbnail_ready', data => {
    if (data.file_path !== file.value?.path || data.size !== size) return
    if (data.success) retry()
    else onError()
  })
  let registered: string | undefined
  watch(() => file.value?.path, path => {
    updateVisibility(registered, -1)
    registered = path
    updateVisibility(registered, 1)
  }, { immediate: true })
  watch(() => [file.value?.id, file.value?.modified_at, file.value?.size], () => {
    clearTimeout(timer); attempts = 0; status.value = 'pending'; version.value++
  }, { immediate: true })
  onUnmounted(() => { off(); clearTimeout(timer); updateVisibility(registered, -1) })
  return { url, status, onLoad, onError, retry: () => { attempts = 0; retry() } }
}
