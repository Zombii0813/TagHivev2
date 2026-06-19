<template>
  <div class="app-shell">
    <AppMenuBar @command="handleMenuCommand" />
    <div class="main-layout" @dragover="handleLayoutDragOver">
    <!-- 侧边栏 -->
    <aside class="sidebar" :class="{ collapsed: appStore.sidebarCollapsed }">
      <div class="sidebar-header" :class="{ collapsed: appStore.sidebarCollapsed }">
        <h1 class="logo">
          <el-icon class="logo-icon"><CollectionTag /></el-icon>
          <span class="logo-text">TagHive</span>
        </h1>
      </div>

      <!-- 工作区管理面板 -->
      <div class="workspace-panel" v-show="!appStore.sidebarCollapsed">
        <!-- 全局视图按钮 -->
        <div
          class="workspace-item workspace-global"
          :class="{ active: appStore.isGlobalView }"
          @click="handleSetGlobalView()"
          :title="'全局视图（跨所有工作区）'"
          v-if="appStore.workspaces.length > 1"
        >
          <el-icon class="workspace-icon"><Grid /></el-icon>
          <span class="workspace-name">全局视图</span>
        </div>

        <!-- 工作区列表 -->
        <div
          v-for="ws in appStore.workspaces"
          :key="ws"
          class="workspace-item"
          :class="{ active: !appStore.isGlobalView && appStore.activeWorkspace === ws }"
          @click="handleSwitchWorkspace(ws)"
          :title="ws"
        >
          <el-icon class="workspace-icon"><Folder /></el-icon>
          <span class="workspace-name">{{ getWorkspaceName(ws) }}</span>
          <el-button
            class="workspace-remove-btn"
            :icon="Close"
            circle
            size="small"
            @click.stop="handleRemoveWorkspace(ws)"
            :title="'移除工作区'"
          />
        </div>

        <!-- 添加工作区按钮 -->
        <div class="workspace-add" @click="handleAddWorkspace" :title="'添加工作区'">
          <el-icon><Plus /></el-icon>
          <span>添加工作区</span>
        </div>
      </div>

      <div class="sidebar-content">
        <TagPanel />
      </div>

      <!-- 折叠状态下的标签图标列表 -->
      <div class="sidebar-collapsed-tags">
        <el-tooltip
          v-for="node in collapsedTagFlatList"
          :key="node.tag.id"
          :content="node.tag.name"
          placement="right"
          :show-after="200"
        >
          <div
            class="collapsed-tag-item"
            :class="{ selected: tagStore.isTagActive(node.tag.id), 'is-child': node.depth > 0 }"
            :style="{
              borderColor: node.tag.color,
              backgroundColor: node.tag.color + '25',
              '--tag-color': node.tag.color,
            }"
            @click="handleCollapsedTagClick(node.tag.id)"
          >
            <span v-if="node.tag.icon" class="collapsed-tag-emoji">{{ node.tag.icon }}</span>
            <span v-else class="collapsed-tag-dot" :style="{ backgroundColor: node.tag.color }"></span>
          </div>
        </el-tooltip>
      </div>
    </aside>

    <!-- 主内容区 -->
    <main class="main-content">
      <!-- 顶部工具栏 -->
      <header ref="toolbarRef" class="toolbar">
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
            :disabled="appStore.workspaces.length === 0"
            :title="appStore.isGlobalView ? '重新扫描所有工作区' : '重新扫描工作区'"
          />

          <!-- 排序下拉菜单 -->
          <el-dropdown @command="handleSortCommand" trigger="click">
            <el-button :title="'排序'">
              <el-icon>
                <component :is="getSortIcon()" />
              </el-icon>
              <span v-if="toolbarWide" class="sort-label">{{ getSortLabel() }}</span>
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

          <!-- 卡片大小调整 -->
          <el-popover
            v-if="fileStore.viewMode === 'grid'"
            :visible="sizeSliderVisible"
            placement="bottom"
            :width="220"
            @update:visible="sizeSliderVisible = $event"
          >
            <template #reference>
              <el-button
                :icon="ScaleToOriginal"
                circle
                :title="'调整卡片大小'"
                @click="sizeSliderVisible = !sizeSliderVisible"
              />
            </template>
            <div class="size-slider-panel">
              <span class="size-slider-label">卡片大小</span>
              <el-slider
                :model-value="fileStore.gridItemSize"
                :min="80"
                :max="320"
                :step="8"
                @update:model-value="fileStore.setGridItemSize($event as number)"
              />
              <span class="size-slider-value">{{ fileStore.gridItemSize }}px</span>
            </div>
          </el-popover>

          <!-- 窄屏时折叠到 more 菜单的按钮 -->
          <template v-if="toolbarWide">
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
          </template>
          <template v-else>
            <el-dropdown trigger="click" placement="bottom-end">
              <el-button :icon="MoreFilled" circle :title="'更多'" />
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item @click="appStore.toggleDetailPanel()">
                    <el-icon><component :is="appStore.detailPanelVisible ? ArrowRight : ArrowLeft" /></el-icon>
                    {{ appStore.detailPanelVisible ? '隐藏详情' : '显示详情' }}
                  </el-dropdown-item>
                  <el-dropdown-item @click="appStore.toggleTheme()">
                    <el-icon><component :is="appStore.isDark ? Sunny : Moon" /></el-icon>
                    {{ appStore.isDark ? '浅色模式' : '深色模式' }}
                  </el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </template>
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
          <template v-if="fileStore.selectedCount > 0">
            <span class="status-text">已选中 {{ fileStore.selectedCount }} 个 / 共 {{ fileStore.totalCount }} 个</span>
            <div class="status-bar-actions">
              <el-button size="small" @click="batchOpsRef?.openAddTags()">
                <el-icon><CollectionTag /></el-icon>
                批量添加标签
              </el-button>
              <el-button size="small" type="danger" @click="batchOpsRef?.confirmDelete()">
                <el-icon><Delete /></el-icon>
                批量删除
              </el-button>
              <el-button size="small" @click="fileStore.clearSelection">取消选择</el-button>
            </div>
          </template>
          <span v-else class="status-text">共 {{ fileStore.totalCount }} 个文件</span>
        </div>
      </footer>
    </main>

    <!-- 详情面板（始终渲染，通过 CSS 动画控制展开/收起） -->
    <DetailPanel
      v-if="!isMobile"
      :class="{ visible: appStore.detailPanelVisible }"
    />

    <!-- 批量操作对话框 -->
    <BatchOperations ref="batchOpsRef" />

    <!-- 日志查看器（菜单栏 工具 → 查看日志 调起） -->
    <LogViewer ref="logViewerRef" />

    <!-- 设置弹窗（菜单栏 工具 → 设置 调起） -->
    <SettingsDialog ref="settingsDialogRef" />

    <!-- 标签包导入/导出向导（菜单栏 文件 → 导入/导出 调起） -->
    <TagTransferDialog
      v-model="showTagTransfer"
      :workspace="appStore.activeWorkspace || ''"
      :initial-action="tagTransferAction"
      @imported="onTagsImported"
    />
    </div>
  </div>
</template>

<script setup lang="ts">
import {
  CollectionTag,
  Delete,
  Expand,
  Fold,
  Grid,
  List,
  ArrowRight,
  ArrowLeft,
  ArrowDown,
  Sunny,
  Moon,
  Sort,
  SortUp,
  SortDown,
  Loading,
  Refresh,
  Folder,
  ScaleToOriginal,
  MoreFilled,
  Plus,
  Close,
} from '@element-plus/icons-vue'

import { useAppStore } from '../stores/app'
import { useFileStore } from '../stores/files'
import { useTagStore } from '../stores/tags'
import TagPanel from './TagPanel.vue'
import SearchBar from '../components/SearchBar.vue'
import BrowserView from './BrowserView.vue'
import DetailPanel from './DetailPanel.vue'
import BatchOperations from '../components/BatchOperations.vue'
import AppMenuBar from '../components/AppMenuBar.vue'
import LogViewer from '../components/LogViewer.vue'
import SettingsDialog from '../components/SettingsDialog.vue'
import TagTransferDialog from './TagTransferDialog.vue'
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { wsClient } from '../api/websocket'
import { ElMessage } from 'element-plus'
import type { ScanProgressEvent, ScanCompletedEvent } from '../types'
import type { TagTreeNode } from '../stores/tags'
import { isTagDragInProgress } from '../utils/drag'

const batchOpsRef = ref<InstanceType<typeof BatchOperations> | null>(null)
const logViewerRef = ref<InstanceType<typeof LogViewer> | null>(null)
const settingsDialogRef = ref<InstanceType<typeof SettingsDialog> | null>(null)
const showTagTransfer = ref(false)
const tagTransferAction = ref<'export' | 'import' | null>(null)

function openTagTransfer(action: 'export' | 'import') {
  if (!appStore.activeWorkspace) {
    ElMessage.warning('请先选择工作区')
    return
  }
  tagTransferAction.value = action
  showTagTransfer.value = true
}

function onTagsImported() {
  // 导入完成后，主动让 TagPanel 重新拉取当前工作区的标签
  window.dispatchEvent(new CustomEvent('taghive:tags-imported'))
}
const appStore = useAppStore()
const fileStore = useFileStore()
const tagStore = useTagStore()

// 折叠态标签图标按层级 DFS 平铺：父→子→孙，忽略 expandedTagIds（折叠态需要始终展示全部）
const collapsedTagFlatList = computed<TagTreeNode[]>(() => {
  const result: TagTreeNode[] = []
  const walk = (nodes: TagTreeNode[]) => {
    for (const node of nodes) {
      result.push(node)
      if (node.children.length > 0) walk(node.children)
    }
  }
  walk(tagStore.tagTree)
  return result
})

// 全局 dragover 处理：标签拖拽经过中间层时防止显示禁止图标
function handleLayoutDragOver(event: DragEvent) {
  if (isTagDragInProgress()) {
    event.preventDefault()
    if (event.dataTransfer) {
      event.dataTransfer.dropEffect = 'copy'
    }
  }
}

const sizeSliderVisible = ref(false)
const toolbarRef = ref<HTMLElement | null>(null)
const toolbarWidth = ref(800)

// 工具栏宽度 >= 720px 时显示完整按钮，否则折叠到 more 菜单
const toolbarWide = computed(() => toolbarWidth.value >= 720)

// 检测是否为移动设备
const isMobile = ref(false)

// 计算属性：根据屏幕宽度判断是否为移动设备
const checkIsMobile = () => {
  isMobile.value = window.innerWidth < 768
}

let toolbarObserver: ResizeObserver | null = null

onMounted(() => {
  checkIsMobile()
  window.addEventListener('resize', checkIsMobile)

  // 监听工具栏宽度
  if (toolbarRef.value) {
    toolbarObserver = new ResizeObserver((entries) => {
      toolbarWidth.value = entries[0].contentRect.width
    })
    toolbarObserver.observe(toolbarRef.value)
    toolbarWidth.value = toolbarRef.value.clientWidth
  }
})

onUnmounted(() => {
  window.removeEventListener('resize', checkIsMobile)
  toolbarObserver?.disconnect()
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
  
  for (const [, option] of Object.entries(sortOptions)) {
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
  if (appStore.isGlobalView) {
    // 全局视图：扫描所有工作区
    if (appStore.workspaces.length === 0) {
      ElMessage.warning('请先添加工作区')
      return
    }
    wsClient.connect()
    fileStore.startScanning()
    for (const ws of appStore.workspaces) {
      wsClient.startScan(ws)
    }
    ElMessage.success('开始扫描所有工作区...')
  } else {
    if (!appStore.activeWorkspace) {
      ElMessage.warning('请先选择工作区')
      return
    }
    wsClient.connect()
    fileStore.startScanning()
    wsClient.startScan(appStore.activeWorkspace)
    ElMessage.success('开始扫描工作区...')
  }
}

// 顶部菜单栏命令分发
function handleMenuCommand(command: string) {
  switch (command) {
    case 'file:add-workspace':
      handleAddWorkspace()
      break
    case 'file:rescan':
      handleRescan()
      break
    case 'file:exit':
      window.close()
      break
    case 'edit:focus-search': {
      const el = document.querySelector<HTMLInputElement>('.search-bar input')
      el?.focus()
      el?.select()
      break
    }
    case 'edit:manage-tags': {
      if (appStore.sidebarCollapsed) appStore.toggleSidebar()
      const btn = document.querySelector<HTMLElement>('.tag-panel .panel-header .header-actions .el-button')
      btn?.click()
      break
    }
    case 'tools:view-logs':
      logViewerRef.value?.open()
      break
    case 'tools:settings':
      settingsDialogRef.value?.open()
      break
    case 'file:export-tags':
      openTagTransfer('export')
      break
    case 'file:import-tags':
      openTagTransfer('import')
      break
    case 'help:about':
      ElMessage.info('TagHive · 基于标签的文件管理工具')
      break
    default:
      ElMessage.info('该功能尚未实现')
  }
}

// ===== 工作区管理 =====
function getWorkspaceName(ws: string): string {
  // 取路径最后一段作为显示名
  return ws.replace(/\\/g, '/').split('/').filter(Boolean).pop() || ws
}

async function handleAddWorkspace() {
  // 记录调用前的工作区列表，用于判断本次是否新增
  const existingBefore = new Set(appStore.workspaces)
  const selected = await appStore.selectFolder()
  if (selected) {
    // 切换到新工作区并刷新视图
    refreshForWorkspace()
    // 仅对“新添加的工作区”自动扫描；已存在的工作区只切换不重复扫描
    if (!existingBefore.has(selected)) {
      wsClient.connect()
      fileStore.startScanning()
      wsClient.startScan(selected)
      ElMessage.success('已添加工作区，开始扫描...')
    }
  }
}

function handleSwitchWorkspace(ws: string) {
  appStore.switchWorkspace(ws)
  refreshForWorkspace()
}

function handleSetGlobalView() {
  appStore.setGlobalView(true)
  refreshForWorkspace()
}

async function handleRemoveWorkspace(ws: string) {
  appStore.removeWorkspace(ws)
  refreshForWorkspace()
}

function refreshForWorkspace() {
  const root = appStore.currentWorkspace || undefined
  tagStore.loadTags(root)
  tagStore.clearSelection()
  if (fileStore.browseMode === 'folder' && !root && !appStore.isGlobalView) {
    fileStore.setBrowseMode('all')
  }
  fileStore.search({ root })
}

// 扫描事件处理 - 使用变量跟踪是否已显示提示
let scanCompletedShown = false
let scanErrorShown = false

// 保存 wsClient.on 返回的取消订阅函数，便于卸载时清理
const wsUnsubscribers: Array<() => void> = []

onMounted(() => {
  // 订阅扫描事件
  wsClient.connect()

  wsUnsubscribers.push(
    wsClient.on<ScanProgressEvent>('scan_progress', (data) => {
      fileStore.updateScanProgress(data.count, data.total, data.percentage, data.current_file)
    })
  )

  wsUnsubscribers.push(
    wsClient.on<ScanCompletedEvent>('scan_completed', (data) => {
      // 避免重复显示提示
      if (scanCompletedShown) return
      scanCompletedShown = true

      fileStore.completeScanning()
      ElMessage.success(`扫描完成，共 ${data.total} 个文件`)
      // 刷新文件列表：保持当前浏览模式
      const root = appStore.currentWorkspace || undefined
      if (fileStore.browseMode === 'folder' && root) {
        // 文件夹浏览模式：重新加载当前所在目录（若无则回到工作区根目录）
        const targetPath = fileStore.currentFolderPath || root
        fileStore.loadFolderContents(targetPath)
      } else {
        fileStore.search({ root })
      }

      // 重置标志，允许下次扫描显示提示
      setTimeout(() => {
        scanCompletedShown = false
      }, 1000)
    })
  )

  wsUnsubscribers.push(
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
  )
})

onUnmounted(() => {
  // 取消所有 WebSocket 事件订阅，避免组件多次挂载导致监听器累积
  for (const off of wsUnsubscribers) off()
  wsUnsubscribers.length = 0
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

// 折叠状态下点击标签图标：切换选中并触发搜索
function handleCollapsedTagClick(tagId: number) {
  const multi = false
  const root = appStore.currentWorkspace || undefined
  if (tagStore.selectedTagIds.has(tagId) && tagStore.selectedTagIds.size === 1) {
    tagStore.clearSelection()
    fileStore.search({ root })
    return
  }
  tagStore.selectTag(tagId, multi)
  if (tagStore.selectedTagIds.size > 0) {
    fileStore.search({
      root,
      tags: Array.from(tagStore.effectiveTagIds),
      match_all_tags: false,
    })
  }
}
</script>

<style scoped>
.app-shell {
  display: flex;
  flex-direction: column;
  height: 100vh;
  overflow: hidden;
  background: linear-gradient(135deg, var(--color-bg-primary) 0%, var(--color-bg-secondary) 50%, var(--color-bg-tertiary) 100%);
}

.main-layout {
  display: flex;
  flex: 1 1 0;
  min-height: 0;
  overflow: hidden;
}

/* ===== 工作区管理面板 ===== */
.workspace-panel {
  padding: 6px 8px;
  border-bottom: 1px solid var(--glass-border);
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex-shrink: 0;
}

.workspace-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 8px;
  border-radius: var(--radius-md);
  cursor: pointer;
  font-size: 13px;
  color: var(--color-text-secondary);
  transition: all 0.15s ease;
  position: relative;
  min-width: 0;
}

.workspace-item:hover {
  background: var(--color-bg-secondary);
  color: var(--color-text-primary);
}

.workspace-item.active {
  background: linear-gradient(135deg, var(--color-accent) 0%, var(--color-accent-hover) 100%);
  color: white;
}

.workspace-item.active .workspace-remove-btn {
  color: white;
}

.workspace-global {
  font-weight: 500;
}

.workspace-icon {
  flex-shrink: 0;
  font-size: 14px;
}

.workspace-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.workspace-remove-btn {
  flex-shrink: 0;
  width: 18px !important;
  height: 18px !important;
  padding: 0 !important;
  border: none !important;
  background: transparent !important;
  color: var(--color-text-secondary) !important;
  opacity: 0;
  transition: opacity 0.15s ease;
  font-size: 10px !important;
}

.workspace-item:hover .workspace-remove-btn {
  opacity: 0.7;
}

.workspace-remove-btn:hover {
  opacity: 1 !important;
  background: rgba(0,0,0,0.1) !important;
}

.workspace-add {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 8px;
  border-radius: var(--radius-md);
  cursor: pointer;
  font-size: 13px;
  color: var(--color-text-secondary);
  transition: all 0.15s ease;
  border: 1px dashed var(--color-border);
  margin-top: 2px;
}

.workspace-add:hover {
  border-color: var(--color-accent);
  color: var(--color-accent);
  background: rgba(99, 102, 241, 0.05);
}

/* ===== 侧边栏 ===== */
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
  overflow: hidden;
  position: relative;
}

.sidebar.collapsed {
  width: 56px;
}

.sidebar-header {
  display: flex;
  align-items: center;
  padding: 0 14px;
  height: var(--header-height);
  border-bottom: 1px solid var(--glass-border);
  flex-shrink: 0;
  overflow: hidden;
}

.sidebar-header.collapsed {
  justify-content: center;
  padding: 0;
}

.logo {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 18px;
  font-weight: 700;
  color: var(--color-text-primary);
  margin: 0;
  letter-spacing: -0.5px;
  white-space: nowrap;
  overflow: hidden;
}

.logo-icon {
  font-size: 26px;
  color: var(--color-accent);
  filter: drop-shadow(0 2px 4px rgba(99, 102, 241, 0.3));
  flex-shrink: 0;
}

.logo-text {
  opacity: 1;
  transition: opacity 0.2s ease;
  overflow: hidden;
}

.sidebar.collapsed .logo-text {
  opacity: 0;
  width: 0;
  pointer-events: none;
}

.sidebar-content {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  /* 折叠时内容淡出 */
  transition: opacity 0.2s ease;
}

.sidebar.collapsed .sidebar-content {
  opacity: 0;
  pointer-events: none;
}

/* 折叠标签图标列表 */
.sidebar-collapsed-tags {
  position: absolute;
  top: var(--header-height);
  left: 0;
  right: 0;
  bottom: 0;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 8px 4px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.2s ease;
}

.sidebar.collapsed .sidebar-collapsed-tags {
  opacity: 1;
  pointer-events: auto;
}

.collapsed-tag-item {
  width: 36px;
  height: 36px;
  border-radius: 8px;
  /* 预占 2px 边框，避免选中态切换时尺寸变化导致竖向位移 */
  border: 2px solid transparent;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  flex-shrink: 0;
  box-sizing: border-box;
  transition: background-color 0.15s ease, box-shadow 0.15s ease, opacity 0.15s ease;
}

.collapsed-tag-item:hover {
  opacity: 0.85;
}

.collapsed-tag-item.selected {
  /* 在已有 2px 边框内侧叠 1px，等效"加粗"，但不改变盒模型 */
  box-shadow:
    inset 0 0 0 1px var(--tag-color, currentColor),
    0 0 0 2px color-mix(in srgb, var(--tag-color, currentColor) 20%, transparent);
}

/* 子标签视觉降级：透明度略低，仍与父标签同尺寸、同基线 */
.collapsed-tag-item.is-child {
  opacity: 0.78;
}

.collapsed-tag-item.is-child:hover,
.collapsed-tag-item.is-child.selected {
  opacity: 1;
}

.collapsed-tag-emoji {
  font-size: 18px;
  line-height: 1;
}

.collapsed-tag-dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
}

/* 移动设备适配 */
@media (max-width: 768px) {
  .sidebar {
    flex-direction: row;
    height: 60px;
    width: 100% !important;
  }

  .sidebar-content {
    flex: 1;
    overflow-x: auto;
    overflow-y: hidden;
  }
}

/* ===== 主内容区 ===== */
.main-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  background: transparent;
}

/* ===== 工具栏 ===== */
.toolbar {
  height: var(--header-height);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 16px;
  border-bottom: 1px solid var(--glass-border);
  background: var(--glass-bg);
  backdrop-filter: var(--glass-blur);
  -webkit-backdrop-filter: var(--glass-blur);
  flex-shrink: 0;
  overflow: hidden;
  gap: 8px;
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

.toolbar-left,
.toolbar-right {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

.toolbar-left {
  flex: 1;
  min-width: 0;
  overflow: hidden;
}

.toolbar-right {
  flex-wrap: nowrap;
  min-width: 0;
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
  flex-shrink: 0;
}

.view-mode-group :deep(.el-button) {
  background: var(--color-bg-tertiary);
  border: 1px solid var(--color-border);
  color: var(--color-text-secondary);
  margin: 0 !important;
  border-radius: 0 !important;
  transition: all 0.2s ease;
}

.view-mode-group :deep(.el-button:first-child) {
  border-top-left-radius: var(--radius-md) !important;
  border-bottom-left-radius: var(--radius-md) !important;
}

.view-mode-group :deep(.el-button:last-child) {
  border-top-right-radius: var(--radius-md) !important;
  border-bottom-right-radius: var(--radius-md) !important;
}

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

/* 卡片大小滑块 */
.size-slider-panel {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
}

.size-slider-label {
  font-size: 12px;
  color: var(--color-text-secondary);
  white-space: nowrap;
}

.size-slider-value {
  font-size: 12px;
  color: var(--color-text-secondary);
  white-space: nowrap;
  min-width: 36px;
  text-align: right;
}

/* ===== 内容区 ===== */
.content-area {
  flex: 1;
  overflow: hidden;
  position: relative;
}

/* ===== 底部状态栏 ===== */
.status-bar {
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: nowrap;
  padding: 0 16px;
  gap: 12px;
  border-top: 1px solid var(--color-border);
  background: var(--color-bg-secondary);
  flex-shrink: 0;
  font-size: 12px;
  color: var(--color-text-secondary);
  overflow: hidden;
}

.status-bar-left {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1 1 0;
  min-width: 0;
}

.status-bar-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
  max-width: 100%;
}

.status-bar-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

.status-text {
  display: flex;
  align-items: center;
  gap: 4px;
  white-space: nowrap;
}

.loading-icon {
  animation: rotate 1s linear infinite;
}

@keyframes rotate {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.scan-progress-container {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1 1 0;
  min-width: 0;
  overflow: hidden;
}

.scan-text {
  white-space: nowrap;
  color: var(--color-accent);
  font-weight: 500;
  flex-shrink: 0;
}

.scan-progress-bar {
  width: 100px;
  flex-shrink: 0;
}

.scan-count {
  white-space: nowrap;
  font-size: 11px;
  color: var(--color-text-secondary);
  flex-shrink: 0;
}

.scan-file {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  /* 占据剩余空间并允许压缩到 0；右侧按钮组宽度变化时不会再撑高状态栏 */
  flex: 1 1 0;
  min-width: 0;
  font-size: 11px;
  color: var(--color-text-secondary);
  opacity: 0.8;
}

@media (max-width: 768px) {
  .status-bar {
    padding: 0 8px;
    font-size: 11px;
  }

  .scan-progress-bar {
    width: 60px;
  }
}

@media (max-width: 480px) {
  .scan-file {
    display: none;
  }
}
</style>
