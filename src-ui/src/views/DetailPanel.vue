<template>
  <aside class="detail-panel">
    <div v-if="!selectedFile" class="empty">
      <el-empty description="选择一个文件查看详情" />
    </div>
    
    <template v-else>
      <!-- 文件预览 -->
      <div class="preview">
        <img
          v-if="selectedFile.type === 'image'"
          :src="previewUrl"
          :alt="selectedFile.name"
        />
        <video
          v-else-if="selectedFile.type === 'video'"
          :key="previewUrl"
          :src="previewUrl"
          controls
          preload="metadata"
          crossorigin="anonymous"
          playsinline
          @error="handleVideoError"
        />
        <div v-else class="icon-preview">
          <el-icon :size="64">
            <Document v-if="selectedFile.type === 'doc'" />
            <Headset v-else-if="selectedFile.type === 'audio'" />
            <Folder v-else />
          </el-icon>
        </div>
      </div>

      <!-- 文件信息 -->
      <div class="info">
        <h3 class="name">{{ selectedFile.name }}</h3>
        
        <div class="meta-list">
          <div class="meta-item">
            <span class="label">类型</span>
            <span class="value">{{ selectedFile.type }}</span>
          </div>
          <div class="meta-item">
            <span class="label">大小</span>
            <span class="value">{{ formatSize(selectedFile.size) }}</span>
          </div>
          <div class="meta-item">
            <span class="label">路径</span>
            <span class="value path" :title="selectedFile.path">{{ selectedFile.path }}</span>
          </div>
          <div class="meta-item">
            <span class="label">修改时间</span>
            <span class="value">{{ formatDate(selectedFile.modified_at) }}</span>
          </div>
        </div>
      </div>

      <!-- 标签管理 -->
      <div class="tags-section">
        <div class="section-header">
          <h4>标签</h4>
          <el-button
            type="primary"
            link
            :icon="Edit"
            @click="showTagDialog = true"
          >
            编辑
          </el-button>
        </div>
        
        <div class="tag-list">
          <el-tag
            v-for="tag in fileTags"
            :key="tag.id"
            :color="tag.color"
            effect="dark"
          >
            {{ tag.name }}
          </el-tag>
          <span v-if="!fileTags.length" class="no-tags">无标签</span>
        </div>
      </div>

      <!-- 操作按钮 -->
      <div class="actions">
        <el-button type="primary" @click="openFile">
          <el-icon><FolderOpened /></el-icon>
          打开文件
        </el-button>
        <el-button @click="openFolder">
          <el-icon><Folder /></el-icon>
          打开所在文件夹
        </el-button>
        <el-button type="danger" plain @click="deleteFile">
          <el-icon><Delete /></el-icon>
          删除记录
        </el-button>
      </div>
    </template>

    <!-- 标签编辑对话框 -->
    <el-dialog
      v-model="showTagDialog"
      title="编辑标签"
      width="400px"
    >
      <el-checkbox-group v-model="selectedTagIds">
        <el-checkbox
          v-for="tag in tagStore.tags"
          :key="tag.id"
          :label="tag.id"
        >
          <span
            class="tag-dot"
            :style="{ backgroundColor: tag.color }"
          ></span>
          {{ tag.name }}
        </el-checkbox>
      </el-checkbox-group>
      <template #footer>
        <el-button @click="showTagDialog = false">取消</el-button>
        <el-button type="primary" @click="saveTags">保存</el-button>
      </template>
    </el-dialog>
  </aside>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Document, Headset, Folder, FolderOpened, Delete, Edit } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { open } from '@tauri-apps/plugin-shell'
import { invoke } from '@tauri-apps/api/core'
import { useFileStore } from '../stores/files'
import { useTagStore } from '../stores/tags'
import { fileApi } from '../api/files'
import { thumbnailApi } from '../api/thumbnails'

const fileStore = useFileStore()
const tagStore = useTagStore()

const showTagDialog = ref(false)
const selectedTagIds = ref<number[]>([])

const selectedFile = computed(() => {
  return fileStore.selectedFiles[0]
})

const previewUrl = computed(() => {
  if (!selectedFile.value) return ''
  // 图片使用缩略图API
  if (selectedFile.value.type === 'image') {
    return thumbnailApi.getThumbnailUrl(selectedFile.value.id, 'large')
  }
  // 视频使用原始文件URL
  if (selectedFile.value.type === 'video') {
    return thumbnailApi.getFileUrl(selectedFile.value.id)
  }
  return ''
})

const fileTags = computed(() => {
  if (!selectedFile.value) return []
  return tagStore.getTagsByIds(selectedFile.value.tag_ids)
})

function handleVideoError(event: Event) {
  const video = event.target as HTMLVideoElement
  console.error('Video error:', video.error)
  ElMessage.error('视频加载失败，请检查文件是否存在')
}

watch(() => selectedFile.value, (file) => {
  if (file) {
    selectedTagIds.value = [...file.tag_ids]
  }
})

function formatSize(bytes: number): string {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i]
}

function formatDate(timestamp: number | undefined): string {
  if (!timestamp) return '-'
  return new Date(timestamp * 1000).toLocaleString()
}

async function openFile() {
  if (!selectedFile.value) return
  try {
    // 使用Tauri后端打开文件
    await invoke('open_file', { path: selectedFile.value.path })
  } catch (error) {
    console.error('Failed to open file:', error)
    // 降级到前端shell打开
    await open(selectedFile.value.path)
  }
}

async function openFolder() {
  if (!selectedFile.value) return
  try {
    const folderPath = selectedFile.value.path.substring(0, selectedFile.value.path.lastIndexOf('\\') + 1)
    // 使用Tauri后端打开文件夹
    await invoke('open_folder', { path: folderPath })
  } catch (error) {
    console.error('Failed to open folder:', error)
    // 降级到前端shell打开
    const folderPath = selectedFile.value.path.substring(0, selectedFile.value.path.lastIndexOf('\\') + 1)
    await open(folderPath)
  }
}

async function deleteFile() {
  if (!selectedFile.value) return
  
  try {
    await ElMessageBox.confirm('确定要删除此文件记录吗？', '确认删除', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
    
    await fileApi.delete(selectedFile.value.id)
    fileStore.removeFile(selectedFile.value.id)
    ElMessage.success('删除成功')
  } catch (error) {
    // 用户取消
  }
}

async function saveTags() {
  if (!selectedFile.value) return
  
  try {
    await fileApi.updateTags(selectedFile.value.id, {
      tag_ids: selectedTagIds.value,
      mode: 'replace',
    })
    fileStore.updateFileTags(selectedFile.value.id, selectedTagIds.value)
    // 刷新标签列表以更新 file_count
    await tagStore.loadTags()
    showTagDialog.value = false
    ElMessage.success('标签更新成功')
  } catch (error) {
    ElMessage.error('标签更新失败')
  }
}
</script>

<style scoped>
.detail-panel {
  width: var(--detail-panel-width);
  flex-shrink: 0;
  border-left: 1px solid var(--color-border);
  background: var(--color-bg-secondary);
  display: flex;
  flex-direction: column;
  overflow-y: auto;
}

.empty {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}

.preview {
  aspect-ratio: 16 / 9;
  background: var(--color-bg-tertiary);
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}

.preview img,
.preview video {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
}

.icon-preview {
  color: var(--color-text-tertiary);
}

.info {
  padding: 16px;
  border-bottom: 1px solid var(--color-border);
}

.name {
  font-size: 16px;
  font-weight: 600;
  color: var(--color-text-primary);
  margin: 0 0 12px 0;
  word-break: break-all;
}

.meta-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.meta-item {
  display: flex;
  font-size: 13px;
}

.label {
  width: 80px;
  color: var(--color-text-tertiary);
  flex-shrink: 0;
}

.value {
  color: var(--color-text-primary);
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.value.path {
  font-family: monospace;
  font-size: 11px;
}

.tags-section {
  padding: 16px;
  border-bottom: 1px solid var(--color-border);
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.section-header h4 {
  margin: 0;
  font-size: 14px;
  color: var(--color-text-secondary);
}

.tag-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.no-tags {
  font-size: 13px;
  color: var(--color-text-tertiary);
}

.actions {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.actions .el-button {
  justify-content: flex-start;
}
</style>
