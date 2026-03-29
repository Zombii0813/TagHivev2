<template>
  <aside class="detail-panel">
    <div v-if="!selectedFile" class="empty">
      <el-empty description="选择一个文件查看详情" />
    </div>
    
    <template v-else>
      <!-- 文件预览 -->
      <div class="preview" :class="{ 'video-preview': selectedFile.type === 'video' }">
        <img
          v-if="selectedFile.type === 'image'"
          :src="previewUrl"
          :alt="selectedFile.name"
          class="preview-media"
        />
        <video
          v-else-if="selectedFile.type === 'video'"
          ref="videoRef"
          :key="previewUrl"
          :src="previewUrl"
          controls
          preload="metadata"
          crossorigin="anonymous"
          playsinline
          @error="handleVideoError"
          @loadedmetadata="onVideoLoaded"
          class="preview-media video-element"
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
        </div>
        
        <div class="tag-list">
          <el-tag
            v-for="tag in fileTags"
            :key="tag.id"
            :color="tag.color"
            effect="dark"
            closable
            @close="confirmRemoveTag(tag)"
            class="file-tag"
          >
            {{ tag.name }}
          </el-tag>
          <el-button
            type="primary"
            link
            :icon="Plus"
            @click="showTagDialog = true"
            class="add-tag-btn"
          >
            添加
          </el-button>
          <span v-if="!fileTags.length" class="no-tags">无标签</span>
        </div>
      </div>

      <!-- 操作按钮 -->
      <div class="actions">
        <el-button type="primary" class="action-btn" @click="openFile">
          <el-icon><FolderOpened /></el-icon>
          打开文件
        </el-button>
        <el-button class="action-btn" @click="openFolder">
          <el-icon><Folder /></el-icon>
          打开所在文件夹
        </el-button>
        <el-button type="danger" plain class="action-btn" @click="deleteFile">
          <el-icon><Delete /></el-icon>
          删除文件
        </el-button>
      </div>
    </template>

    <!-- 标签编辑对话框 -->
    <el-dialog
      v-model="showTagDialog"
      title="编辑标签"
      width="400px"
      append-to-body
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
import { Document, Headset, Folder, FolderOpened, Delete, Plus } from '@element-plus/icons-vue'
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
const videoRef = ref<HTMLVideoElement | null>(null)
const videoAspectRatio = ref(16 / 9)

function onVideoLoaded(event: Event) {
  const video = event.target as HTMLVideoElement
  if (video.videoWidth && video.videoHeight) {
    videoAspectRatio.value = video.videoWidth / video.videoHeight
  }
}

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
    // 获取文件夹路径（处理Windows和Unix路径）
    const path = selectedFile.value.path
    const lastSlash = path.lastIndexOf('\\') > path.lastIndexOf('/') ? path.lastIndexOf('\\') : path.lastIndexOf('/')
    const folderPath = lastSlash > 0 ? path.substring(0, lastSlash) : path
    // 使用Tauri后端打开文件夹并选中文件
    await invoke('open_folder', { path: folderPath, filePath: selectedFile.value.path })
  } catch (error) {
    console.error('Failed to open folder:', error)
    // 降级到前端shell打开
    const path = selectedFile.value.path
    const lastSlash = path.lastIndexOf('\\') > path.lastIndexOf('/') ? path.lastIndexOf('\\') : path.lastIndexOf('/')
    const folderPath = lastSlash > 0 ? path.substring(0, lastSlash) : path
    await open(folderPath)
  }
}

async function deleteFile() {
  if (!selectedFile.value) return
  
  try {
    await ElMessageBox.confirm('确定要将此文件移至回收站吗？', '确认删除', {
      confirmButtonText: '移至回收站',
      cancelButtonText: '取消',
      type: 'warning',
    })
    
    await fileApi.delete(selectedFile.value.id)
    fileStore.removeFile(selectedFile.value.id)
    ElMessage.success('文件已移至回收站')
  } catch (error) {
    // 用户取消
  }
}

async function confirmRemoveTag(tag: { id: number; name: string; color?: string }) {
  if (!selectedFile.value) return
  
  try {
    await ElMessageBox.confirm(`确定要移除标签 "${tag.name}" 吗？`, '确认移除', {
      confirmButtonText: '移除',
      cancelButtonText: '取消',
      type: 'warning',
    })
    
    // 从当前标签列表中移除
    const newTagIds = selectedFile.value.tag_ids.filter(id => id !== tag.id)
    
    await fileApi.updateTags(selectedFile.value.id, {
      tag_ids: newTagIds,
      mode: 'replace',
    })
    fileStore.updateFileTags(selectedFile.value.id, newTagIds)
    // 刷新标签列表以更新 file_count
    await tagStore.reloadTags()
    ElMessage.success('标签已移除')
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
    await tagStore.reloadTags()
    showTagDialog.value = false
    ElMessage.success('标签更新成功')
  } catch (error) {
    ElMessage.error('标签更新失败')
  }
}
</script>

<style scoped>
.detail-panel {
  /* 默认折叠（宽度为 0），通过 .visible 展开 */
  width: 0;
  flex-shrink: 0;
  border-left: 0px solid var(--color-border);
  background: var(--color-bg-secondary);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  transition: width 0.3s cubic-bezier(0.4, 0, 0.2, 1),
              border-left-width 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.detail-panel.visible {
  width: var(--detail-panel-width);
  border-left-width: 1px;
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

.preview.video-preview {
  aspect-ratio: v-bind('videoAspectRatio');
  max-height: 400px;
}

.preview-media {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.preview-media.video-element {
  object-fit: contain;
  max-width: 100%;
  max-height: 100%;
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
  align-items: center;
}

.file-tag {
  cursor: default;
}

.add-tag-btn {
  padding: 0 8px;
  height: 28px;
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

.action-btn {
  width: 100%;
  min-width: 100%;
  justify-content: flex-start;
  box-sizing: border-box;
  margin: 0 !important;
  margin-left: 0 !important;
  margin-right: 0 !important;
}

.actions .el-button + .el-button {
  margin-left: 0;
}
</style>
