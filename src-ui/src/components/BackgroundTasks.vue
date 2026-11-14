<template>
  <Transition name="th-fade">
  <div v-if="store.isScanning || showDuration" class="background-tasks">
    <!-- 任务入口随任务开始/结束淡入淡出（外层 Transition），避免状态栏左侧内容突然出现或消失 -->
    <el-popover placement="top-start" trigger="click" :width="340">
      <template #reference>
        <el-button class="task-entry" size="small" text :title="summary" :aria-label="`查看后台任务：${summary}`">
          <el-icon :class="{ 'task-running': store.isScanning || job.running }"><Loading v-if="store.isScanning || job.running" /><Clock v-else /></el-icon>
          <span class="task-summary" role="status">{{ summary }}</span>
        </el-button>
      </template>
      <div class="task-details">
        <section v-if="store.isScanning" class="scan-task">
          <strong>工作区扫描</strong>
          <el-progress :percentage="store.scanProgress" :stroke-width="4" />
          <span>已处理 {{ store.scanCount }} / {{ store.scanTotal }}</span>
          <span v-if="store.scanCurrentFile" class="task-path">{{ store.scanCurrentFile }}</span>
          <el-button size="small" @click="wsClient.cancelScan()">取消全部扫描</el-button>
        </section>
        <section v-if="showDuration" class="coverage">
          <strong>媒体时长</strong>
          <span v-if="error" class="task-error" role="alert">{{ error }}</span>
          <span v-if="coverageLoaded">时长覆盖 {{ coverage.known }} / {{ coverage.total }}</span>
          <span v-else-if="!error">正在读取覆盖率…</span>
          <span>未知时长始终排在末尾；每批最多补探测 1000 项。</span>
          <template v-if="job.running">
            <span>补探测 {{ job.processed }} / {{ job.total }}（失败 {{ job.failed }}）</span>
            <el-progress :percentage="job.total ? Math.min(100, Math.round(job.processed / job.total * 100)) : 0" :stroke-width="4" />
            <el-button size="small" :disabled="busy" @click="cancel">取消补探测</el-button>
            <span>取消将在当前文件结束后生效</span>
          </template>
          <el-button v-else size="small" :loading="busy" :disabled="!coverageLoaded || coverage.probed >= coverage.total" @click="start">补探测未处理媒体</el-button>
          <el-button v-if="error" size="small" :disabled="busy" @click="refresh">重试读取</el-button>
        </section>
      </div>
    </el-popover>
  </div>
  </Transition>
</template>

<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { Clock, Loading } from '@element-plus/icons-vue'
import { apiClient } from '../api/client'
import { wsClient } from '../api/websocket'
import { useFileStore } from '../stores/files'
import { useAppStore } from '../stores/app'

const store = useFileStore(), app = useAppStore()
const coverage = ref({ total: 0, probed: 0, known: 0 })
const coverageLoaded = ref(false)
const job = ref({ running: false, processed: 0, total: 0, failed: 0 })
const error = ref(''), busy = ref(false)
let timer: ReturnType<typeof setTimeout> | undefined
let version = 0, disposed = false
const showDuration = computed(() => store.sortBy === 'duration' || job.value.running || busy.value)
const summary = computed(() => {
  if (store.isScanning && job.value.running) return '任务 · 2（扫描、补探测）'
  if (store.isScanning) return `扫描 ${store.scanCount} / ${store.scanTotal}`
  if (job.value.running) return `补探测 ${job.value.processed} / ${job.value.total}`
  if (error.value) return '时长读取失败'
  return coverageLoaded.value ? `时长 ${coverage.value.known} / ${coverage.value.total}` : '正在读取时长…'
})
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
      showDuration.value ? apiClient.post<typeof coverage.value>('/api/media/coverage', scope.value) : Promise.resolve(null),
      apiClient.get<typeof job.value>('/api/media/probe'),
    ])
    if (disposed || request !== version) return
    const finished = job.value.running && !status.running
    if (value) { coverage.value = value; coverageLoaded.value = true }
    job.value = status; error.value = ''
    if (finished) void store.reloadCurrentView()
  } catch { if (!disposed && request === version && showDuration.value) error.value = '时长覆盖率读取失败' }
  finally { if (!disposed && request === version && showDuration.value) timer = setTimeout(refresh, 2500) }
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
// 初始检查后台任务；只有时长排序下的范围变化需要立即重读覆盖率。
// 运行中的任务始终由轮询跟踪，避免普通名称搜索的每次输入都请求时长接口。
watch([() => store.sortBy === 'duration', () => store.sortBy === 'duration' ? JSON.stringify(scope.value) : ''], () => {
  coverageLoaded.value = false
  void refresh()
}, { immediate: true })
onUnmounted(() => { disposed = true; version++; clearTimeout(timer) })
</script>

<style scoped>
.background-tasks { display: flex; min-width: 0; max-width: 100%; }
.task-entry { min-width: 0; max-width: 100%; padding: 4px 0; }
.task-entry :deep(> span) { min-width: 0; }
.task-summary { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.task-entry .el-icon { flex-shrink: 0; margin-right: 6px; }
.task-details { display: flex; flex-direction: column; gap: 16px; max-height: min(70vh, 520px); overflow-y: auto; }
.scan-task, .coverage { display: flex; flex-direction: column; align-items: flex-start; gap: 10px; font-size: 12px; }
.task-details .el-progress { width: 100%; }
.task-details :deep(.el-button + .el-button) { margin-left: 0; }
.task-path { max-width: 100%; overflow-wrap: anywhere; color: var(--color-text-secondary); }
.task-error { color: var(--el-color-danger); }
.task-running { animation: task-spin 1s linear infinite; }
@keyframes task-spin { to { transform: rotate(360deg); } }
@media (prefers-reduced-motion: reduce) { .task-running { animation: none; } }
</style>
