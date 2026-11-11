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
const refresh = () => {
  if (refreshTimer) clearTimeout(refreshTimer)
  refreshTimer = setTimeout(() => {
    fileStore.markTabsDirty(fileStore.activeTabId)
    void fileStore.reloadCurrentView()
    void tagStore.loadTags(appStore.currentWorkspace || undefined)
  }, 250)
}
const unsubscribe = [
  wsClient.on('file_changed', refresh), wsClient.on('file_deleted', refresh),
  wsClient.on('connected', refresh),
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
