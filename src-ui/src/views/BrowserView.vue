<template>
  <div class="browser-view">
    <!-- 空状态 -->
    <div v-if="!appStore.currentWorkspace" class="empty-state">
      <el-empty description="请选择一个工作区">
        <el-button type="primary" @click="selectWorkspace">
          选择文件夹
        </el-button>
      </el-empty>
    </div>

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
import { computed, onMounted, watch, ref, onUnmounted } from 'vue'
import { RecycleScroller } from 'vue-virtual-scroller'
import 'vue-virtual-scroller/dist/vue-virtual-scroller.css'
import { useAppStore } from '../stores/app'
import { useFileStore } from '../stores/files'
import FileCard from '../components/FileCard.vue'
import FileListItem from '../components/FileListItem.vue'
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
  
  // 移除滚动监听
  if (scrollerRef.value) {
    scrollerRef.value.removeEventListener('scroll', handleScroll)
  }
})

// 监听工作区变化
watch(() => appStore.currentWorkspace, (newPath) => {
  if (newPath) {
    fileStore.search({ root: newPath })
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
</style>
