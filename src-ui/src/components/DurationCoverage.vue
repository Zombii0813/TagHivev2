<template>
  <div class="coverage" role="status">
    <span v-if="error">{{ error }}</span>
    <span v-else>时长覆盖 {{ coverage.known }} / {{ coverage.total }}；未知时长始终排在末尾。</span>
    <span v-if="job.running">补探测 {{ job.processed }} / {{ job.total }}（失败 {{ job.failed }}）</span>
    <el-button v-if="job.running" size="small" :disabled="busy" @click="cancel">取消补探测</el-button>
    <el-button v-else size="small" :loading="busy" :disabled="coverage.probed >= coverage.total" @click="start">补探测未处理媒体（最多 1000 项）</el-button>
    <span v-if="job.running">取消将在当前文件结束后生效</span>
  </div>
</template>

<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { apiClient } from '../api/client'
import { useFileStore } from '../stores/files'
import { useAppStore } from '../stores/app'

const store = useFileStore(), app = useAppStore()
const coverage = ref({ total: 0, probed: 0, known: 0 })
const job = ref({ running: false, processed: 0, total: 0, failed: 0 })
const error = ref(''), busy = ref(false)
let timer: ReturnType<typeof setTimeout> | undefined
let version = 0, disposed = false
const scope = computed(() => {
  const tab = store.activeTab
  const folder = tab.browseMode !== 'all' && !!tab.currentFolderPath
  const filtered = !!(tab.searchText || tab.searchType || tab.searchQuery.tags?.length)
  return { ...tab.searchQuery, root: folder ? tab.currentFolderPath : tab.isGlobalView ? undefined : tab.workspace,
    roots: tab.isGlobalView ? [...app.workspaces] : undefined, text: tab.searchText || undefined,
    types: tab.searchType ? [tab.searchType] : undefined,
    direct_root: folder && !filtered ? tab.currentFolderPath : undefined }
})
async function refresh() {
  const request = ++version
  clearTimeout(timer)
  try {
    const [value, status] = await Promise.all([
      apiClient.post<typeof coverage.value>('/api/media/coverage', scope.value),
      apiClient.get<typeof job.value>('/api/media/probe'),
    ])
    if (disposed || request !== version) return
    const finished = job.value.running && !status.running
    coverage.value = value; job.value = status; error.value = ''
    if (finished) void store.reloadCurrentView()
  } catch { if (!disposed && request === version) error.value = '时长覆盖率读取失败' }
  finally { if (!disposed && request === version) timer = setTimeout(refresh, 2500) }
}
async function start() {
  busy.value = true
  const targets = { ...scope.value }
  try { job.value = await apiClient.post('/api/media/probe', targets); await refresh() }
  catch { error.value = '补探测启动失败，请稍后重试' }
  finally { busy.value = false }
}
async function cancel() {
  busy.value = true
  try { await apiClient.delete('/api/media/probe'); await refresh() }
  catch { error.value = '取消失败，请重试' }
  finally { busy.value = false }
}
watch(() => JSON.stringify(scope.value), refresh, { immediate: true })
onUnmounted(() => { disposed = true; version++; clearTimeout(timer) })
</script>

<style scoped>
.coverage { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; padding: 8px 14px; font-size: 12px; background: var(--color-bg-tertiary); }
</style>
