<template>
  <div class="app">
    <router-view />
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, watch } from 'vue'
import { wsClient } from './api/websocket'
import { useTagStore } from './stores/tags'
import { useAppStore } from './stores/app'
import { useFileStore } from './stores/files'

const appStore = useAppStore()
const fileStore = useFileStore()
const tagStore = useTagStore()
let refreshTimer: ReturnType<typeof setTimeout> | undefined
const changedPaths = new Set<string>()
let refreshAll = false
const refresh = (event?: { path?: string; destination?: string }) => {
  if (!event?.path) refreshAll = true
  else { changedPaths.add(event.path); if (event.destination) changedPaths.add(event.destination) }
  if (refreshTimer) return
  refreshTimer = setTimeout(() => {
    refreshTimer = undefined
    const paths = refreshAll ? undefined : [...changedPaths]
    changedPaths.clear(); refreshAll = false
    void fileStore.refreshChangedPaths(paths)
    const root = appStore.currentWorkspace?.replace(/\\/g, '/').toLowerCase()
    if (!paths || !root || paths.some(path => path.replace(/\\/g, '/').toLowerCase().startsWith(root + '/'))) {
      void tagStore.loadTags(appStore.currentWorkspace || undefined)
    }
  }, 500)
}
const unsubscribe = [
  wsClient.on<{ path?: string; destination?: string }>('file_changed', refresh),
  wsClient.on<{ path?: string; destination?: string }>('file_deleted', refresh),
  wsClient.on('connected', () => refresh()),
]
watch(() => [...appStore.workspaces], paths => {
  wsClient.subscribeWorkspaces(paths)
  fileStore.markTabsDirty()
  refresh()
}, { immediate: true })
onUnmounted(() => {
  unsubscribe.forEach(off => off())
  if (refreshTimer) clearTimeout(refreshTimer)
  wsClient.disconnect()
})

onMounted(async () => {
  await appStore.initialize()
  // 工作区列表就绪后剔除跨会话恢复出的死标签页（其工作区已被移除）。
  // 必须等 initialize 完成：在那之前 workspaces 为空，会把全部标签页误判为失效。
  fileStore.pruneInvalidTabs(appStore.workspaces)
})
</script>

<style>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

html, body, #app, .app {
  height: 100%;
  width: 100%;
  overflow: hidden;
}

body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}
</style>
