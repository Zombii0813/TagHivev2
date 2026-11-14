<template>
  <div class="app-shell" :class="{ 'density-compact': appStore.compactDensity, 'is-resizing': resizing }" :style="{ '--sidebar-width': appStore.sidebarWidth + 'px', '--detail-panel-width': appStore.detailWidth + 'px' }">
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
      <Transition name="th-fade">
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

        <!-- 工作区列表：增删时条目展开/收起，其余条目随高度变化自然让位 -->
        <TransitionGroup name="ws-item" tag="div" class="workspace-list">
        <div
          v-for="ws in appStore.workspaces"
          :key="ws"
          class="workspace-item"
          :class="{ active: !appStore.isGlobalView && appStore.activeWorkspace === ws, 'drop-active': dropActiveWs === ws }"
          @click="handleSwitchWorkspace(ws)"
          :title="ws"
          @dragover="onWorkspaceDragOver(ws, $event)"
          @dragleave="onWorkspaceDragLeave(ws)"
          @drop="onWorkspaceDrop(ws, $event)"
        >
          <el-icon class="workspace-icon"><Folder /></el-icon>
          <span class="workspace-name">{{ getWorkspaceName(ws) }}</span>
          <!-- 与该工作区标签页同色的圆点，便于在标签栏中对应 -->
          <span class="workspace-dot" :style="{ background: workspaceDot(ws) }" />
          <el-button
            class="workspace-remove-btn"
            :icon="Close"
            circle
            size="small"
            @click.stop="handleRemoveWorkspace(ws)"
            :title="'移除工作区'"
          />
        </div>
        </TransitionGroup>

        <!-- 添加工作区按钮 -->
        <div class="workspace-add" @click="handleAddWorkspace" :title="'添加工作区'">
          <el-icon><Plus /></el-icon>
          <span>添加工作区</span>
        </div>
      </div>
      </Transition>

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

    <div v-if="!appStore.sidebarCollapsed" class="panel-resizer" role="separator" tabindex="0" aria-label="调整侧栏宽度" aria-orientation="vertical" :aria-valuenow="appStore.sidebarWidth" :aria-valuemin="200" :aria-valuemax="360" @pointerdown="startResize('sidebar', $event)" @keydown="resizeKey('sidebar', $event)" @dblclick="appStore.sidebarWidth = 240" />
    <!-- 主内容区 -->
    <main class="main-content">
      <!-- 顶部工具栏 -->
      <header ref="toolbarRef" class="toolbar" :class="{ compact: !toolbarWide }">
        <div class="toolbar-left">
          <el-button
            v-if="!isMobile"
            :icon="appStore.sidebarCollapsed ? Expand : Fold"
            circle
            aria-label="展开或收起侧栏"
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

          <!-- 浏览模式切换：点击展开下拉，横向图标选择 -->
          <el-dropdown
            ref="browseModeDropdownRef"
            trigger="click"
            popper-class="browse-mode-dropdown"
          >
            <el-button
              :class="['browse-mode-btn', { active: fileStore.browseMode !== 'all' }]"
              :icon="browseModeIcon"
              circle
              :title="`浏览模式：${currentBrowseModeLabel}`"
            />
            <template #dropdown>
              <div class="browse-mode-options">
                <button
                  v-for="opt in browseModeOptions"
                  :key="opt.value"
                  type="button"
                  :class="['browse-mode-option', { active: fileStore.browseMode === opt.value }]"
                  :title="opt.label"
                  @click="handleSelectBrowseMode(opt.value)"
                >
                  <el-icon :size="18"><component :is="opt.icon" /></el-icon>
                  <span class="browse-mode-option-label">{{ opt.label }}</span>
                </button>
              </div>
            </template>
          </el-dropdown>

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
              <el-switch v-model="appStore.compactDensity" active-text="紧凑密度" />
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

      <!-- 浏览标签页栏 -->
      <BrowserTabsBar />
      <BrowserContextBar
        @clear-filters="clearFilters"
        @manage-tags="batchOpsRef?.openAddTags()"
        @delete-selected="batchOpsRef?.confirmDelete()"
      />

      <!-- 文件浏览器 -->
      <div class="content-area">
        <BrowserView @delete-selected="batchOpsRef?.confirmDelete($event)" />
      </div>

      <Transition name="bar-expand">
        <div v-if="fileStore.activeTab.queryError" class="query-error" role="alert">
          {{ fileStore.activeTab.queryError }}
          <el-button size="small" @click="fileStore.reloadCurrentView()">重试</el-button>
        </div>
      </Transition>
      <!-- 底部状态栏 -->
      <footer class="status-bar">
        <div class="status-bar-left">
          <BackgroundTasks />
          <Transition name="th-fade">
            <span v-if="fileStore.isLoading && !fileStore.isScanning" class="status-text loading-status">
              <el-icon class="loading-icon"><Loading /></el-icon> 加载中...
            </span>
          </Transition>
        </div>
        <div class="status-bar-right">
          <span class="file-count" :title="`已加载 ${fileStore.files.length} / 共 ${fileStore.totalCount} 个文件`">已加载 {{ fileStore.files.length }} / 共 {{ fileStore.totalCount }} 个文件</span>
        </div>
      </footer>
    </main>

    <!-- 隐藏详情时卸载组件，释放媒体流与播放器资源。
         调节条与面板同处一个停靠容器，进出场动画作用在容器上：
         只做位移滑入/滑出，中列宽度在过程中只变化一次（见 .detail-slide-* 样式说明）。 -->
    <Transition name="detail-slide">
      <div v-if="detailShown" class="detail-dock">
        <div class="panel-resizer detail-resizer" role="separator" tabindex="0" aria-label="调整详情宽度" aria-orientation="vertical" :aria-valuenow="appStore.detailWidth" :aria-valuemin="280" :aria-valuemax="480" @pointerdown="startResize('detail', $event)" @keydown="resizeKey('detail', $event)" @dblclick="appStore.detailWidth = 320" />
        <DetailPanel class="visible" />
      </div>
    </Transition>

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
  FolderOpened,
  Menu,
  Connection,
  Operation,
  ScaleToOriginal,
  MoreFilled,
  Plus,
  Close,
} from '@element-plus/icons-vue'

import { useAppStore } from '../stores/app'
import { useFileStore } from '../stores/files'
import { useTagStore } from '../stores/tags'
import TagPanel from './TagPanel.vue'
import BackgroundTasks from '../components/BackgroundTasks.vue'
import BrowserContextBar from '../components/BrowserContextBar.vue'
import SearchBar from '../components/SearchBar.vue'
import BrowserTabsBar from '../components/BrowserTabsBar.vue'
import { MAX_TABS } from '../stores/browserTabs'
import { workspacePalette } from '../utils/workspaceColor'
const BrowserView = defineAsyncComponent(() => import('./BrowserView.vue'))
const DetailPanel = defineAsyncComponent(() => import('./DetailPanel.vue'))
import BatchOperations from '../components/BatchOperations.vue'
import AppMenuBar from '../components/AppMenuBar.vue'
import LogViewer from '../components/LogViewer.vue'
import SettingsDialog from '../components/SettingsDialog.vue'
import TagTransferDialog from './TagTransferDialog.vue'
import { defineAsyncComponent, ref, computed, markRaw, onMounted, onUnmounted } from 'vue'
import { wsClient } from '../api/websocket'
import { ElMessage } from 'element-plus'
import type { ScanProgressEvent, ScanCompletedEvent } from '../types'
import type { TagTreeNode } from '../stores/tags'
import { isTagDragInProgress } from '../utils/drag'
import { hasItemDrag, getItemDrag, clearItemDragState } from '../utils/dragItems'
import { fileApi } from '../api/files'
import { folderApi } from '../api/folders'

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
const toolbarWide = computed(() => toolbarWidth.value >= 840)

// 检测是否为移动设备
const isMobile = ref(false)

// 详情栏是否显示：启用详情、有选择且非移动宽度
const detailShown = computed(() => !isMobile.value && appStore.detailPanelVisible && fileStore.hasSelection)

// 是否正在拖动面板调节条：期间关闭面板宽度过渡，保证宽度紧跟指针
const resizing = ref(false)

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

function clearFilters() {
  fileStore.activeTab.searchText = ''
  fileStore.activeTab.searchType = ''
  tagStore.clearSelection()
  void fileStore.reloadCurrentView()
}
function changePanelWidth(panel: 'sidebar' | 'detail', value: number) {
  if (panel === 'sidebar') appStore.sidebarWidth = Math.max(200, Math.min(360, value))
  else appStore.detailWidth = Math.max(280, Math.min(480, value))
}
function resizeKey(panel: 'sidebar' | 'detail', event: KeyboardEvent) {
  if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return
  event.preventDefault()
  const current = panel === 'sidebar' ? appStore.sidebarWidth : appStore.detailWidth
  const direction = (event.key === 'ArrowRight' ? 1 : -1) * (panel === 'detail' ? -1 : 1)
  changePanelWidth(panel, event.key === 'Home' ? 0 : event.key === 'End' ? 999 : current + direction * 16)
}
function startResize(panel: 'sidebar' | 'detail', event: PointerEvent) {
  event.preventDefault()
  const start = event.clientX
  const width = panel === 'sidebar' ? appStore.sidebarWidth : appStore.detailWidth
  const target = event.currentTarget as HTMLElement
  target.setPointerCapture(event.pointerId)
  resizing.value = true
  const move = (e: PointerEvent) => changePanelWidth(panel, width + (e.clientX - start) * (panel === 'detail' ? -1 : 1))
  const stop = () => { resizing.value = false; target.removeEventListener('pointermove', move); target.removeEventListener('lostpointercapture', stop) }
  target.addEventListener('pointermove', move)
  target.addEventListener('lostpointercapture', stop)
}

// 处理排序命令
const handleSortCommand = (command: string) => {
  const option = sortOptions[command]
  if (option) {
    // 明确指定字段与方向，由 store 按当前浏览上下文（蜂巢/树窗层级、
    // 标签过滤或全部文件）重载，避免跳回全部文件视图
    fileStore.setSort(option.field, option.desc)
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
    case 'edit:select-all':
      fileStore.selectAll()
      break
    case 'edit:clear-selection':
      fileStore.clearSelection()
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

/** 工作区圆点记号颜色，与该工作区标签页底色同色相 */
function workspaceDot(ws: string): string {
  return workspacePalette(ws, appStore.isDark).dot
}

async function handleAddWorkspace() {
  // 记录调用前的工作区列表，用于判断本次是否新增
  const existingBefore = new Set(appStore.workspaces)
  const selected = await appStore.selectFolder()
  if (selected) {
    // 与点击已有工作区一致：为新工作区开一个标签页，不动其它标签页
    await handleSwitchWorkspace(selected)
    // 仅对“新添加的工作区”自动扫描；已存在的工作区只切换不重复扫描
    if (!existingBefore.has(selected)) {
      wsClient.connect()
      fileStore.startScanning()
      wsClient.startScan(selected)
      ElMessage.success('已添加工作区，开始扫描...')
    }
  }
}

/**
 * 点击侧栏工作区：新建一个该工作区的标签页，已有标签页不受影响。
 *
 * 标签页与工作区解绑后，工作区不再是全局状态，而是标签页的属性；
 * 若已存在该工作区的标签页则直接切过去，避免重复点击堆积标签页。
 */
async function handleSwitchWorkspace(ws: string) {
  const existing = fileStore.tabList.find(
    t => !t.isGlobalView && t.workspace === ws
  )
  if (existing) {
    await fileStore.switchTab(existing.id)
    return
  }
  await openWorkspaceTab(ws, false)
}

/**
 * 新建指定工作区的标签页并切换过去。
 *
 * @param ws 工作区根路径；全局视图时传空串
 * @param isGlobalView 是否为跨工作区全局视图
 */
async function openWorkspaceTab(ws: string, isGlobalView: boolean) {
  // appStore 同步、标签树重载与数据加载都由 addTab → switchTab 统一完成，
  // 这里只负责建标签页，避免两处各做一遍引发重复加载
  const created = await fileStore.addTab({
    workspace: ws,
    isGlobalView,
    currentFolderPath: isGlobalView ? '' : ws,
  })
  if (!created) {
    ElMessage.warning(`标签页数量已达上限（${MAX_TABS} 个），请先关闭部分标签页`)
  }
}

// ─── 拖拽文件/文件夹到侧栏工作区：移动/复制到该工作区的记忆层级 ───
const dropActiveWs = ref('')

// 解析目标目录：优先该工作区上次浏览层级（须仍位于该工作区下），否则工作区根
function resolveWsTargetDir(ws: string): string {
  const remembered = fileStore.getRememberedFolder(ws)
  if (remembered) {
    const r = remembered.replace(/\\/g, '/')
    const root = ws.replace(/\\/g, '/')
    if (r === root || r.startsWith(root + '/')) return remembered
  }
  return ws
}

function onWorkspaceDragOver(ws: string, event: DragEvent) {
  const drag = getItemDrag()
  if (!hasItemDrag(event) && !drag) return
  // 文件夹拖到自身工作区根不允许（无意义/防自包含由后端兜底）
  event.preventDefault()
  dropActiveWs.value = ws
  if (event.dataTransfer) {
    event.dataTransfer.dropEffect = event.ctrlKey || event.metaKey ? 'copy' : 'move'
  }
}

function onWorkspaceDragLeave(ws: string) {
  if (dropActiveWs.value === ws) dropActiveWs.value = ''
}

async function onWorkspaceDrop(ws: string, event: DragEvent) {
  if (!hasItemDrag(event) && !getItemDrag()) return
  event.preventDefault()
  dropActiveWs.value = ''
  const drag = getItemDrag()
  clearItemDragState()
  if (!drag) return
  const copy = event.ctrlKey || event.metaKey
  const targetDir = resolveWsTargetDir(ws)
  try {
    if (drag.kind === 'file' && drag.fileIds?.length) {
      if (copy) {
        const r = await fileApi.copy(drag.fileIds, targetDir, ws)
        ElMessage.success(`已复制 ${r.files.length} 个文件到「${getWorkspaceName(ws)}」`)
      } else {
        const r = await fileApi.move(drag.fileIds, targetDir, ws)
        ElMessage.success(`已移动 ${r.files.length} 个文件到「${getWorkspaceName(ws)}」`)
      }
    } else if (drag.kind === 'folder' && drag.folderPath) {
      const src = drag.folderPath.replace(/\\/g, '/')
      const dst = targetDir.replace(/\\/g, '/')
      if (dst === src || dst.startsWith(src + '/')) {
        ElMessage.warning('不能移动到文件夹自身或其子目录')
        return
      }
      if (copy) {
        await folderApi.copyFolder(drag.folderPath, targetDir)
        ElMessage.success(`已复制文件夹到「${getWorkspaceName(ws)}」`)
      } else {
        await folderApi.moveFolder(drag.folderPath, targetDir, ws)
        ElMessage.success(`已移动文件夹到「${getWorkspaceName(ws)}」`)
      }
    }
    // 移动会从源（通常是当前工作区）移走文件，复制也可能落入当前工作区，
    // 统一刷新当前工作区列表，确保卡片及时更新。
    reloadCurrentFiles()
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || (copy ? '复制失败' : '移动失败'))
  }
}

// 点击「全部工作区」：同样新建标签页，已有标签页不受影响
async function handleSetGlobalView() {
  if (appStore.workspaces.length === 0) return
  const existing = fileStore.tabList.find(t => t.isGlobalView)
  if (existing) {
    await fileStore.switchTab(existing.id)
    return
  }
  await openWorkspaceTab('', true)
}

async function handleRemoveWorkspace(ws: string) {
  appStore.removeWorkspace(ws)
  fileStore.forgetWorkspaceFolder(ws)
  // 关闭该工作区的标签页：其内容已随工作区移除而失效。
  // closeTab 恒保留最后一个标签页，若全部标签页都属于该工作区，
  // 留下的那个由 refreshForWorkspace 重置到新的活动工作区。
  await fileStore.closeWorkspaceTabs(ws)
  refreshForWorkspace()
}

function refreshForWorkspace() {
  const root = appStore.currentWorkspace || undefined
  tagStore.loadTags(root)
  tagStore.clearSelection()
  // 切换工作区时清空文件选择，避免带着上个工作区的选中项进入新工作区
  fileStore.clearSelection()
  if (fileStore.browseMode !== 'all' && !root && !appStore.isGlobalView) {
    fileStore.setBrowseMode('all')
  }
  // 文件夹浏览/树窗模式下，文件列表由导航组件或工作区监听按记忆层级恢复，
  // 此处不再 search 覆盖，避免回到根目录或与目录加载竞争。
  if (fileStore.browseMode !== 'all' && root) return
  fileStore.search({ root })
}

// 重新加载当前文件列表（不改变浏览模式/层级），用于移动、复制等操作后刷新。
// 与 refreshForWorkspace 不同：folder/tree 模式下也会真正重载当前目录内容。
function reloadCurrentFiles() {
  const root = appStore.currentWorkspace || undefined
  if (fileStore.browseMode !== 'all' && fileStore.currentFolderPath) {
    fileStore.loadFolderContents(fileStore.currentFolderPath)
  } else {
    fileStore.search({ root })
  }
}

// 每个完成事件都携带队列剩余数，所有工作区处理完才结束全局进度。
const wsUnsubscribers: Array<() => void> = []
onMounted(() => {
  wsClient.connect()
  wsUnsubscribers.push(wsClient.on('scan_started', () => fileStore.startScanning()))
  wsUnsubscribers.push(wsClient.on<ScanProgressEvent>('scan_progress', data => {
    fileStore.updateScanProgress(data.count, data.total, data.percentage, `${data.path} · ${data.current_file ?? ''}`)
  }))
  wsUnsubscribers.push(wsClient.on<ScanCompletedEvent>('scan_completed', data => {
    if (!data.remaining) fileStore.completeScanning()
    ElMessage.success(`${data.cancelled ? '扫描已取消' : '扫描完成'}，处理 ${data.total} 个文件${data.remaining ? `，剩余 ${data.remaining} 个工作区` : ''}`)
    void fileStore.refreshChangedPaths([data.path])
  }))
  wsUnsubscribers.push(wsClient.on<{ message: string; remaining?: number }>('scan_error', error => {
    if (!error.remaining) fileStore.resetScanning()
    ElMessage.error(`扫描失败: ${error.message}`)
  }))
})

onUnmounted(() => {
  // 取消所有 WebSocket 事件订阅，避免组件多次挂载导致监听器累积
  for (const off of wsUnsubscribers) off()
  wsUnsubscribers.length = 0
})

// 浏览模式选项：下拉横向图标选择（value 与 store 的 BrowseMode 一致）
const browseModeOptions = [
  { value: 'all', label: '全部文件', icon: markRaw(Menu) },
  { value: 'folder', label: '蜂巢导航', icon: markRaw(Connection) },
  { value: 'tree', label: '文件夹树窗', icon: markRaw(Operation) },
  { value: 'explorer', label: '资源管理器', icon: markRaw(FolderOpened) },
] as const

// 当前模式对应的触发按钮图标
const browseModeIcon = computed(() => {
  const opt = browseModeOptions.find((o) => o.value === fileStore.browseMode)
  return opt ? opt.icon : Menu
})

// 当前模式名称（触发按钮 tooltip 用）
const currentBrowseModeLabel = computed(() => {
  const opt = browseModeOptions.find((o) => o.value === fileStore.browseMode)
  return opt ? opt.label : '全部文件'
})

// 浏览模式下拉引用（选中后手动收起）
const browseModeDropdownRef = ref()

// 选择浏览模式并收起下拉
function handleSelectBrowseMode(mode: typeof browseModeOptions[number]['value']) {
  fileStore.setBrowseMode(mode)
  browseModeDropdownRef.value?.handleClose?.()
}

// 折叠状态下点击标签图标：切换选中并触发搜索
function handleCollapsedTagClick(tagId: number) {
  const multi = false
  if (tagStore.selectedTagIds.has(tagId) && tagStore.selectedTagIds.size === 1) {
    tagStore.clearSelection()
    fileStore.reloadCurrentView()
    return
  }
  tagStore.selectTag(tagId, multi)
  if (tagStore.selectedTagIds.size > 0) {
    // 过滤范围由 store 按当前浏览模式/层级统一决定
    fileStore.filterByTags(Array.from(tagStore.effectiveTagIds))
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
  /* 详情停靠容器（抽屉形态与退场浮层）的定位基准，使其上缘紧贴菜单栏下方 */
  position: relative;
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

.workspace-item.drop-active {
  outline: 2px dashed var(--color-accent);
  outline-offset: -2px;
  background: var(--color-bg-secondary);
}

/* 工作区列表：TransitionGroup 的容器，沿用面板的纵向间距 */
.workspace-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

/* 增删工作区：条目自左滑入并撑开高度 / 收起高度并淡出，相邻条目随之平滑让位 */
.ws-item-enter-active,
.ws-item-leave-active {
  overflow: hidden;
  transition:
    max-height var(--motion-base) var(--ease-out),
    padding var(--motion-base) var(--ease-out),
    opacity var(--motion-base) var(--ease-out),
    transform var(--motion-base) var(--ease-out);
}

.ws-item-enter-from,
.ws-item-leave-to {
  max-height: 0;
  padding-top: 0;
  padding-bottom: 0;
  opacity: 0;
  transform: translateX(-10px);
}

.ws-item-enter-to,
.ws-item-leave-from {
  max-height: 40px;
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

/*
 * 工作区配色记号：与标签页底色同色相，用于在标签栏里对应工作区。
 *
 * 绝对定位叠在删除按钮的位置上（该按钮常驻文档流、仅靠 opacity 显隐），
 * 这样圆点不额外占宽，悬停时两者交替淡入淡出且不发生布局跳动。
 */
.workspace-dot {
  position: absolute;
  right: 8px;
  top: 50%;
  width: 8px;
  height: 8px;
  margin-top: -4px;
  border-radius: 50%;
  pointer-events: none;
  transition: opacity 0.15s ease;
}

.workspace-item:hover .workspace-dot {
  opacity: 0;
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

/* 拖动调节条期间关闭宽度过渡：否则面板会滞后于指针 0.3s，拖起来发黏 */
.app-shell.is-resizing .sidebar,
.app-shell.is-resizing .detail-dock {
  transition: none;
}

.app-shell.is-resizing {
  cursor: col-resize;
  user-select: none;
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

/* 按压反馈：按下瞬间回落并轻微收缩，松开后回到悬停的上浮态 */
.toolbar :deep(.el-button:active),
.view-mode-group :deep(.el-button.active:active) {
  transform: translateY(0) scale(0.96);
  transition-duration: 60ms;
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
  min-height: 0;
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
  overflow: hidden;
}

.status-bar-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 0 1 auto;
  min-width: 0;
  max-width: 65%;
}

.file-count { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.loading-status { flex-shrink: 0; }

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

@media (max-width: 768px) {
  .status-bar {
    padding: 0 8px;
    font-size: 11px;
  }

}

.toolbar.compact { height: auto; min-height: var(--header-height); flex-wrap: wrap; padding: 8px 12px; }
.toolbar.compact .toolbar-left { flex-basis: 100%; overflow: visible; }
.toolbar.compact .toolbar-right { width: 100%; justify-content: flex-end; }
.query-error { padding: 8px 16px; background: var(--color-bg-tertiary); color: var(--color-text-primary); flex-shrink: 0; }

/* 查询提示栏：出现/消失时纵向展开/收起，文件区随之平滑让位而不是跳变 */
.bar-expand-enter-active,
.bar-expand-leave-active {
  overflow: hidden;
  transition:
    max-height var(--motion-base) var(--ease-out),
    padding var(--motion-base) var(--ease-out),
    opacity var(--motion-base) var(--ease-out);
}
.bar-expand-enter-from,
.bar-expand-leave-to { max-height: 0; padding-top: 0; padding-bottom: 0; opacity: 0; }
.bar-expand-enter-to,
.bar-expand-leave-from { max-height: 72px; }

/* ===== 详情停靠容器（UI-09 文件详情栏 + UI-12-02 详情宽度调节条） =====
 * 宽度写在容器上而不是依赖内部面板：DetailPanel 为异步组件，首次打开时
 * 面板尚未加载完成，容器也要先占好位，滑入过程才不会中途跳宽。 */
.detail-dock {
  display: flex;
  flex-shrink: 0;
  width: calc(var(--detail-panel-width) + 5px);
  min-height: 0;
  background: var(--color-bg-secondary);
  /* 双击调节条恢复默认宽度、键盘步进时平滑过渡；指针拖动期间由 .is-resizing 关闭 */
  transition: width var(--motion-base) var(--ease-standard);
}
.detail-dock :deep(.detail-panel.visible) { flex: 1 1 0; width: auto; min-width: 0; }

/* 进出场只做位移，中列宽度在整个过程中只变化一次：
 * - 进场：容器从第一帧起就占满最终宽度，中列一次性收窄，面板再滑入让出的空位；
 * - 退场：容器脱离布局浮在右缘，中列一次性展开，面板在其上方滑出。
 * 不能让中列宽度随动画逐帧变化：文件网格按列数定宽并整行居中，
 * 连续变宽会让网格每帧重新居中（左右漂移），换列的那一帧整行宽度突变（瞬移）。
 * 仅剩的那一次换列由 BrowserView 的文件区淡入盖住。 */
.detail-slide-enter-active {
  transition: transform var(--motion-slow) var(--ease-out), opacity var(--motion-base) var(--ease-out);
}
.detail-slide-leave-active {
  position: absolute;
  right: 0;
  top: 0;
  bottom: 0;
  z-index: 30;
  transition: transform var(--motion-base) var(--ease-in), opacity var(--motion-base) var(--ease-in);
}
.detail-slide-enter-from,
.detail-slide-leave-to {
  transform: translateX(100%);
  opacity: 0;
}

/* 抽屉形态：始终浮在中列之上，不参与布局 */
@media (max-width: 1279px) {
  .detail-dock { position: absolute; right: 0; top: 0; bottom: 0; z-index: 30; width: min(380px, 80vw); box-shadow: var(--shadow-xl); }
  .detail-slide-enter-from,
  .detail-slide-leave-to {
    /* 多移出 24px，让投影一并离开视口 */
    transform: translateX(calc(100% + 24px));
  }
}

.panel-resizer { width: 5px; flex-shrink: 0; cursor: col-resize; touch-action: none; background: transparent; transition: background-color var(--motion-fast) ease; }
.panel-resizer:hover, .panel-resizer:focus-visible { background: var(--color-accent); outline: none; }
@media (max-width: 1279px) { .detail-resizer { display: none; } }
</style>

<!-- 浏览模式下拉：teleport 到 body，需非 scoped 全局样式 -->
<style>
.browse-mode-dropdown .el-dropdown-menu {
  padding: 6px !important;
}

.browse-mode-options {
  display: flex;
  flex-direction: row;
  gap: 6px;
}

.browse-mode-option {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  width: 72px;
  padding: 10px 6px;
  border: 1px solid transparent;
  border-radius: var(--radius-md, 8px);
  background: transparent;
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: all 0.15s ease;
}

.browse-mode-option:hover {
  background: var(--color-bg-secondary);
  border-color: var(--color-accent);
  color: var(--color-accent);
}

.browse-mode-option.active {
  background: linear-gradient(135deg, var(--color-accent) 0%, var(--color-accent-hover) 100%);
  border-color: var(--color-accent);
  color: #fff;
}

.browse-mode-option-label {
  font-size: 11px;
  line-height: 1.2;
  white-space: nowrap;
}
</style>
