<template>
  <div class="settings-view">
    <el-page-header title="返回" @back="$router.back()" />
    
    <h2>设置</h2>
    
    <el-form label-width="120px" class="settings-form">
      <el-form-item label="当前工作区">
        <div class="workspace-setting">
          <el-input
            v-model="currentWorkspace"
            readonly
            placeholder="未选择工作区"
          >
            <template #append>
              <el-button @click="selectWorkspace">选择文件夹</el-button>
            </template>
          </el-input>
        </div>
      </el-form-item>
      
      <el-form-item label="主题">
        <el-radio-group v-model="appStore.theme" @change="appStore.setTheme">
          <el-radio-button label="light">浅色</el-radio-button>
          <el-radio-button label="dark">深色</el-radio-button>
        </el-radio-group>
      </el-form-item>
      
      <el-form-item>
        <el-button type="primary" @click="rescanWorkspace">
          <el-icon><Refresh /></el-icon>
          重新扫描工作区
        </el-button>
        <el-button @click="openLogViewer">
          <el-icon><Document /></el-icon>
          查看日志
        </el-button>
      </el-form-item>
    </el-form>
    
    <!-- 扫描进度对话框 -->
    <el-dialog
      v-model="scanning"
      title="扫描工作区"
      :close-on-click-modal="false"
      :show-close="false"
      width="400px"
    >
      <div class="scan-progress">
        <el-progress :percentage="scanProgress" :status="scanStatus" />
        <p>已扫描 {{ scanCount }} 个文件</p>
      </div>
    </el-dialog>
    
    <!-- 日志查看器 -->
    <LogViewer ref="logViewerRef" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { Refresh, Document } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useAppStore } from '../stores/app'
import { useFileStore } from '../stores/files'
import { wsClient } from '../api/websocket'
import LogViewer from '../components/LogViewer.vue'

const appStore = useAppStore()
const fileStore = useFileStore()

const scanning = ref(false)
const scanProgress = ref(0)
const scanCount = ref(0)
const scanStatus = ref('')
const logViewerRef = ref<InstanceType<typeof LogViewer>>()

const currentWorkspace = computed(() => appStore.currentWorkspace || '')

function openLogViewer() {
  logViewerRef.value?.open()
}

async function selectWorkspace() {
  const path = await appStore.selectFolder()
  if (path) {
    // 连接 WebSocket
    wsClient.connect()
    
    // 订阅扫描完成事件
    const unsubscribeCompleted = wsClient.on<{ path: string; total: number }>('scan_completed', (data) => {
      ElMessage.success(`扫描完成，共 ${data.total} 个文件`)
      // 扫描完成后刷新文件列表
      fileStore.search({ root: path })
      unsubscribeCompleted()
    })
    
    const unsubscribeError = wsClient.on<{ message: string }>('scan_error', (error) => {
      ElMessage.error(`扫描失败: ${error.message}`)
      unsubscribeError()
    })
    
    // 开始扫描
    wsClient.startScan(path)
    ElMessage.success('工作区已更新，开始扫描...')
  }
}

function rescanWorkspace() {
  if (!appStore.currentWorkspace) {
    ElMessage.warning('请先选择工作区')
    return
  }
  
  scanning.value = true
  scanProgress.value = 0
  scanCount.value = 0
  scanStatus.value = ''
  
  // 连接 WebSocket
  wsClient.connect()
  
  // 订阅扫描事件
  const unsubscribeProgress = wsClient.on<ScanProgressEvent>('scan_progress', (data) => {
    scanCount.value = data.count
  })
  
  const unsubscribeCompleted = wsClient.on<{ path: string; total: number }>('scan_completed', (data) => {
    scanProgress.value = 100
    scanStatus.value = 'success'
    scanning.value = false
    ElMessage.success(`扫描完成，共 ${data.total} 个文件`)
    fileStore.search({ root: appStore.currentWorkspace! })
    
    // 取消订阅
    unsubscribeProgress()
    unsubscribeCompleted()
  })
  
  const unsubscribeError = wsClient.on<{ message: string }>('scan_error', (error) => {
    scanStatus.value = 'exception'
    scanning.value = false
    ElMessage.error(`扫描失败: ${error.message}`)
    
    unsubscribeProgress()
    unsubscribeCompleted()
    unsubscribeError()
  })
  
  // 开始扫描
  wsClient.startScan(appStore.currentWorkspace)
}

interface ScanProgressEvent {
  count: number
  path: string
}
</script>

<style scoped>
.settings-view {
  padding: 24px;
  max-width: 800px;
  margin: 0 auto;
}

h2 {
  margin: 24px 0;
  color: var(--color-text-primary);
}

.settings-form {
  margin-top: 32px;
}

.workspace-setting {
  display: flex;
  gap: 12px;
}

.scan-progress {
  text-align: center;
  padding: 20px;
}

.scan-progress p {
  margin-top: 16px;
  color: var(--color-text-secondary);
}
</style>
