<template>
  <!-- 批量添加标签对话框 -->
  <el-dialog
    v-model="showAddTagsDialog"
    title="批量添加标签"
    width="400px"
  >
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
    <template #footer>
      <span class="dialog-footer">
        <el-button @click="showAddTagsDialog = false">取消</el-button>
        <el-button type="primary" @click="applyTags">应用</el-button>
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
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useFileStore } from '../stores/files'
import { useTagStore } from '../stores/tags'
import { useAppStore } from '../stores/app'
import { fileApi } from '../api/files'

const fileStore = useFileStore()
const tagStore = useTagStore()
const appStore = useAppStore()

const showAddTagsDialog = ref(false)
const showDeleteDialog = ref(false)
const selectedTagIds = ref<number[]>([])
const newTagName = ref('')

async function addNewTag() {
  if (!newTagName.value.trim()) return

  try {
    const tag = await tagStore.createTag(
      newTagName.value.trim(),
      '#409eff',
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
    showAddTagsDialog.value = false
    selectedTagIds.value = []
  } catch (error) {
    ElMessage.error('标签添加失败')
    console.error('Failed to update tags:', error)
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
.text-warning {
  color: var(--color-warning);
  margin-top: 8px;
}
</style>
