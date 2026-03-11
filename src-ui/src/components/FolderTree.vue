<template>
  <div class="folder-tree">
    <div v-if="loading" class="loading-state">
      <el-icon class="loading-icon"><Loading /></el-icon>
      <span>加载中...</span>
    </div>
    
    <div v-else-if="!rootPath" class="empty-state">
      <span>请先选择工作区</span>
    </div>
    
    <div v-else-if="folders.length === 0" class="empty-state">
      <span>暂无文件夹</span>
    </div>
    
    <div v-else class="tree-container">
      <div
        class="tree-node root-node"
        :class="{ selected: selectedPath === rootPath }"
        @click="selectFolder(rootPath)"
      >
        <el-icon class="node-icon"><Folder /></el-icon>
        <span class="node-name">{{ rootName }}</span>
        <span class="file-count">({{ totalFiles }})</span>
      </div>
      
      <div class="tree-children">
        <FolderTreeNode
          v-for="folder in folders"
          :key="folder.path"
          :folder="folder"
          :selected-path="selectedPath"
          :level="1"
          @select="selectFolder"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { Loading, Folder } from '@element-plus/icons-vue'
import { folderApi } from '../api/folders'
import type { FolderNode } from '../types'
import FolderTreeNode from './FolderTreeNode.vue'

const props = defineProps<{
  rootPath: string | null
}>()

const emit = defineEmits<{
  select: [path: string]
}>()

const loading = ref(false)
const folders = ref<FolderNode[]>([])
const selectedPath = ref<string>('')
const totalFiles = ref(0)

const rootName = computed(() => {
  if (!props.rootPath) return ''
  const parts = props.rootPath.split(/[/\\]/)
  return parts[parts.length - 1] || props.rootPath
})

// 计算总文件数（包含根目录直接文件和子文件夹中的文件）
function calcTotalFiles(nodes: FolderNode[], rootFileCount: number): number {
  let count = rootFileCount
  for (const node of nodes) {
    count += node.file_count
  }
  return count
}

async function loadFolderTree() {
  if (!props.rootPath) {
    folders.value = []
    totalFiles.value = 0
    return
  }
  
  loading.value = true
  try {
    const result = await folderApi.getTree(props.rootPath)
    folders.value = result.folders
    totalFiles.value = calcTotalFiles(result.folders, result.root_file_count)
    // 默认选中根目录
    if (!selectedPath.value) {
      selectedPath.value = props.rootPath
      emit('select', props.rootPath)
    }
  } catch (error) {
    console.error('Failed to load folder tree:', error)
  } finally {
    loading.value = false
  }
}

function selectFolder(path: string) {
  selectedPath.value = path
  emit('select', path)
}

// 监听根路径变化
watch(() => props.rootPath, () => {
  selectedPath.value = props.rootPath || ''
  loadFolderTree()
}, { immediate: true })

onMounted(() => {
  if (props.rootPath) {
    loadFolderTree()
  }
})
</script>

<style scoped>
.folder-tree {
  height: 100%;
  overflow-y: auto;
  padding: 8px;
}

.loading-state,
.empty-state {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 16px;
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

.tree-container {
  user-select: none;
}

.tree-node {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 8px;
  border-radius: 4px;
  cursor: pointer;
  transition: background-color 0.2s;
  font-size: 13px;
}

.tree-node:hover {
  background-color: var(--color-bg-hover);
}

.tree-node.selected {
  background-color: var(--color-accent-light);
  color: var(--color-accent);
}

.root-node {
  font-weight: 500;
  margin-bottom: 4px;
}

.node-icon {
  font-size: 16px;
  flex-shrink: 0;
}

.node-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.file-count {
  font-size: 11px;
  color: var(--color-text-secondary);
  flex-shrink: 0;
}

.tree-node.selected .file-count {
  color: var(--color-accent);
}

.tree-children {
  margin-left: 4px;
}
</style>
