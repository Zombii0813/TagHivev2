<template>
  <div class="search-bar">
    <el-input
      v-model="searchText"
      placeholder="搜索文件..."
      clearable
      @keyup.enter="handleSearch"
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
import { ref } from 'vue'
import { Search, ArrowDown } from '@element-plus/icons-vue'
import { useFileStore } from '../stores/files'

const fileStore = useFileStore()
const searchText = ref('')
const selectedType = ref('')

function handleSearch() {
  fileStore.search({
    text: searchText.value || undefined,
    types: selectedType.value ? [selectedType.value] : undefined,
  })
}

function handleTypeFilter(type: string) {
  selectedType.value = type
  handleSearch()
}
</script>

<style scoped>
.search-bar {
  display: flex;
  gap: 8px;
}

.search-bar .el-input {
  width: 300px;
}
</style>
