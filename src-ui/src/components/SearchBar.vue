<template>
  <div class="search-bar">
    <el-input
      v-model="searchText"
      aria-label="搜索文件名"
      :placeholder="searchPlaceholder"
      clearable
      @input="handleInput"
      @clear="handleClear"
    >
      <template #prefix>
        <el-icon><Search /></el-icon>
      </template>
    </el-input>

    <el-dropdown @command="handleTypeFilter">
      <el-button :type="selectedType ? 'primary' : 'default'" :plain="!!selectedType">
        {{ typeLabels[selectedType] || '类型' }}
        <el-icon class="el-icon--right"><ArrowDown /></el-icon>
      </el-button>
      <template #dropdown>
        <el-dropdown-menu>
          <el-dropdown-item command="">全部</el-dropdown-item>
          <el-dropdown-item command="image">图片</el-dropdown-item>
          <el-dropdown-item command="video">视频</el-dropdown-item>
          <el-dropdown-item command="doc">文档</el-dropdown-item>
          <el-dropdown-item command="audio">音频</el-dropdown-item>
        </el-dropdown-menu>
      </template>
    </el-dropdown>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount } from 'vue'
import { Search, ArrowDown } from '@element-plus/icons-vue'
import { useFileStore } from '../stores/files'

const fileStore = useFileStore()

// 搜索条件存在标签页里而非本组件：搜索是「浏览位置」的一部分，
// 切换标签页要能看回该页自己的搜索词。组件为受控，不持有本地副本。
const searchText = computed<string>({
  get: () => fileStore.activeTab.searchText,
  set: (v) => { fileStore.activeTab.searchText = v },
})
const selectedType = computed<string>({
  get: () => fileStore.activeTab.searchType,
  set: (v) => { fileStore.activeTab.searchType = v },
})

const typeLabels: Record<string, string> = { image: '图片', video: '视频', doc: '文档', audio: '音频' }
const searchPlaceholder = computed(() => fileStore.activeTab.isGlobalView
  ? '搜索已添加的工作区…'
  : fileStore.activeTab.browseMode === 'all' ? '搜索当前工作区…' : '搜索当前目录及子目录…')

// 防抖定时器
let debounceTimer: ReturnType<typeof setTimeout> | null = null
const DEBOUNCE_DELAY = 300 // 防抖延迟 300ms

/**
 * 对指定标签页执行搜索，条件取自该标签页自身。
 *
 * @param tabId 目标标签页 id
 */
function handleSearch(tabId: string) {
  fileStore.reloadCurrentView(tabId)
}

function handleInput() {
  // 在输入时就捕获标签页：防抖等待的 300ms 内用户可能切走，
  // 届时再取 activeTabId 会把 A 的搜索结果写进 B
  const tabId = fileStore.activeTabId
  fileStore.clearSelection(tabId)
  fileStore.invalidateRequests(tabId)
  if (debounceTimer) {
    clearTimeout(debounceTimer)
  }
  debounceTimer = setTimeout(() => {
    handleSearch(tabId)
  }, DEBOUNCE_DELAY)
}

onBeforeUnmount(() => { if (debounceTimer) clearTimeout(debounceTimer) })

// 点击清空按钮：立即搜索（显示所有文件）。
// 这里用显式事件而非 watch(searchText)——搜索词现在属于标签页，
// 从「有搜索词」的标签页切到「无搜索词」的标签页同样会让值变空，
// watch 会误判为用户清空而发起一次搜索，覆盖目标标签页刚恢复的数据。
function handleClear() {
  const tabId = fileStore.activeTabId
  fileStore.clearSelection(tabId)
  fileStore.invalidateRequests(tabId)
  if (debounceTimer) {
    clearTimeout(debounceTimer)
  }
  handleSearch(tabId)
}

function handleTypeFilter(type: string) {
  selectedType.value = type
  handleSearch(fileStore.activeTabId)
}
</script>

<style scoped>
.search-bar {
  display: flex;
  gap: 8px;
  flex: 1;
  min-width: 304px;
  max-width: 540px;
}

.search-bar .el-input {
  flex: 1;
  min-width: 224px;
}

/* 响应式：小屏幕时隐藏类型筛选按钮文字 */
@media (max-width: 640px) {
  .search-bar .el-button {
    padding: 8px;
  }

  .search-bar .el-button span {
    display: none;
  }
}
</style>
