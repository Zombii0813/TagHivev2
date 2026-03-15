<template>
  <div class="browser-view">
    <!-- 空状态 -->
    <div v-if="!appStore.currentWorkspace" class="empty-state-container">
      <EmptyState
        icon="folder"
        title="开始管理您的文件"
        description="选择一个文件夹作为工作区，开始使用 TagHive 管理您的文件和标签"
        action-text="选择文件夹"
        hint="支持图片、视频、音频、文档等多种文件类型"
        @action="selectWorkspace"
      />
    </div>

    <!-- 文件夹浏览模式 -->
    <template v-else-if="fileStore.browseMode === 'folder'">
      <div class="tree-view-container">
        <!-- 左侧文件夹树 -->
        <div class="folder-tree-panel">
          <FolderTree
            :root-path="appStore.currentWorkspace"
            @select="handleFolderSelect"
          />
        </div>
        
        <!-- 右侧文件列表 -->
        <div ref="scrollerRef" class="scroller-container">
          <!-- Grid 模式 -->
          <RecycleScroller
            v-if="fileStore.viewMode === 'grid'"
            class="scroller grid-view"
            :items="gridRows"
            :item-size="gridItemHeight"
            key-field="rowIndex"
            v-slot="{ item: row }"
          >
            <div class="grid-row" :style="gridRowStyle">
              <div
                v-for="file in row.files"
                :key="file.id"
                class="grid-cell"
                :style="gridCellStyle"
              >
                <FileCard
                  :file="file"
                  :selected="fileStore.selectedIds.has(file.id)"
                  :size="gridItemWidth"
                  @click="handleFileClick(file.id, $event)"
                  @dblclick="handleFileDblClick(file)"
                />
              </div>
            </div>
          </RecycleScroller>

          <!-- List 模式 -->
          <RecycleScroller
            v-else
            class="scroller list-view"
            :items="fileStore.files"
            :item-size="60"
            key-field="id"
            v-slot="{ item }"
          >
            <FileListItem
              ref="fileListItemRefs"
              :file="item"
              :selected="fileStore.selectedIds.has(item.id)"
              @click="handleFileClick(item.id, $event)"
              @dblclick="handleFileDblClick(item)"
            />
          </RecycleScroller>
          
          <!-- 加载更多提示 -->
          <div v-if="fileStore.hasMore && fileStore.isLoading" class="load-more">
            <el-icon class="loading-icon"><Loading /></el-icon>
            <span>加载中...</span>
          </div>
        </div>
      </div>
    </template>

    <!-- 文件列表 -->
    <template v-else>
      <div ref="scrollerRef" class="scroller-container">
        <!-- Grid 模式 - 使用 CSS Grid 布局 -->
        <RecycleScroller
          v-if="fileStore.viewMode === 'grid'"
          class="scroller grid-view"
          :items="gridRows"
          :item-size="gridItemHeight"
          key-field="rowIndex"
          v-slot="{ item: row }"
        >
          <div class="grid-row" :style="gridRowStyle">
            <div
              v-for="file in row.files"
              :key="file.id"
              class="grid-cell"
              :style="gridCellStyle"
            >
              <FileCard
                :file="file"
                :selected="fileStore.selectedIds.has(file.id)"
                :size="gridItemWidth"
                @click="handleFileClick(file.id, $event)"
                @dblclick="handleFileDblClick(file)"
              />
            </div>
          </div>
        </RecycleScroller>

        <RecycleScroller
          v-else
          class="scroller list-view"
          :items="fileStore.files"
          :item-size="60"
          key-field="id"
          v-slot="{ item }"
        >
          <FileListItem
            ref="fileListItemRefs"
            :file="item"
            :selected="fileStore.selectedIds.has(item.id)"
            @click="handleFileClick(item.id, $event)"
            @dblclick="handleFileDblClick(item)"
          />
        </RecycleScroller>
      </div>

      <!-- 加载更多提示 -->
      <div v-if="fileStore.hasMore && fileStore.isLoading" class="load-more">
        <el-icon class="loading-icon"><Loading /></el-icon>
        <span>加载中...</span>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, watch, ref, onUnmounted, nextTick } from 'vue'
import { RecycleScroller } from 'vue-virtual-scroller'
import 'vue-virtual-scroller/dist/vue-virtual-scroller.css'
import { useAppStore } from '../stores/app'
import { useFileStore } from '../stores/files'
import FileCard from '../components/FileCard.vue'
import FileListItem from '../components/FileListItem.vue'
import FolderTree from '../components/FolderTree.vue'
import EmptyState from '../components/EmptyState.vue'
import type { FileSummary } from '../types'
import { open } from '@tauri-apps/plugin-shell'
import { wsClient } from '../api/websocket'
import { ElMessage } from 'element-plus'
import { Loading } from '@element-plus/icons-vue'

// 滚动加载配置
const SCROLL_THRESHOLD = 100 // 距离底部多少像素时触发加载


const appStore = useAppStore()
const fileStore = useFileStore()

const scrollerRef = ref<HTMLElement | null>(null)
const fileListItemRefs = ref<InstanceType<typeof FileListItem>[]>([])
const containerWidth = ref(0)

// ResizeObserver 实例
let resizeObserver: ResizeObserver | null = null

// Grid 布局配置
const GAP = 16 // 间距
const MIN_ITEM_WIDTH = 160 // 最小宽度
const PADDING = 32 // 左右 padding 总和
const INFO_HEIGHT = 80 // 文件名等信息区域高度（包含标签区域）

// 计算每行显示的列数
const gridColumns = computed(() => {
  if (containerWidth.value === 0) return 4
  const availableWidth = containerWidth.value - PADDING
  const columns = Math.floor((availableWidth + GAP) / (MIN_ITEM_WIDTH + GAP))
  return Math.max(columns, 2) // 最少显示 2 列
})

// 计算每个 grid item 的宽度
const gridItemWidth = computed(() => {
  if (containerWidth.value === 0) return MIN_ITEM_WIDTH
  const availableWidth = containerWidth.value - PADDING
  // 计算每个 item 的宽度
  const itemWidth = (availableWidth - (gridColumns.value - 1) * GAP) / gridColumns.value
  return Math.max(itemWidth, MIN_ITEM_WIDTH)
})

// 计算每个 grid item 的高度
const gridItemHeight = computed(() => {
  return gridItemWidth.value + INFO_HEIGHT
})

// 将文件列表按行分组
interface GridRow {
  rowIndex: number
  files: FileSummary[]
}

const gridRows = computed<GridRow[]>(() => {
  const rows: GridRow[] = []
  const files = fileStore.files
  const columns = gridColumns.value
  
  for (let i = 0; i < files.length; i += columns) {
    rows.push({
      rowIndex: Math.floor(i / columns),
      files: files.slice(i, i + columns)
    })
  }
  
  return rows
})

// Grid 行样式
const gridRowStyle = computed(() => ({
  display: 'flex',
  gap: `${GAP}px`,
  padding: `0 ${PADDING / 2}px`,
  height: `${gridItemHeight.value}px`
}))

// Grid 单元格样式
const gridCellStyle = computed(() => ({
  flex: '0 0 auto',
  width: `${gridItemWidth.value}px`
}))

// 监听容器宽度变化
function updateContainerWidth() {
  if (scrollerRef.value) {
    containerWidth.value = scrollerRef.value.clientWidth
  }
}

// 处理滚动事件，实现无限滚动加载
function handleScroll(event: Event) {
  const target = event.target as HTMLElement
  if (!target) return

  const { scrollTop, scrollHeight, clientHeight } = target
  const distanceToBottom = scrollHeight - scrollTop - clientHeight

  // 当距离底部小于阈值时，加载更多
  if (distanceToBottom < SCROLL_THRESHOLD && fileStore.hasMore && !fileStore.isLoading) {
    fileStore.loadMore()
  }
}

onMounted(() => {
  updateContainerWidth()
  window.addEventListener('resize', updateContainerWidth)
  
  // 使用 ResizeObserver 监听容器大小变化
  if (scrollerRef.value && typeof ResizeObserver !== 'undefined') {
    resizeObserver = new ResizeObserver(() => {
      updateContainerWidth()
    })
    resizeObserver.observe(scrollerRef.value)
  }
  
  // 添加滚动监听
  if (scrollerRef.value) {
    scrollerRef.value.addEventListener('scroll', handleScroll)
  }
  
  if (appStore.currentWorkspace) {
    fileStore.search({ root: appStore.currentWorkspace })
  }
})

onUnmounted(() => {
  window.removeEventListener('resize', updateContainerWidth)
  
  // 移除 ResizeObserver
  if (resizeObserver) {
    resizeObserver.disconnect()
    resizeObserver = null
  }
  
  // 移除滚动监听
  if (scrollerRef.value) {
    scrollerRef.value.removeEventListener('scroll', handleScroll)
  }
})

// 监听工作区变化
watch(() => appStore.currentWorkspace, (newPath) => {
  if (newPath) {
    if (fileStore.browseMode === 'folder') {
      // 文件夹浏览模式：加载根目录内容
      fileStore.loadFolderContents(newPath)
    } else {
      // 全部文件模式：搜索所有文件
      fileStore.search({ root: newPath })
    }
  }
})

// 监听浏览模式变化
watch(() => fileStore.browseMode, async (newMode) => {
  if (!appStore.currentWorkspace) return
  
  if (newMode === 'folder') {
    // 切换到文件夹浏览模式：加载根目录内容
    await fileStore.loadFolderContents(appStore.currentWorkspace)
  } else {
    // 切换到全部文件模式：搜索所有文件
    await fileStore.search({ root: appStore.currentWorkspace })
  }
  
  // 等待 DOM 更新后重新设置 ResizeObserver
  await nextTick()
  
  // 清理旧的 ResizeObserver
  if (resizeObserver) {
    resizeObserver.disconnect()
    resizeObserver = null
  }
  
  // 更新容器宽度
  updateContainerWidth()
  
  // 重新设置 ResizeObserver
  if (scrollerRef.value && typeof ResizeObserver !== 'undefined') {
    resizeObserver = new ResizeObserver(() => {
      updateContainerWidth()
    })
    resizeObserver.observe(scrollerRef.value)
    
    // 重新添加滚动监听
    scrollerRef.value.removeEventListener('scroll', handleScroll)
    scrollerRef.value.addEventListener('scroll', handleScroll)
  }
})

async function selectWorkspace() {
  console.log('[BrowserView] selectWorkspace called')
  try {
    const path = await appStore.selectFolder()
    console.log('[BrowserView] selectFolder returned:', path)
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
    }
  } catch (error) {
    console.error('[BrowserView] Error in selectWorkspace:', error)
  }
}

function handleFileClick(fileId: number, event: MouseEvent) {
  const multi = event.ctrlKey || event.metaKey
  const range = event.shiftKey
  
  if (range && fileStore.selectedIds.size > 0) {
    // 范围选择
    const lastSelected = Array.from(fileStore.selectedIds).pop()
    if (lastSelected) {
      fileStore.selectRange(lastSelected, fileId)
    }
  } else {
    fileStore.selectFile(fileId, multi)
  }
}

async function handleFileDblClick(file: FileSummary) {
  // 打开文件
  try {
    await open(file.path)
  } catch (error) {
    console.error('Failed to open file:', error)
  }
}

// 处理文件夹选择
async function handleFolderSelect(folderPath: string) {
  await fileStore.loadFolderContents(folderPath)
}
</script>

<style scoped>
.browser-view {
  height: 100%;
  overflow: hidden;
}

.empty-state {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
}

.scroller-container {
  height: 100%;
  width: 100%;
}

.scroller {
  height: 100%;
}

.grid-view {
  padding: 16px 0;
}

/* 确保 RecycleScroller 的 item view 占满宽度 */
.grid-view :deep(.vue-recycle-scroller__item-view) {
  width: 100% !important;
  position: absolute !important;
  left: 0 !important;
}

/* Grid 行容器 */
.grid-row {
  box-sizing: border-box;
  align-items: flex-start;
}

/* Grid 单元格 */
.grid-cell {
  box-sizing: border-box;
}

.list-view {
  padding: 8px 0;
}

.load-more {
  padding: 16px;
  text-align: center;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: var(--color-text-secondary);
  font-size: 14px;
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

/* 树形视图样式 */
.tree-view-container {
  display: flex;
  height: 100%;
  overflow: hidden;
}

.folder-tree-panel {
  width: 280px;
  flex-shrink: 0;
  border-right: 1px solid var(--color-border);
  background: var(--color-bg-secondary);
  overflow-y: auto;
}

.tree-view-container .scroller-container {
  flex: 1;
  min-width: 0;
}

/* 响应式：小屏幕时调整文件夹树宽度 */
@media (max-width: 768px) {
  .folder-tree-panel {
    width: 200px;
  }
}

@media (max-width: 480px) {
  .folder-tree-panel {
    width: 160px;
  }
}
</style>
