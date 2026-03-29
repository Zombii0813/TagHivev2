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
        @contextmenu.prevent="handleNodeContextMenu({ folder: { name: rootName, path: rootPath, file_count: totalFiles, children: [], is_expanded: true }, event: $event })"
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
          @contextmenu="handleNodeContextMenu"
        />
      </div>
    </div>

    <!-- 文件夹右键菜单 -->
    <el-popover
      :visible="contextMenuVisible"
      :virtual-ref="contextMenuTrigger"
      virtual-triggering
      trigger="contextmenu"
      placement="bottom-start"
      :width="148"
      popper-class="context-menu-popover"
      @update:visible="(v) => { if (!v) contextMenuVisible = false }"
    >
      <div class="context-menu">
        <div class="context-menu-item" @click="openCreateSubdirDialog">
          <el-icon><FolderAdd /></el-icon>
          <span>新建子目录</span>
        </div>
      </div>
    </el-popover>

    <!-- 新建子目录对话框 -->
    <el-dialog
      v-model="showCreateDialog"
      title="新建子目录"
      width="400px"
      append-to-body
      destroy-on-close
    >
      <div class="create-dialog-hint">在 <strong>{{ contextMenuFolder?.name }}</strong> 下创建子目录</div>
      <el-input
        v-model="newSubdirName"
        placeholder="输入目录名称"
        maxlength="80"
        clearable
        style="margin-top: 12px"
        @keyup.enter="confirmCreateSubdir"
      />
      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" :loading="creating" :disabled="!newSubdirName.trim()" @click="confirmCreateSubdir">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { Loading, Folder, FolderAdd } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { invoke } from '@tauri-apps/api/core'
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

// ===== 右键菜单 =====

const contextMenuVisible = ref(false)
const contextMenuTrigger = ref<HTMLElement>()
const contextMenuFolder = ref<FolderNode | null>(null)
const showCreateDialog = ref(false)

const contextMenuAnchor = (() => {
  const el = document.createElement('div')
  el.style.cssText = 'position:fixed;left:-9999px;top:-9999px;width:1px;height:1px;pointer-events:none'
  document.body.appendChild(el)
  return el
})()
const newSubdirName = ref('')
const creating = ref(false)

function closeFolderContextMenu() {
  contextMenuVisible.value = false
}

function handleNodeContextMenu(payload: { folder: FolderNode; event: MouseEvent }) {
  contextMenuFolder.value = payload.folder
  window.dispatchEvent(new Event('close-context-menus'))
  contextMenuAnchor.style.left = `${payload.event.clientX}px`
  contextMenuAnchor.style.top = `${payload.event.clientY}px`
  contextMenuTrigger.value = contextMenuAnchor
  contextMenuVisible.value = true
}

function openCreateSubdirDialog() {
  contextMenuVisible.value = false
  newSubdirName.value = ''
  showCreateDialog.value = true
}

async function confirmCreateSubdir() {
  const name = newSubdirName.value.trim()
  if (!name || !props.rootPath || !contextMenuFolder.value) return
  creating.value = true
  try {
    try {
      await folderApi.createFolder(props.rootPath, contextMenuFolder.value.path, name)
    } catch (error: any) {
      if (error?.response?.status !== 404) throw error
      const targetPath = `${contextMenuFolder.value.path.replace(/[\/\\]+$/, '')}/${name}`
      await invoke('create_folder', { path: targetPath })
    }
    showCreateDialog.value = false
    ElMessage.success(`已创建目录：${name}`)
    await loadFolderTree()
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || '创建目录失败')
  } finally {
    creating.value = false
  }
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
  window.addEventListener('close-context-menus', closeFolderContextMenu)
})

onUnmounted(() => {
  window.removeEventListener('close-context-menus', closeFolderContextMenu)
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

.context-menu {
  padding: 4px 0;
}

.context-menu-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  cursor: pointer;
  font-size: 13px;
  border-radius: 6px;
  transition: background-color 0.15s;
}

.context-menu-item:hover {
  background-color: var(--color-bg-secondary);
}

.create-dialog-hint {
  font-size: 13px;
  color: var(--color-text-secondary);
}
</style>
