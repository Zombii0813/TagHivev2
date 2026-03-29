<template>
  <div class="tag-panel" @dragover="handlePanelDragOver">
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
      ref="tagListRef"
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
        :data-tag-id="tag.id"
        draggable="true"
        @click="handleTagClick(tag.id, $event)"
        @contextmenu.prevent="handleContextMenu(tag, $event)"
        @dragstart="handleTagDragStart(tag.id, $event)"
        @dragend="resetDragState"
        @dragover.prevent.stop="handleTagDragOver(tag.id, $event)"
        @dragleave="handleTagDragLeave(tag.id)"
        @drop.prevent.stop="handleTagDrop(tag, $event)"
      >
        <span v-if="tag.icon" class="tag-icon">{{ tag.icon }}</span>
        <span v-else class="tag-dot" :style="{ backgroundColor: tag.color }"></span>
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
        <el-form-item label="图标">
          <div class="icon-picker-row">
            <div
              class="icon-preview"
              :style="newTag.icon ? { borderColor: newTag.color } : {}"
            >
              <span v-if="newTag.icon" class="icon-preview-emoji">{{ newTag.icon }}</span>
              <span v-else class="icon-preview-dot" :style="{ backgroundColor: newTag.color }"></span>
            </div>
            <el-input
              v-model="newTag.icon"
              placeholder="输入或粘贴 Emoji，如 🎨"
              maxlength="8"
              class="icon-input"
              clearable
            />
          </div>
          <div class="emoji-presets">
            <span
              v-for="e in emojiPresets"
              :key="e"
              class="emoji-preset-item"
              :class="{ active: newTag.icon === e }"
              @click="newTag.icon = newTag.icon === e ? '' : e"
            >{{ e }}</span>
          </div>
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
      :width="140"
      popper-class="context-menu-popover"
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
        <el-form-item label="图标">
          <div class="icon-picker-row">
            <div
              class="icon-preview"
              :style="editingTag.icon ? { borderColor: editingTag.color } : {}"
            >
              <span v-if="editingTag.icon" class="icon-preview-emoji">{{ editingTag.icon }}</span>
              <span v-else class="icon-preview-dot" :style="{ backgroundColor: editingTag.color }"></span>
            </div>
            <el-input
              v-model="editingTag.icon"
              placeholder="输入或粘贴 Emoji，如 🎨"
              maxlength="8"
              class="icon-input"
              clearable
            />
          </div>
          <div class="emoji-presets">
            <span
              v-for="e in emojiPresets"
              :key="e"
              class="emoji-preset-item"
              :class="{ active: editingTag.icon === e }"
              @click="editingTag.icon = editingTag.icon === e ? '' : e"
            >{{ e }}</span>
          </div>
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
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { Plus, Close, Edit, Delete } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useTagStore } from '../stores/tags'
import { useFileStore } from '../stores/files'
import { useAppStore } from '../stores/app'
import type { Tag } from '../types'
import { getDraggedTagId, setTagDragData, hasTagDrag, clearTagDragState, isTagDragInProgress } from '../utils/drag'

const tagStore = useTagStore()
const fileStore = useFileStore()
const appStore = useAppStore()

const showCreateDialog = ref(false)
const showEditDialog = ref(false)
const newTag = ref({
  name: '',
  color: '#409EFF',
  icon: '',
  description: '',
})

const editingTag = ref<Tag & { description?: string }>({
  id: 0,
  name: '',
  color: '#409EFF',
  icon: '',
  description: '',
  created_at: '',
  file_count: 0,
})

// 常用 emoji 预设
const emojiPresets = [
  '🎨', '📁', '⭐', '🔥', '💡', '🎵', '📷', '🎬',
  '📝', '🔖', '💼', '🏷️', '🎯', '✅', '❤️', '🌟',
  '🚀', '💎', '🌈', '🍀', '🐾', '🎮', '📚', '🔑',
]

const contextMenuVisible = ref(false)
const contextMenuTrigger = ref<HTMLElement>()
const selectedTag = ref<Tag | null>(null)
const draggingTagId = ref<number | null>(null)
const tagListRef = ref<HTMLElement | null>(null)

const contextMenuAnchor = (() => {
  const el = document.createElement('div')
  el.style.cssText = 'position:fixed;left:-9999px;top:-9999px;width:1px;height:1px;pointer-events:none'
  document.body.appendChild(el)
  return el
})()
const reorderTargetTagId = ref<number | null>(null)
const listDropActive = ref(false)

// 加载标签，根据当前工作目录过滤
function loadTagsForWorkspace() {
  const workspace = appStore.currentWorkspace
  tagStore.loadTags(workspace || undefined)
}

onMounted(() => {
  loadTagsForWorkspace()
  window.addEventListener('close-context-menus', closeContextMenu)
})

onUnmounted(() => {
  window.removeEventListener('close-context-menus', closeContextMenu)
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
      workspace,
      newTag.value.icon || undefined,
    )
    ElMessage.success('标签创建成功')
    showCreateDialog.value = false
    newTag.value = { name: '', color: '#409EFF', icon: '', description: '' }
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
  clearTagDragState()
}

// 面板根元素 dragover：标签拖拽时防止在非 tag-list 区域显示禁止图标
function handlePanelDragOver(event: DragEvent) {
  if (isTagDragInProgress()) {
    event.preventDefault()
    if (event.dataTransfer) {
      event.dataTransfer.dropEffect = 'move'
    }
  }
}

function handleTagDragStart(tagId: number, event: DragEvent) {
  draggingTagId.value = tagId
  setTagDragData(event, tagId)
}

function handleTagDragOver(tagId: number, event: DragEvent) {
  if (!isTagDragInProgress() && !hasTagDrag(event)) {
    return
  }

  reorderTargetTagId.value = draggingTagId.value === tagId ? null : tagId
  if (event.dataTransfer) {
    event.dataTransfer.dropEffect = 'move'
  }
}

function handleTagDragLeave(tagId: number) {
  if (reorderTargetTagId.value === tagId) {
    reorderTargetTagId.value = null
  }
}

function handleTagListDragOver(event: DragEvent) {
  if (isTagDragInProgress() || hasTagDrag(event)) {
    listDropActive.value = true
  }
}

function handleTagListDragLeave() {
  listDropActive.value = false
}

async function handleTagDrop(tag: Tag, event: DragEvent) {
  const draggedTagId = getDraggedTagId(event)

  if (draggedTagId !== null && draggedTagId !== tag.id) {
    // 根据鼠标在目标 tag 的上/下半决定插入位置
    const el = (event.currentTarget as HTMLElement)
    const rect = el.getBoundingClientRect()
    const isLowerHalf = event.clientY > rect.top + rect.height / 2
    const targetId = isLowerHalf ? getNextTagId(tag.id) : tag.id
    tagStore.reorderTags(draggedTagId, targetId)
  }
  resetDragState()
}

async function handleTagListDrop(event: DragEvent) {
  const draggedTagId = getDraggedTagId(event)

  if (draggedTagId !== null) {
    const targetTagId = getTagIdNearY(event.clientY, draggedTagId)
    tagStore.reorderTags(draggedTagId, targetTagId)
  }

  resetDragState()
}

// 根据鼠标 Y 坐标找到最近的目标标签 id
// 返回 null 表示追加到末尾
function getTagIdNearY(clientY: number, excludeTagId: number): number | null {
  if (!tagListRef.value) return null

  const items = Array.from(tagListRef.value.querySelectorAll<HTMLElement>('.tag-item'))
  if (!items.length) return null

  let nearestId: number | null = null
  let nearestDist = Infinity

  for (const item of items) {
    const rect = item.getBoundingClientRect()
    const itemCenter = rect.top + rect.height / 2
    const dist = Math.abs(clientY - itemCenter)

    if (dist < nearestDist) {
      nearestDist = dist
      // 读取 tag id（通过 data 属性或 key）
      const idStr = item.dataset.tagId
      if (idStr) {
        const id = Number(idStr)
        if (id !== excludeTagId) {
          // 鼠标在该 tag 下半部时，插到它后面（targetId = 下一个 tag），否则插到它前面
          nearestId = clientY > itemCenter ? getNextTagId(id) : id
        }
      }
    }
  }

  return nearestId
}

function getNextTagId(tagId: number): number | null {
  const order = tagStore.orderedTags
  const idx = order.findIndex(t => t.id === tagId)
  return idx !== -1 && idx + 1 < order.length ? order[idx + 1].id : null
}

function closeContextMenu() {
  contextMenuVisible.value = false
}

function handleContextMenu(tag: Tag, event: MouseEvent) {
  selectedTag.value = tag

  // 关闭其他面板的右键菜单
  window.dispatchEvent(new Event('close-context-menus'))

  contextMenuAnchor.style.left = `${event.clientX}px`
  contextMenuAnchor.style.top = `${event.clientY}px`
  contextMenuTrigger.value = contextMenuAnchor
  contextMenuVisible.value = true
}

function onContextMenuVisibleChange(val: boolean) {
  contextMenuVisible.value = val
}

function editTag() {
  if (!selectedTag.value) return

  editingTag.value = { ...selectedTag.value, icon: selectedTag.value.icon || '' }
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
      icon: editingTag.value.icon || undefined,
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
  padding: 6px 10px;
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

.tag-icon {
  font-size: 15px;
  line-height: 1;
  flex-shrink: 0;
  width: 18px;
  text-align: center;
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

/* 图标选择器 */
.icon-picker-row {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
}

.icon-preview {
  width: 32px;
  height: 32px;
  border-radius: 6px;
  border: 1px solid var(--color-border);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  background: var(--color-bg-secondary);
}

.icon-preview-emoji {
  font-size: 18px;
  line-height: 1;
}

.icon-preview-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
}

.icon-input {
  flex: 1;
}

.emoji-presets {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 8px;
}

.emoji-preset-item {
  font-size: 18px;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  cursor: pointer;
  border: 1px solid transparent;
  transition: all 0.15s ease;
  user-select: none;
}

.emoji-preset-item:hover {
  background: var(--color-bg-secondary);
  border-color: var(--color-border);
}

.emoji-preset-item.active {
  background: var(--color-accent-light);
  border-color: var(--color-accent);
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
