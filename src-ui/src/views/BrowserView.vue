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
      <RecycleScroller
        v-if="fileStore.viewMode === 'grid'"
        class="scroller grid-view"
        :items="fileStore.files"
        :item-size="200"
        :grid-items="gridItems"
        key-field="id"
        v-slot="{ item }"
      >
        <FileCard
          :file="item"
          :selected="fileStore.selectedIds.has(item.id)"
          @click="handleFileClick(item.id, $event)"
          @dblclick="handleFileDblClick(item)"
        />
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
          :file="item"
          :selected="fileStore.selectedIds.has(item.id)"
          @click="handleFileClick(item.id, $event)"
          @dblclick="handleFileDblClick(item)"
        />
      </RecycleScroller>

      <!-- 加载更多 -->
      <div v-if="fileStore.hasMore" class="load-more">
        <el-button
          :loading="fileStore.isLoading"
          @click="fileStore.loadMore()"
        >
          加载更多
        </el-button>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, watch } from 'vue'
import { RecycleScroller } from 'vue-virtual-scroller'
import 'vue-virtual-scroller/dist/vue-virtual-scroller.css'
import { useAppStore } from '../stores/app'
import { useFileStore } from '../stores/files'
import FileCard from '../components/FileCard.vue'
import FileListItem from '../components/FileListItem.vue'
import type { FileItem } from '../types'
import { open } from '@tauri-apps/plugin-shell'

const appStore = useAppStore()
const fileStore = useFileStore()

// 根据容器宽度计算网格列数
const gridItems = computed(() => {
  // 默认每行4个
  return 4
})

// 监听工作区变化
watch(() => appStore.currentWorkspace, (newPath) => {
  if (newPath) {
    fileStore.search({ root: newPath })
  }
})

onMounted(() => {
  if (appStore.currentWorkspace) {
    fileStore.search({ root: appStore.currentWorkspace })
  }
})

async function selectWorkspace() {
  console.log('[BrowserView] selectWorkspace called')
  try {
    const path = await appStore.selectFolder()
    console.log('[BrowserView] selectFolder returned:', path)
    if (path) {
      fileStore.search({ root: path })
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

async function handleFileDblClick(file: FileItem) {
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

.scroller {
  height: 100%;
}

.grid-view {
  padding: 16px;
}

.list-view {
  padding: 8px 0;
}

.load-more {
  padding: 16px;
  text-align: center;
}
</style>
