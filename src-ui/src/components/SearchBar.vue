<template>
  <div class="search-bar">
    <el-input
      v-model="searchText"
      placeholder="搜索文件..."
      clearable
      @input="handleInput"
    >
      <template #prefix>
        <el-icon><Search /></el-icon>
      </template>
    </el-input>
    
    <el-dropdown @command="handleTypeFilter">
      <el-button>
        类型
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
import { ref, watch } from 'vue'
import { Search, ArrowDown } from '@element-plus/icons-vue'
import { useFileStore } from '../stores/files'
import { useAppStore } from '../stores/app'

const fileStore = useFileStore()
const appStore = useAppStore()
const searchText = ref('')
const selectedType = ref('')

// 防抖定时器
let debounceTimer: ReturnType<typeof setTimeout> | null = null
const DEBOUNCE_DELAY = 300 // 防抖延迟 300ms

function handleSearch() {
  fileStore.search({
    text: searchText.value || undefined,
    types: selectedType.value ? [selectedType.value] : undefined,
    root: appStore.currentWorkspace || undefined,
  })
}

function handleInput() {
  // 清除之前的定时器
  if (debounceTimer) {
    clearTimeout(debounceTimer)
  }
  // 设置新的定时器，延迟执行搜索
  debounceTimer = setTimeout(() => {
    handleSearch()
  }, DEBOUNCE_DELAY)
}

function handleTypeFilter(type: string) {
  selectedType.value = type
  handleSearch()
}

// 监听清空事件
watch(searchText, (newValue) => {
  if (newValue === '') {
    // 清空时立即搜索（显示所有文件）
    if (debounceTimer) {
      clearTimeout(debounceTimer)
    }
    handleSearch()
  }
})
</script>

<style scoped>
.search-bar {
  display: flex;
  gap: 8px;
  flex: 1;
  min-width: 0;
  max-width: 400px;
}

.search-bar .el-input {
  flex: 1;
  min-width: 0;
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
