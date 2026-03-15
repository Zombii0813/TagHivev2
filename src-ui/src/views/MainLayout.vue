<template>
  <div class="main-layout">
    <!-- 侧边栏 -->
    <aside class="sidebar" :class="{ collapsed: appStore.sidebarCollapsed }">
      <div class="sidebar-header">
        <h1 class="logo">
          <el-icon><CollectionTag /></el-icon>
          <span v-if="!appStore.sidebarCollapsed">TagHive</span>
        </h1>
      </div>
      
      <div class="sidebar-content">
        <TagPanel />
      </div>
    </aside>

    <!-- 主内容区 -->
    <main class="main-content">
      <!-- 顶部工具栏 -->
      <header class="toolbar">
        <div class="toolbar-left">
          <el-button
            v-if="!isMobile"
            :icon="appStore.sidebarCollapsed ? Expand : Fold"
            circle
            @click="appStore.toggleSidebar()"
          />
          <SearchBar />
        </div>
        
        <div class="toolbar-right">
          <!-- 重新扫描按钮 -->
          <el-button
            :icon="Refresh"
            circle
            @click="handleRescan"
            :loading="fileStore.isScanning"
            :disabled="!appStore.currentWorkspace"
            :title="'重新扫描工作区'"
          />
          
          <!-- 排序下拉菜单 -->
          <el-dropdown @command="handleSortCommand" trigger="click">
            <el-button :title="'排序'">
              <el-icon>
                <component :is="getSortIcon()" />
              </el-icon>
              <span class="sort-label">{{ getSortLabel() }}</span>
              <el-icon class="el-icon--right"><arrow-down /></el-icon>
            </el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="name_asc">
                  <el-icon><Sort /></el-icon> 名称升序
                </el-dropdown-item>
                <el-dropdown-item command="name_desc">
                  <el-icon><SortDown /></el-icon> 名称降序
                </el-dropdown-item>
                <el-dropdown-item divided command="modified_at_desc">
                  <el-icon><SortDown /></el-icon> 日期降序（最新）
                </el-dropdown-item>
                <el-dropdown-item command="modified_at_asc">
                  <el-icon><Sort /></el-icon> 日期升序（最早）
                </el-dropdown-item>
                <el-dropdown-item divided command="size_desc">
                  <el-icon><SortDown /></el-icon> 大小降序
                </el-dropdown-item>
                <el-dropdown-item command="size_asc">
                  <el-icon><Sort /></el-icon> 大小升序
                </el-dropdown-item>
                <el-dropdown-item divided command="duration_desc">
                  <el-icon><SortDown /></el-icon> 时长降序
                </el-dropdown-item>
                <el-dropdown-item command="duration_asc">
                  <el-icon><Sort /></el-icon> 时长升序
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>

          <!-- 文件夹浏览模式切换 -->
          <el-button
            :class="['browse-mode-btn', { active: fileStore.browseMode === 'folder' }]"
            :icon="Folder"
            circle
            @click="toggleBrowseMode"
            :title="fileStore.browseMode === 'folder' ? '切换到全部文件模式' : '切换到文件夹浏览模式'"
          />

          <!-- 视图模式切换 -->
          <el-button-group class="view-mode-group">
            <el-button
              :class="['view-mode-btn', { active: fileStore.viewMode === 'grid' }]"
              :icon="Grid"
              @click="fileStore.setViewMode('grid')"
              :title="'网格视图'"
            />
            <el-button
              :class="['view-mode-btn', { active: fileStore.viewMode === 'list' }]"
              :icon="List"
              @click="fileStore.setViewMode('list')"
              :title="'列表视图'"
            />
          </el-button-group>
          
          <el-button
            :icon="appStore.detailPanelVisible ? ArrowRight : ArrowLeft"
            circle
            @click="appStore.toggleDetailPanel()"
            :title="appStore.detailPanelVisible ? '隐藏详情' : '显示详情'"
          />
          
          <el-button 
            :icon="appStore.isDark ? Sunny : Moon" 
            circle 
            @click="appStore.toggleTheme()"
            :title="appStore.isDark ? '切换到浅色模式' : '切换到深色模式'" 
          />
          <el-button :icon="Setting" circle @click="$router.push('/settings')" :title="'设置'" />
        </div>
      </header>

      <!-- 文件浏览器 -->
      <div class="content-area">
        <BrowserView />
      </div>

      <!-- 底部状态栏 -->
      <footer class="status-bar">
        <div class="status-bar-left">
          <!-- 扫描进度显示 -->
          <div v-if="fileStore.isScanning" class="scan-progress-container">
            <el-icon class="loading-icon"><Loading /></el-icon>
            <span class="scan-text">扫描中</span>
            <el-progress 
              :percentage="fileStore.scanProgress" 
              :show-text="false"
              :stroke-width="4"
              class="scan-progress-bar"
            />
            <span class="scan-count">{{ fileStore.scanCount }} / {{ fileStore.scanTotal }}</span>
            <span v-if="fileStore.scanCurrentFile" class="scan-file" :title="fileStore.scanCurrentFile">
              {{ truncateFileName(fileStore.scanCurrentFile) }}
            </span>
          </div>
          <span v-else-if="fileStore.isLoading" class="status-text">
            <el-icon class="loading-icon"><Loading /></el-icon> 加载中...
          </span>
        </div>
        <div class="status-bar-right">
          <span class="status-text" v-if="fileStore.selectedCount > 0">
            已选中 {{ fileStore.selectedCount }} 个文件 / 共 {{ fileStore.totalCount }} 个文件
          </span>
          <span class="status-text" v-else>
            共 {{ fileStore.totalCount }} 个文件
          </span>
        </div>
      </footer>
    </main>

    <!-- 详情面板 -->
    <DetailPanel v-if="appStore.detailPanelVisible && !isMobile" />
    
    <!-- 批量操作面板 -->
    <BatchOperations />
  </div>
</template>

<script setup lang="ts">
import {
  CollectionTag,
  Expand,
  Fold,
  Grid,
  List,
  ArrowRight,
  ArrowLeft,
  ArrowDown,
  Setting,
  Sunny,
  Moon,
  Sort,
  SortUp,
  SortDown,
  Loading,
  Refresh,
  Folder,
  Files,
} from '@element-plus/icons-vue'

import { useAppStore } from '../stores/app'
import { useFileStore } from '../stores/files'
import TagPanel from './TagPanel.vue'
import SearchBar from '../components/SearchBar.vue'
import BrowserView from './BrowserView.vue'
import DetailPanel from './DetailPanel.vue'
import BatchOperations from '../components/BatchOperations.vue'
import { ref, onMounted, onUnmounted } from 'vue'
import { wsClient } from '../api/websocket'
import { ElMessage } from 'element-plus'
import type { ScanProgressEvent, ScanCompletedEvent } from '../types'

const appStore = useAppStore()
const fileStore = useFileStore()

// 检测是否为移动设备
const isMobile = ref(false)

// 计算属性：根据屏幕宽度判断是否为移动设备
const checkIsMobile = () => {
  isMobile.value = window.innerWidth < 768
}

onMounted(() => {
  checkIsMobile()
  window.addEventListener('resize', checkIsMobile)
})

onUnmounted(() => {
  window.removeEventListener('resize', checkIsMobile)
})

// 排序选项映射
const sortOptions: Record<string, { field: string; desc: boolean; label: string }> = {
  name_asc: { field: 'name', desc: false, label: '名称升序' },
  name_desc: { field: 'name', desc: true, label: '名称降序' },
  modified_at_asc: { field: 'modified_at', desc: false, label: '日期升序' },
  modified_at_desc: { field: 'modified_at', desc: true, label: '日期降序' },
  size_asc: { field: 'size', desc: false, label: '大小升序' },
  size_desc: { field: 'size', desc: true, label: '大小降序' },
  duration_asc: { field: 'duration', desc: false, label: '时长升序' },
  duration_desc: { field: 'duration', desc: true, label: '时长降序' },
}

// 处理排序命令
const handleSortCommand = (command: string) => {
  const option = sortOptions[command]
  if (option) {
    fileStore.setSortBy(option.field)
    fileStore.sortDesc = option.desc
  }
}

// 获取当前排序图标
const getSortIcon = () => {
  if (fileStore.sortDesc) {
    return SortDown
  }
  return SortUp
}

// 获取当前排序标签
const getSortLabel = () => {
  const currentField = fileStore.sortBy
  const currentDesc = fileStore.sortDesc
  
  for (const [key, option] of Object.entries(sortOptions)) {
    if (option.field === currentField && option.desc === currentDesc) {
      return option.label
    }
  }
  
  // 默认显示
  const fieldLabels: Record<string, string> = {
    name: '名称',
    modified_at: '日期',
    size: '大小',
    duration: '时长',
  }
  const fieldLabel = fieldLabels[currentField] || currentField
  return currentDesc ? `${fieldLabel}降序` : `${fieldLabel}升序`
}

// 处理重新扫描
const handleRescan = () => {
  if (!appStore.currentWorkspace) {
    ElMessage.warning('请先选择工作区')
    return
  }
  
  // 连接 WebSocket
  wsClient.connect()
  
  // 开始扫描
  fileStore.startScanning()
  wsClient.startScan(appStore.currentWorkspace)
  ElMessage.success('开始扫描工作区...')
}

// 扫描事件处理 - 使用变量跟踪是否已显示提示
let scanCompletedShown = false
let scanErrorShown = false

onMounted(() => {
  checkIsMobile()
  window.addEventListener('resize', checkIsMobile)
  
  // 订阅扫描事件
  wsClient.connect()
  
  wsClient.on<ScanProgressEvent>('scan_progress', (data) => {
    fileStore.updateScanProgress(data.count, data.total, data.percentage, data.current_file)
  })
  
  wsClient.on<ScanCompletedEvent>('scan_completed', (data) => {
    // 避免重复显示提示
    if (scanCompletedShown) return
    scanCompletedShown = true
    
    fileStore.completeScanning()
    ElMessage.success(`扫描完成，共 ${data.total} 个文件`)
    // 刷新文件列表
    if (appStore.currentWorkspace) {
      fileStore.search({ root: appStore.currentWorkspace })
    }
    
    // 重置标志，允许下次扫描显示提示
    setTimeout(() => {
      scanCompletedShown = false
    }, 1000)
  })
  
  wsClient.on<{ message: string }>('scan_error', (error) => {
    // 避免重复显示提示
    if (scanErrorShown) return
    scanErrorShown = true
    
    fileStore.resetScanning()
    ElMessage.error(`扫描失败: ${error.message}`)
    
    // 重置标志
    setTimeout(() => {
      scanErrorShown = false
    }, 1000)
  })
})

onUnmounted(() => {
  window.removeEventListener('resize', checkIsMobile)
})

// 截断文件名显示
const truncateFileName = (path: string, maxLength: number = 30): string => {
  if (path.length <= maxLength) return path
  const fileName = path.split('/').pop() || path.split('\\').pop() || path
  if (fileName.length <= maxLength) return fileName
  return fileName.substring(0, maxLength - 3) + '...'
}

// 切换浏览模式
const toggleBrowseMode = () => {
  if (fileStore.browseMode === 'folder') {
    fileStore.setBrowseMode('all')
  } else {
    fileStore.setBrowseMode('folder')
  }
}
</script>

<style scoped>
.main-layout {
  display: flex;
  height: 100vh;
  overflow: hidden;
  background: linear-gradient(135deg, var(--color-bg-primary) 0%, var(--color-bg-secondary) 50%, var(--color-bg-tertiary) 100%);
}

.sidebar {
  width: var(--sidebar-width);
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  border-right: 1px solid var(--glass-border);
  background: var(--glass-bg);
  backdrop-filter: var(--glass-blur);
  -webkit-backdrop-filter: var(--glass-blur);
  transition: width 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  box-shadow: var(--glass-shadow);
}

.sidebar-content {
  flex: 1;
  overflow-y: auto;
}

/* 移动设备适配 */
@media (max-width: 768px) {
  .sidebar {
    flex-direction: row;
    height: 60px;
  }
  
  .sidebar-content {
    flex: 1;
    overflow-x: auto;
    overflow-y: hidden;
  }
  
  .sidebar.collapsed {
    width: 100% !important;
  }
}

.sidebar.collapsed {
  width: 60px;
}

.sidebar-header {
  padding: 16px;
  border-bottom: 1px solid var(--glass-border);
}

.logo {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 20px;
  font-weight: 700;
  color: var(--color-text-primary);
  margin: 0;
  letter-spacing: -0.5px;
}

.logo .el-icon {
  font-size: 28px;
  color: var(--color-accent);
  filter: drop-shadow(0 2px 4px rgba(99, 102, 241, 0.3));
}

.main-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  background: transparent;
  /* 确保主内容区有足够宽度，不被右侧面板过度压缩 */
  min-width: 600px;
}

.toolbar {
  height: var(--header-height);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 20px;
  border-bottom: 1px solid var(--glass-border);
  background: var(--glass-bg);
  backdrop-filter: var(--glass-blur);
  -webkit-backdrop-filter: var(--glass-blur);
  min-width: 0;
  flex-shrink: 0;
  overflow: hidden;
  gap: 12px;
  box-shadow: var(--shadow-sm);
}

/* 工具栏按钮样式优化 */
.toolbar :deep(.el-button) {
  border-radius: var(--radius-md);
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
}

.toolbar :deep(.el-button:hover) {
  transform: translateY(-1px);
  box-shadow: var(--shadow-md);
}

.toolbar :deep(.el-button--primary) {
  background: linear-gradient(135deg, var(--color-accent) 0%, var(--color-accent-hover) 100%);
  border: none;
  box-shadow: 0 4px 14px rgba(99, 102, 241, 0.4);
}

.toolbar :deep(.el-button--primary:hover) {
  box-shadow: 0 6px 20px rgba(99, 102, 241, 0.5);
  transform: translateY(-2px);
}

/* 文件夹浏览模式按钮样式 */
.browse-mode-btn {
  background: var(--color-bg-tertiary) !important;
  border: 1px solid var(--color-border) !important;
  color: var(--color-text-secondary) !important;
  transition: all 0.2s ease !important;
}

.browse-mode-btn:hover {
  background: var(--color-bg-secondary) !important;
  border-color: var(--color-accent) !important;
  color: var(--color-accent) !important;
}

.browse-mode-btn.active {
  background: linear-gradient(135deg, var(--color-accent) 0%, var(--color-accent-hover) 100%) !important;
  border-color: var(--color-accent) !important;
  color: white !important;
  box-shadow: 0 4px 14px rgba(99, 102, 241, 0.4);
}

.browse-mode-btn.active:hover {
  box-shadow: 0 6px 20px rgba(99, 102, 241, 0.5);
  transform: translateY(-2px);
}

/* 视图模式按钮组样式 */
.view-mode-group {
  display: flex;
}

.view-mode-group :deep(.el-button) {
  background: var(--color-bg-tertiary);
  border: 1px solid var(--color-border);
  color: var(--color-text-secondary);
  margin: 0 !important;
  border-radius: 0 !important;
  transition: all 0.2s ease;
}

/* 第一个按钮左边圆角 */
.view-mode-group :deep(.el-button:first-child) {
  border-top-left-radius: var(--radius-md) !important;
  border-bottom-left-radius: var(--radius-md) !important;
}

/* 最后一个按钮右边圆角 */
.view-mode-group :deep(.el-button:last-child) {
  border-top-right-radius: var(--radius-md) !important;
  border-bottom-right-radius: var(--radius-md) !important;
}

/* 中间按钮取消相邻边圆角（通过上面的 0 已经实现） */
.view-mode-group :deep(.el-button:hover) {
  background: var(--color-bg-secondary);
  border-color: var(--color-accent);
  color: var(--color-accent);
  z-index: 1;
}

.view-mode-group :deep(.el-button.active) {
  background: linear-gradient(135deg, var(--color-accent) 0%, var(--color-accent-hover) 100%);
  border-color: var(--color-accent);
  color: white;
  z-index: 2;
  box-shadow: 0 4px 14px rgba(99, 102, 241, 0.4);
}

.view-mode-group :deep(.el-button.active:hover) {
  box-shadow: 0 6px 20px rgba(99, 102, 241, 0.5);
  transform: translateY(-2px);
}

.toolbar-left,
.toolbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.toolbar-right {
  flex-wrap: nowrap;
  flex-shrink: 0;
  /* 右侧按钮组允许收缩 */
  min-width: 0;
}

.toolbar-left {
  /* 左侧区域可以收缩 */
  flex: 1;
  min-width: 0;
  overflow: hidden;
}

/* 排序按钮样式 */
.toolbar-right .el-dropdown {
  flex-shrink: 0;
}

.toolbar-right .el-button-group {
  flex-shrink: 0;
}

.sort-label {
  margin-left: 4px;
  font-size: 13px;
  white-space: nowrap;
}

/* 按钮标签样式 */
.btn-label {
  margin-left: 4px;
  font-size: 13px;
}

/* 响应式断点：中等屏幕 - 隐藏排序文字 */
@media (max-width: 1100px) {
  .sort-label {
    display: none;
  }
}

/* 响应式断点：较小屏幕 - 进一步压缩 */
@media (max-width: 900px) {
  .toolbar {
    padding: 0 12px;
    gap: 6px;
  }
  
  .toolbar-left,
  .toolbar-right {
    gap: 6px;
  }
}

/* 响应式断点：小屏幕 - 最小间距 */
@media (max-width: 768px) {
  .toolbar {
    padding: 0 8px;
    gap: 4px;
  }
  
  .toolbar-left,
  .toolbar-right {
    gap: 4px;
  }
  
  /* 隐藏搜索栏的占位空间 */
  .toolbar-left :deep(.search-bar) {
    max-width: 200px;
  }
}

/* 响应式断点：超小屏幕 - 隐藏部分按钮文字 */
@media (max-width: 640px) {
  .toolbar-left :deep(.search-bar) {
    max-width: 150px;
  }
}

/* 响应式断点：极窄屏幕 - 只保留图标 */
@media (max-width: 560px) {
  .toolbar {
    padding: 0 6px;
    gap: 2px;
  }
  
  .toolbar-left,
  .toolbar-right {
    gap: 2px;
  }
  
  .toolbar-left :deep(.search-bar) {
    max-width: 120px;
  }
}

.content-area {
  flex: 1;
  overflow: hidden;
  position: relative;
}

/* 底部状态栏 */
.status-bar {
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 16px;
  border-top: 1px solid var(--color-border);
  background: var(--color-bg-secondary);
  flex-shrink: 0;
  font-size: 12px;
  color: var(--color-text-secondary);
}

.status-bar-left,
.status-bar-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.status-text {
  display: flex;
  align-items: center;
  gap: 4px;
}

.loading-icon {
  animation: rotate 1s linear infinite;
}

@keyframes rotate {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

/* 扫描进度样式 */
.scan-progress-container {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  min-width: 0;
}

.scan-text {
  white-space: nowrap;
  color: var(--color-accent);
  font-weight: 500;
}

.scan-progress-bar {
  width: 100px;
  flex-shrink: 0;
}

.scan-count {
  white-space: nowrap;
  font-size: 11px;
  color: var(--color-text-secondary);
}

.scan-file {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 200px;
  font-size: 11px;
  color: var(--color-text-secondary);
  opacity: 0.8;
}

/* 响应式：小屏幕时调整状态栏 */
@media (max-width: 768px) {
  .status-bar {
    padding: 0 8px;
    font-size: 11px;
  }
  
  .scan-progress-bar {
    width: 60px;
  }
  
  .scan-file {
    max-width: 100px;
  }
}

@media (max-width: 480px) {
  .scan-file {
    display: none;
  }
}
</style>
