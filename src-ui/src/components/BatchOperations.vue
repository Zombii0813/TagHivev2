<template>
  <!-- 批量管理标签对话框 -->
  <el-dialog
    v-model="showAddTagsDialog"
    title="批量管理标签"
    width="min(460px, 92vw)"
    @close="resetState"
    :close-on-click-modal="!submitting"
    :close-on-press-escape="!submitting"
    :show-close="!submitting"
  >
    <div class="selection-summary">
      已选 {{ targets.length }} 个文件
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
          <span class="tag-count">({{ item.count }}/{{ targets.length }})</span>
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
        <el-button type="primary" :loading="submitting" :disabled="submitting || selectedTagIds.length === 0" @click="applyTags">
          应用添加
        </el-button>
      </span>
    </template>
  </el-dialog>

  <!-- 确认删除对话框 -->
  <el-dialog
    v-model="showDeleteDialog"
    title="确认删除"
    width="min(400px, 92vw)"
    :close-on-click-modal="false"
    :close-on-press-escape="!submitting"
    :show-close="!submitting"
  >
    <p>确定要删除选中的 {{ targets.length }} 个文件吗？</p>
    <p class="text-warning">文件将移入系统回收站，可在回收站中恢复</p>
    <ul class="delete-targets"><li v-for="file in targets" :key="file.id">{{ file.name }}</li></ul>
    <p v-if="failures.length" role="alert">失败 {{ failures.length }} 项：{{ failures.join('；') }}。再次点击删除将仅重试失败项。</p>
    <template #footer>
      <span class="dialog-footer">
        <el-button :disabled="submitting" @click="showDeleteDialog = false">取消</el-button>
        <el-button type="danger" :loading="submitting" @click="deleteSelectedFiles">删除</el-button>
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
import type { Tag, FileSummary } from '../types'

const fileStore = useFileStore()
const tagStore = useTagStore()
const appStore = useAppStore()

const showAddTagsDialog = ref(false)
const showDeleteDialog = ref(false)
const selectedTagIds = ref<number[]>([])
const newTagName = ref('')
const submitting = ref(false)
const targets = ref<FileSummary[]>([])
const failures = ref<string[]>([])
function captureTargets(files = fileStore.selectedFiles) {
  targets.value = files.map(f => ({ ...f, tag_ids: [...f.tag_ids] }))
  failures.value = []
}

function openAddTags() {
  if (submitting.value || fileStore.activeTab.queryError || fileStore.activeTab.queryKey !== fileStore.activeTab.appliedQuery) return
  captureTargets()
  showAddTagsDialog.value = true
}

// 当前过滤选中的标签集合，用于在已有标签区高亮
const filterTagIds = computed(() => tagStore.selectedTagIds)

// 聚合所选文件标签：返回 [{ tag, count }]
const aggregatedTags = computed<Array<{ tag: Tag; count: number }>>(() => {
  const counter = new Map<number, number>()
  for (const file of targets.value) {
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
  if (submitting.value) return
  if (!selectedTagIds.value.length) {
    ElMessage.warning('请选择标签')
    return
  }

  const selectedFileIds = targets.value.map(f => f.id)

  const tagIds = [...selectedTagIds.value]
  submitting.value = true
  try {
    await tagStore.assignTagsToFiles(selectedFileIds, tagIds)
    targets.value.forEach(f => { f.tag_ids = [...new Set([...f.tag_ids, ...tagIds])] })
    ElMessage.success('标签添加成功')
    selectedTagIds.value = []
  } catch (error) {
    ElMessage.error('标签添加失败')
    console.error('Failed to update tags:', error)
  } finally { submitting.value = false }
}

async function confirmRemoveTag(item: { tag: Tag; count: number }) {
  if (submitting.value) return
  const targetFileIds = targets.value.filter(f => f.tag_ids.includes(item.tag.id)).map(f => f.id)
  const tagId = item.tag.id
  submitting.value = true
  try {
    try { await ElMessageBox.confirm(`从 ${targetFileIds.length} 个文件中移除标签 “${item.tag.name}”？`, '确认移除', { type: 'warning' }) }
    catch { return }
    await tagStore.removeTagFromFiles(targetFileIds, tagId)
    targets.value.forEach(f => { f.tag_ids = f.tag_ids.filter(id => id !== tagId) })
    ElMessage.success('标签已移除')
  } catch { ElMessage.error('标签移除失败') }
  finally { submitting.value = false }
}

function confirmDelete(files?: FileSummary[]) {
  if (submitting.value || fileStore.activeTab.queryError || fileStore.activeTab.queryKey !== fileStore.activeTab.appliedQuery) return
  captureTargets(files)
  showDeleteDialog.value = true
}

async function deleteSelectedFiles() {
  if (submitting.value) return
  const snapshot = [...targets.value]
  const failed: FileSummary[] = []
  failures.value = []
  submitting.value = true
  try {
    for (const file of snapshot) {
      try { await fileApi.delete(file.id); fileStore.removeFile(file.id) }
      catch { failed.push(file); failures.value.push(file.name) }
    }
    targets.value = failed
    const succeeded = snapshot.length - failed.length
    if (failed.length) ElMessage.warning(`已移入回收站 ${succeeded} 项，失败 ${failed.length} 项`)
    else { ElMessage.success(`已移入回收站 ${succeeded} 项`); showDeleteDialog.value = false }
  } finally { submitting.value = false }
}

defineExpose({ openAddTags, confirmDelete })
</script>

<style scoped>
.delete-targets { max-height: 180px; overflow: auto; padding-left: 20px; overflow-wrap: anywhere; }
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
