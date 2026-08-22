<template>
  <div class="app">
    <router-view />
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useAppStore } from './stores/app'
import { useFileStore } from './stores/files'

const appStore = useAppStore()
const fileStore = useFileStore()

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
