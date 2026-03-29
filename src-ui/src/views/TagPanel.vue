<template>
  <div class="tag-panel">
    <div class="panel-header">
      <h3>标签</h3>
      <el-button
        type="primary"
        size="small"
        :icon="Plus"
        @click="showCreateDialog = true"
      >
        新建
      </el-button>
    </div>

    <!-- 过滤状态提示 -->
    <div class="filter-status" :class="{ active: tagStore.hasSelection }">
      <el-alert
        :title="tagStore.hasSelection ? `已选择 ${tagStore.selectedTagIds.size} 个标签过滤` : '点击标签进行过滤'"
        :type="tagStore.hasSelection ? 'info' : 'info'"
        :closable="false"
        show-icon
      >
        <template #default>
          <el-button
            v-if="tagStore.hasSelection"
            type="primary"
            link
            size="small"
            :icon="Close"
            @click="clearFilter"
          >
            清除过滤
          </el-button>
          <span v-else class="filter-hint">支持多选 (Ctrl+点击)</span>
        </template>
      </el-alert>
    </div>

    <div
      class="tag-list"
      :class="{ 'list-drop-active': listDropActive }"
      v-loading="tagStore.isLoading"
      @dragover.prevent="handleTagListDragOver"
      @dragleave="handleTagListDragLeave"
      @drop.prevent="handleTagListDrop"
    >
      <div
        v-for="tag in tagStore.orderedTags"
        :key="tag.id"
        class="tag-item"
        :class="{
          selected: tagStore.selectedTagIds.has(tag.id),
          'drag-source': draggingTagId === tag.id,
          'drag-over': reorderTargetTagId === tag.id,
        }"
        :style="{ backgroundColor: tag.color + '20', borderColor: tag.color }"
        draggable="true"
        @click="handleTagClick(tag.id, $event)"
        @contextmenu.prevent="handleContextMenu(tag, $event)"
        @dragstart="handleTagDragStart(tag.id, $event)"
        @dragend="resetDragState"
        @dragover.prevent="handleTagDragOver(tag.id, $event)"
        @dragleave="handleTagDragLeave(tag.id)"
        @drop.prevent="handleTagDrop(tag, $event)"
      >
        <span class="tag-dot" :style="{ backgroundColor: tag.color }"></span>
        <span class="tag-name">{{ tag.name }}</span>
        <span class="tag-count">{{ tag.file_count }}</span>
      </div>
    </div>

    <!-- 新建标签对话框 -->
    <el-dialog
      v-model="showCreateDialog"
      title="新建标签"
      width="400px"
      append-to-body
      :modal-class="'tag-dialog-modal'"
    >
      <el-form :model="newTag" label-width="80px">
        <el-form-item label="名称">
          <el-input v-model="newTag.name" placeholder="输入标签名称" />
        </el-form-item>
        <el-form-item label="颜色">
          <el-color-picker v-model="newTag.color" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input
            v-model="newTag.description"
            type="textarea"
            placeholder="可选描述"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" @click="createTag">确定</el-button>
      </template>
    </el-dialog>

    <!-- 标签右键菜单 -->
    <el-popover
      :visible="contextMenuVisible"
      :virtual-ref="contextMenuTrigger"
      virtual-triggering
      trigger="contextmenu"
      placement="bottom-start"
      :width="150"
      @update:visible="onContextMenuVisibleChange"
    >
      <div class="context-menu">
        <div class="context-menu-item" @click="editTag">
          <el-icon><Edit /></el-icon>
          <span>编辑标签</span>
        </div>
        <div class="context-menu-item delete" @click="confirmDeleteTag">
          <el-icon><Delete /></el-icon>
          <span>删除标签</span>
        </div>
      </div>
    </el-popover>

    <!-- 编辑标签对话框 -->
    <el-dialog
      v-model="showEditDialog"
      title="编辑标签"
      width="400px"
      append-to-body
      :modal-class="'tag-dialog-modal'"
    >
      <el-form :model="editingTag" label-width="80px">
        <el-form-item label="名称">
          <el-input v-model="editingTag.name" placeholder="输入标签名称" />
        </el-form-item>
        <el-form-item label="颜色">
          <el-color-picker v-model="editingTag.color" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input
            v-model="editingTag.description"
            type="textarea"
            placeholder="可选描述"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showEditDialog = false">取消</el-button>
        <el-button type="primary" @click="saveTagEdit">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch, nextTick } from 'vue'
import { Plus, Close, Edit, Delete } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useTagStore } from '../stores/tags'
import { useFileStore } from '../stores/files'
import { useAppStore } from '../stores/app'
import type { Tag } from '../types'
import { getDraggedTagId, setTagDragData } from '../utils/drag'

const tagStore = useTagStore()
const fileStore = useFileStore()
const appStore = useAppStore()

const showCreateDialog = ref(false)
const showEditDialog = ref(false)
const newTag = ref({
  name: '',
  color: '#409EFF',
  description: '',
})

const editingTag = ref<Tag & { description?: string }>({
  id: 0,
  name: '',
  color: '#409EFF',
  description: '',
  created_at: '',
  file_count: 0,
})

const contextMenuVisible = ref(false)
const contextMenuTrigger = ref<HTMLElement>()
const selectedTag = ref<Tag | null>(null)
const draggingTagId = ref<number | null>(null)
const reorderTargetTagId = ref<number | null>(null)
const listDropActive = ref(false)

// 加载标签，根据当前工作目录过滤
function loadTagsForWorkspace() {
  const workspace = appStore.currentWorkspace
  tagStore.loadTags(workspace || undefined)
}

onMounted(() => {
  loadTagsForWorkspace()
})

// 监听工作目录变化，重新加载标签
watch(() => appStore.currentWorkspace, (newWorkspace, oldWorkspace) => {
  if (newWorkspace !== oldWorkspace) {
    console.log('[TagPanel] Workspace changed from', oldWorkspace, 'to', newWorkspace)
    // 清除标签选择
    tagStore.clearSelection()
    // 重新加载标签
    loadTagsForWorkspace()
    // 如果当前有标签过滤，清除过滤并重新搜索
    if (tagStore.hasSelection) {
      fileStore.search({ root: newWorkspace || undefined })
    }
  }
})

function handleTagClick(tagId: number, event: MouseEvent) {
  const multi = event.ctrlKey || event.metaKey
  
  // 检查是否点击的是已选中的标签
  if (tagStore.selectedTagIds.has(tagId) && !multi) {
    // 如果是已选中的标签且没有按多选键，则取消选择
    tagStore.clearSelection()
    // 重新搜索当前工作区的文件
    if (appStore.currentWorkspace) {
      fileStore.search({ root: appStore.currentWorkspace })
    } else {
      fileStore.search({})
    }
    return
  }
  
  tagStore.selectTag(tagId, multi)
  
  // 更新文件搜索
  if (tagStore.selectedTagIds.size > 0) {
    fileStore.search({
      root: appStore.currentWorkspace || undefined,
      tags: Array.from(tagStore.selectedTagIds),
      match_all_tags: false,
    })
  } else {
    // 如果没有选中任何标签，搜索当前工作区
    if (appStore.currentWorkspace) {
      fileStore.search({ root: appStore.currentWorkspace })
    } else {
      fileStore.search({})
    }
  }
}

function clearFilter() {
  tagStore.clearSelection()
  // 重新搜索当前工作区的文件
  if (appStore.currentWorkspace) {
    fileStore.search({ root: appStore.currentWorkspace })
  } else {
    fileStore.search({})
  }
}

async function createTag() {
  if (!newTag.value.name.trim()) {
    ElMessage.warning('请输入标签名称')
    return
  }
  
  try {
    // 传入当前工作目录，实现标签隔离
    const workspace = appStore.currentWorkspace || undefined
    await tagStore.createTag(
      newTag.value.name,
      newTag.value.color,
      newTag.value.description,
      workspace
    )
    ElMessage.success('标签创建成功')
    showCreateDialog.value = false
    newTag.value = { name: '', color: '#409EFF', description: '' }
  } catch (error: any) {
    // 处理 409 冲突错误
    if (error?.response?.status === 409) {
      ElMessage.error('该工作目录下已存在同名标签')
    } else {
      ElMessage.error('标签创建失败')
    }
  }
}

function resetDragState() {
  draggingTagId.value = null
  reorderTargetTagId.value = null
  listDropActive.value = false
}

function handleTagDragStart(tagId: number, event: DragEvent) {
  draggingTagId.value = tagId
  setTagDragData(event, tagId)
}

function handleTagDragOver(tagId: number, event: DragEvent) {
  const draggedTagId = getDraggedTagId(event)

  if (draggedTagId !== null) {
    reorderTargetTagId.value = draggedTagId === tagId ? null : tagId
    if (event.dataTransfer) {
      event.dataTransfer.dropEffect = 'move'
    }
  }
}

function handleTagDragLeave(tagId: number) {
  if (reorderTargetTagId.value === tagId) {
    reorderTargetTagId.value = null
  }
}

function handleTagListDragOver(event: DragEvent) {
  const draggedTagId = getDraggedTagId(event)
  if (draggedTagId !== null) {
    listDropActive.value = true
  }
}

function handleTagListDragLeave() {
  listDropActive.value = false
}

async function handleTagDrop(tag: Tag, event: DragEvent) {
  const draggedTagId = getDraggedTagId(event)

  if (draggedTagId !== null) {
    if (draggedTagId !== tag.id) {
      tagStore.reorderTags(draggedTagId, tag.id)
    }
    resetDragState()
  }
}

async function handleTagListDrop(event: DragEvent) {
  const draggedTagId = getDraggedTagId(event)

  if (draggedTagId !== null) {
    tagStore.reorderTags(draggedTagId, null)
  }

  resetDragState()
}

async function handleContextMenu(tag: Tag, event: MouseEvent) {
  selectedTag.value = tag
  
  // 创建虚拟触发元素
  const trigger = document.createElement('div')
  trigger.style.position = 'fixed'
  trigger.style.left = event.clientX + 'px'
  trigger.style.top = event.clientY + 'px'
  document.body.appendChild(trigger)
  contextMenuTrigger.value = trigger as HTMLElement
  
  contextMenuVisible.value = true
  
  // 清理
  await nextTick()
  setTimeout(() => {
    if (trigger.parentNode) {
      document.body.removeChild(trigger)
    }
  }, 100)
}

function onContextMenuVisibleChange(val: boolean) {
  contextMenuVisible.value = val
}

function editTag() {
  if (!selectedTag.value) return
  
  editingTag.value = { ...selectedTag.value }
  contextMenuVisible.value = false
  showEditDialog.value = true
}

async function saveTagEdit() {
  if (!editingTag.value.name.trim()) {
    ElMessage.warning('请输入标签名称')
    return
  }
  
  try {
    await tagStore.updateTag(editingTag.value.id, {
      name: editingTag.value.name,
      color: editingTag.value.color,
      description: editingTag.value.description,
    })
    ElMessage.success('标签更新成功')
    showEditDialog.value = false
  } catch (error) {
    ElMessage.error('标签更新失败')
  }
}

async function confirmDeleteTag() {
  if (!selectedTag.value) return
  
  const tag = selectedTag.value
  contextMenuVisible.value = false
  
  try {
    await ElMessageBox.confirm(
      `确定要删除标签 "${tag.name}" 吗？${tag.file_count > 0 ? `该标签已关联 ${tag.file_count} 个文件。` : ''}`,
      '删除确认',
      {
        confirmButtonText: '删除',
        cancelButtonText: '取消',
        type: 'warning',
      }
    )
    
    await tagStore.deleteTag(tag.id)
    
    // 如果该标签正在被过滤，清除过滤
    if (tagStore.selectedTagIds.has(tag.id)) {
      tagStore.clearSelection()
      if (appStore.currentWorkspace) {
        fileStore.search({ root: appStore.currentWorkspace })
      } else {
        fileStore.search({})
      }
    }
    
    ElMessage.success('标签删除成功')
  } catch (error: any) {
    if (error !== 'cancel') {
      ElMessage.error('标签删除失败')
    }
  }
}
</script>

<style scoped>
.tag-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid var(--color-border);
}

.panel-header h3 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-secondary);
}

.filter-status {
  padding: 8px 16px;
  border-bottom: 1px solid var(--color-border);
  background: var(--color-bg-secondary);
}

.filter-status :deep(.el-alert) {
  padding: 8px 12px;
}

.filter-status .filter-hint {
  font-size: 12px;
  color: var(--color-text-tertiary);
}

.tag-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
  transition: background-color 0.2s ease, border-color 0.2s ease;
}

.tag-list.list-drop-active {
  background: color-mix(in srgb, var(--color-accent-light) 45%, transparent);
}

.tag-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  margin-bottom: 4px;
  border-radius: 6px;
  border: 1px solid transparent;
  cursor: pointer;
  transition: all 0.2s ease;
}

.tag-item:hover {
  opacity: 0.8;
}

.tag-item.selected {
  border-width: 2px;
}

.tag-item.drag-source {
  opacity: 0.65;
}

.tag-item.drag-over {
  border-color: var(--color-accent) !important;
  transform: translateX(4px);
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--color-accent) 50%, transparent);
}

.tag-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.tag-name {
  flex: 1;
  font-size: 13px;
  color: var(--color-text-primary);
}

.tag-count {
  font-size: 11px;
  color: var(--color-text-tertiary);
  background: var(--color-bg-tertiary);
  padding: 2px 6px;
  border-radius: 10px;
}

.context-menu {
  padding: 4px 0;
}

.context-menu-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  cursor: pointer;
  transition: background-color 0.2s;
}

.context-menu-item:hover {
  background-color: var(--color-bg-secondary);
}

.context-menu-item.delete {
  color: var(--color-danger);
}

.context-menu-item.delete:hover {
  background-color: var(--color-danger-light);
}
</style>
