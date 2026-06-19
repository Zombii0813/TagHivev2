<template>
  <!-- 批量管理标签对话框 -->
  <el-dialog
    v-model="showAddTagsDialog"
    title="批量管理标签"
    width="460px"
    @close="resetState"
  >
    <div class="selection-summary">
      已选 {{ fileStore.selectedCount }} 个文件
    </div>

    <!-- 已有标签：所选文件标签的并集，点 × 即时批量解绑 -->
    <div class="section">
      <div class="section-title">已有标签</div>
      <div v-if="aggregatedTags.length === 0" class="empty-hint">所选文件暂无标签</div>
      <div v-else class="tag-list">
        <el-tag
          v-for="item in aggregatedTags"
          :key="item.tag.id"
          :color="item.tag.color"
          effect="dark"
          closable
          :class="['existing-tag', { 'is-filtered': filterTagIds.has(item.tag.id) }]"
          @close="confirmRemoveTag(item)"
        >
          {{ item.tag.name }}
          <span class="tag-count">({{ item.count }}/{{ fileStore.selectedCount }})</span>
        </el-tag>
      </div>
    </div>

    <el-divider class="section-divider" />

    <!-- 添加标签：保留原有交互 -->
    <div class="section">
      <div class="section-title">添加标签</div>
      <el-form>
        <el-form-item label="选择标签">
          <el-select
            v-model="selectedTagIds"
            multiple
            placeholder="请选择标签"
            style="width: 100%"
          >
            <el-option
              v-for="tag in tagStore.tags"
              :key="tag.id"
              :label="tag.name"
              :value="tag.id"
              :style="{ backgroundColor: tag.color + '20', color: tag.color }"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="新建标签">
          <el-input
            v-model="newTagName"
            placeholder="输入新标签名称"
            @keyup.enter="addNewTag"
          >
            <template #append>
              <el-button @click="addNewTag">添加</el-button>
            </template>
          </el-input>
        </el-form-item>
      </el-form>
    </div>

    <template #footer>
      <span class="dialog-footer">
        <el-button @click="showAddTagsDialog = false">关闭</el-button>
        <el-button type="primary" :disabled="selectedTagIds.length === 0" @click="applyTags">
          应用添加
        </el-button>
      </span>
    </template>
  </el-dialog>

  <!-- 确认删除对话框 -->
  <el-dialog
    v-model="showDeleteDialog"
    title="确认删除"
    width="400px"
    :close-on-click-modal="false"
  >
    <p>确定要删除选中的 {{ fileStore.selectedCount }} 个文件吗？</p>
    <p class="text-warning">此操作不可撤销</p>
    <template #footer>
      <span class="dialog-footer">
        <el-button @click="showDeleteDialog = false">取消</el-button>
        <el-button type="danger" @click="deleteSelectedFiles">删除</el-button>
      </span>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useFileStore } from '../stores/files'
import { useTagStore } from '../stores/tags'
import { useAppStore } from '../stores/app'
import { fileApi } from '../api/files'
import { pickDistinctColor, PRESET_COLORS } from '../utils/color'
import type { Tag } from '../types'

const fileStore = useFileStore()
const tagStore = useTagStore()
const appStore = useAppStore()

const showAddTagsDialog = ref(false)
const showDeleteDialog = ref(false)
const selectedTagIds = ref<number[]>([])
const newTagName = ref('')

// 当前过滤选中的标签集合，用于在已有标签区高亮
const filterTagIds = computed(() => tagStore.selectedTagIds)

// 聚合所选文件标签：返回 [{ tag, count }]
const aggregatedTags = computed<Array<{ tag: Tag; count: number }>>(() => {
  const counter = new Map<number, number>()
  for (const file of fileStore.selectedFiles) {
    for (const tagId of file.tag_ids) {
      counter.set(tagId, (counter.get(tagId) || 0) + 1)
    }
  }

  const items: Array<{ tag: Tag; count: number }> = []
  for (const [tagId, count] of counter.entries()) {
    const tag = tagStore.getTagById(tagId)
    if (tag) {
      items.push({ tag, count })
    }
  }

  // 当前过滤选中的标签置顶，其余按 count 降序、名称升序
  items.sort((a, b) => {
    const aFiltered = filterTagIds.value.has(a.tag.id) ? 1 : 0
    const bFiltered = filterTagIds.value.has(b.tag.id) ? 1 : 0
    if (aFiltered !== bFiltered) return bFiltered - aFiltered
    if (a.count !== b.count) return b.count - a.count
    return a.tag.name.localeCompare(b.tag.name)
  })
  return items
})

function resetState() {
  selectedTagIds.value = []
  newTagName.value = ''
}

async function addNewTag() {
  if (!newTagName.value.trim()) return

  try {
    const used = tagStore.tags.map(t => t.color).filter((c): c is string => !!c)
    const tag = await tagStore.createTag(
      newTagName.value.trim(),
      pickDistinctColor(used, PRESET_COLORS),
      '',
      appStore.currentWorkspace || undefined,
    )
    selectedTagIds.value.push(tag.id)
    newTagName.value = ''
    ElMessage.success('标签创建成功')
  } catch (error) {
    ElMessage.error('标签创建失败')
    console.error('Failed to create tag:', error)
  }
}

async function applyTags() {
  if (!selectedTagIds.value.length) {
    ElMessage.warning('请选择标签')
    return
  }

  const selectedFileIds = Array.from(fileStore.selectedIds)

  try {
    await tagStore.assignTagsToFiles(selectedFileIds, selectedTagIds.value)
    ElMessage.success('标签添加成功')
    selectedTagIds.value = []
  } catch (error) {
    ElMessage.error('标签添加失败')
    console.error('Failed to update tags:', error)
  }
}

async function confirmRemoveTag(item: { tag: Tag; count: number }) {
  try {
    await ElMessageBox.confirm(
      `从 ${item.count} 个文件中移除标签 “${item.tag.name}”？`,
      '确认移除',
      {
        confirmButtonText: '移除',
        cancelButtonText: '取消',
        type: 'warning',
      },
    )
  } catch {
    return // 用户取消
  }

  // 仅向带有该标签的文件发起请求，避免无谓写入
  const targetFileIds = fileStore.selectedFiles
    .filter(f => f.tag_ids.includes(item.tag.id))
    .map(f => f.id)

  if (!targetFileIds.length) return

  try {
    await tagStore.removeTagFromFiles(targetFileIds, item.tag.id)
    ElMessage.success(`已从 ${targetFileIds.length} 个文件移除标签`)
  } catch (error) {
    ElMessage.error('标签移除失败')
    console.error('Failed to remove tag from files:', error)
  }
}

function confirmDelete() {
  showDeleteDialog.value = true
}

async function deleteSelectedFiles() {
  const selectedFileIds = Array.from(fileStore.selectedIds)

  try {
    for (const fileId of selectedFileIds) {
      await fileApi.delete(fileId)
      fileStore.removeFile(fileId)
    }
    ElMessage.success('文件删除成功')
    showDeleteDialog.value = false
  } catch (error) {
    ElMessage.error('文件删除失败')
    console.error('Failed to delete files:', error)
  }
}

defineExpose({ openAddTags: () => { showAddTagsDialog.value = true }, confirmDelete })
</script>

<style scoped>
.selection-summary {
  font-size: 13px;
  color: var(--color-text-tertiary);
  margin-bottom: 12px;
}

.section {
  margin-bottom: 4px;
}

.section-title {
  font-size: 13px;
  color: var(--color-text-secondary);
  margin-bottom: 8px;
}

.section-divider {
  margin: 12px 0;
}

.empty-hint {
  font-size: 13px;
  color: var(--color-text-tertiary);
  padding: 4px 0;
}

.tag-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.existing-tag {
  cursor: default;
}

.existing-tag.is-filtered {
  outline: 2px solid var(--el-color-primary);
  outline-offset: 1px;
}

.tag-count {
  margin-left: 4px;
  font-size: 11px;
  opacity: 0.85;
}

.text-warning {
  color: var(--color-warning);
  margin-top: 8px;
}
</style>
