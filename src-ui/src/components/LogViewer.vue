<template>
  <el-dialog
    v-model="visible"
    title="Sidecar 日志"
    width="80%"
    :close-on-click-modal="false"
    class="log-viewer-dialog"
  >
    <div class="log-viewer">
      <div class="log-toolbar">
        <el-button-group>
          <el-button @click="refreshLogs" :icon="Refresh">刷新</el-button>
          <el-button @click="clearLogs" :icon="Delete">清空</el-button>
          <el-button @click="openLogFolder" :icon="FolderOpened">打开文件夹</el-button>
        </el-button-group>
        <el-input-number
          v-model="lineCount"
          :min="50"
          :max="5000"
          :step="50"
          size="small"
          style="width: 120px"
        >
          <template #suffix>行</template>
        </el-input-number>
      </div>
      <div ref="logContainer" class="log-content">
        <pre v-if="logs">{{ logs }}</pre>
        <el-empty v-else description="暂无日志" />
      </div>
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { invoke } from '@tauri-apps/api/core'
import { ElMessage } from 'element-plus'
import { Refresh, Delete, FolderOpened } from '@element-plus/icons-vue'

const visible = ref(false)
const logs = ref('')
const lineCount = ref(500)
const logContainer = ref<HTMLDivElement>()

const refreshLogs = async () => {
  try {
    const result = await invoke<string>('get_sidecar_logs', { lines: lineCount.value })
    logs.value = result
    // 滚动到底部
    setTimeout(() => {
      if (logContainer.value) {
        logContainer.value.scrollTop = logContainer.value.scrollHeight
      }
    }, 100)
  } catch (error) {
    ElMessage.error(`获取日志失败: ${error}`)
  }
}

const clearLogs = () => {
  logs.value = ''
}

const openLogFolder = async () => {
  try {
    await invoke('open_logs_folder')
  } catch (error) {
    ElMessage.error(`打开日志文件夹失败: ${error}`)
  }
}

// 当行数变化时自动刷新
watch(lineCount, () => {
  refreshLogs()
})

// 打开对话框时刷新日志
const open = () => {
  visible.value = true
  refreshLogs()
}

defineExpose({
  open
})
</script>

<style scoped>
.log-viewer {
  display: flex;
  flex-direction: column;
  height: 60vh;
}

.log-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 0;
  border-bottom: 1px solid var(--el-border-color);
  margin-bottom: 10px;
}

.log-content {
  flex: 1;
  overflow: auto;
  background-color: #1e1e1e;
  border-radius: 4px;
  padding: 10px;
}

.log-content pre {
  margin: 0;
  color: #d4d4d4;
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
  font-size: 12px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-wrap: break-word;
}

:deep(.log-viewer-dialog .el-dialog__body) {
  padding: 0 20px 20px;
}
</style>
