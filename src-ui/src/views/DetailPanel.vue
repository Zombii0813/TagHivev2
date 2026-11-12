<template>
  <aside class="detail-panel">
    <el-button aria-label="关闭详情" @click="appStore.toggleDetailPanel()">关闭详情</el-button>
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
          @load="thumb.onLoad"
          @error="thumb.onError"
          class="preview-media"
        />
        <button v-if="selectedFile.type === 'image' && thumb.status.value === 'error'" @click="thumb.retry">预览失败，重试</button>
        <video
          v-if="selectedFile.type === 'video'"
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
        <div v-if="!['image', 'video'].includes(selectedFile.type)" class="icon-preview">
          <el-icon :size="64">
            <Document v-if="selectedFile.type === 'doc'" />
            <Headset v-else-if="selectedFile.type === 'audio'" />
            <Folder v-else />
          </el-icon>
        </div>
      </div>

      <!-- 文件信息 -->
      <div class="info">
        <!-- 文件名即「打开文件」入口：与下方路径点击打开目录形成一组对称操作，
             不占额外纵向空间，也避免与视频播放器控件区域争抢点击 -->
        <h3
          class="name name-link"
          role="button"
          tabindex="0"
          :title="`打开文件：${selectedFile.name}`"
          @click="openFile"
          @keydown.enter.prevent="openFile"
          @keydown.space.prevent="openFile"
        >{{ selectedFile.name }}</h3>
        
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
            <span
              class="value value-link path-value"
              :class="{ 'path-expanded': pathExpanded }"
              role="button"
              tabindex="0"
              title="打开所在文件夹"
              @click="openFolder"
              @keydown.enter.prevent="openFolder"
              @keydown.space.prevent="openFolder"
            >{{ selectedFile.path }}</span>
          </div>
          <div class="path-actions">
            <el-button size="small" @click="pathExpanded = !pathExpanded">{{ pathExpanded ? '收起路径' : '展开路径' }}</el-button>
            <el-button size="small" @click="copyPath">复制路径</el-button>
          </div>
          <div class="meta-item">
            <span class="label">修改时间</span>
            <span class="value">{{ formatDate(selectedFile.modified_at) }}</span>
          </div>

          <!-- 视频/音频专属属性：由后端惰性探测，加载中先占位 -->
          <template v-if="showMediaMeta">
            <div class="meta-item">
              <span class="label">时长</span>
              <span class="value">{{ mediaText(formatDuration(mediaInfo?.duration)) }}</span>
            </div>
            <div v-if="selectedFile.type === 'video'" class="meta-item">
              <span class="label">分辨率</span>
              <span class="value">{{ mediaText(formatResolution(mediaInfo?.width, mediaInfo?.height)) }}</span>
            </div>
            <div class="meta-item">
              <span class="label">比特率</span>
              <span class="value">{{ mediaText(formatBitrate(mediaInfo?.bitrate)) }}</span>
            </div>
          </template>
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
            @click="openTagDialog"
            class="add-tag-btn"
          >
            添加
          </el-button>
          <span v-if="!fileTags.length" class="no-tags">无标签</span>
        </div>
      </div>

    </template>

    <!-- 标签编辑对话框 -->
    <el-dialog
      v-model="showTagDialog"
      title="编辑标签"
      :close-on-click-modal="!submitting"
      :close-on-press-escape="!submitting"
      :show-close="!submitting"
      width="min(400px, 92vw)"
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
        <el-button type="primary"  :loading="submitting" @click="saveTags">保存</el-button>
      </template>
    </el-dialog>
  </aside>
</template>

<script setup lang="ts">
import { computed, ref, watch, onBeforeUnmount } from 'vue'
import { useThumbnail } from '../composables/useThumbnail'
import { Document, Headset, Folder, Plus } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { open } from '@tauri-apps/plugin-shell'
import { invoke } from '@tauri-apps/api/core'
import { useAppStore } from '../stores/app'
import { useFileStore } from '../stores/files'
import { useTagStore } from '../stores/tags'
import { fileApi } from '../api/files'
import { thumbnailApi } from '../api/thumbnails'
import type { FileSummary, MediaInfo } from '../types'

const fileStore = useFileStore()
const appStore = useAppStore()
const tagStore = useTagStore()
const pathExpanded = ref(false)
async function copyPath() {
  const path = selectedFile.value?.path
  if (!path) return
  try { await navigator.clipboard.writeText(path); ElMessage.success('路径已复制') }
  catch { ElMessage.error('复制失败，请展开路径后手动复制') }
}

const showTagDialog = ref(false)
const selectedTagIds = ref<number[]>([])
const videoRef = ref<HTMLVideoElement | null>(null)
const videoAspectRatio = ref(16 / 9)

// 媒体元数据（时长/分辨率/比特率）：后端惰性探测，前端按当前选中文件异步拉取
const mediaInfo = ref<MediaInfo | null>(null)
const mediaLoading = ref(false)
// 请求失败（sidecar 未就绪 / 端点不可用 / 超时）单独标记，
// 与「文件本身探测不出元数据」区分开，避免两种情况都显示 '-' 无从排查
const mediaError = ref(false)
// 记录发起请求时的文件 id，用于丢弃快速切换选中项时的过期响应
let mediaRequestId: number | null = null

function onVideoLoaded(event: Event) {
  const video = event.target as HTMLVideoElement
  if (video.videoWidth && video.videoHeight) {
    videoAspectRatio.value = video.videoWidth / video.videoHeight
  }
}

const selectedFile = computed(() => {
  return fileStore.activeFile
})

const thumb = useThumbnail(selectedFile, 'large')
onBeforeUnmount(() => {
  const video = videoRef.value
  if (video) { video.pause(); video.removeAttribute('src'); video.load() }
  mediaRequestId = null
})
const submitting = ref(false)
const editFileId = ref<number | null>(null)
function openTagDialog() {
  if (!selectedFile.value) return
  editFileId.value = selectedFile.value.id
  selectedTagIds.value = [...selectedFile.value.tag_ids]
  showTagDialog.value = true
}

// 浏览器 <video> 可原生播放的容器；其余走服务端转码流
const NATIVE_PLAYABLE = new Set(['mp4', 'webm', 'ogg', 'ogv', 'mov', 'm4v'])

function isNativePlayable(file: { ext?: string; name?: string }): boolean {
  const ext = (file.ext || file.name?.split('.').pop() || '')
    .toLowerCase()
    .replace(/^\./, '')
  return NATIVE_PLAYABLE.has(ext)
}

const previewUrl = computed(() => {
  if (!selectedFile.value) return ''
  // 图片使用缩略图API
  if (selectedFile.value.type === 'image') {
    return thumb.url.value
  }
  // 视频：原生格式直传原始文件，其余走转码流（ts/rmvb/wmv 等）
  if (selectedFile.value.type === 'video') {
    return isNativePlayable(selectedFile.value)
      ? thumbnailApi.getFileUrl(selectedFile.value.id)
      : thumbnailApi.getTranscodeUrl(selectedFile.value.id)
  }
  return ''
})

const fileTags = computed(() => {
  if (!selectedFile.value) return []
  return tagStore.getTagsByIds(selectedFile.value.tag_ids)
})

// 仅视频/音频展示媒体属性行（音频无分辨率，模板内单独判断）
const showMediaMeta = computed(() => {
  const type = selectedFile.value?.type
  return type === 'video' || type === 'audio'
})

// 拉取当前文件的媒体元数据；非媒体文件直接清空，不发请求
async function loadMediaInfo(fileId: number | null) {
  mediaInfo.value = null
  mediaError.value = false
  mediaRequestId = fileId

  if (fileId === null || !showMediaMeta.value) {
    mediaLoading.value = false
    return
  }

  // 列表接口已带回媒体字段：后端此前探测过，直接同步渲染，
  // 与文件名/大小等属性同一帧出现，不发请求也无加载态
  const cached = selectedFile.value
  if (cached && cached.id === fileId && hasMediaFields(cached)) {
    mediaInfo.value = {
      file_id: fileId,
      duration: cached.duration,
      width: cached.width,
      height: cached.height,
      bitrate: cached.bitrate,
    }
    mediaLoading.value = false
    return
  }

  mediaLoading.value = true
  try {
    const info = await fileApi.getMediaInfo(fileId)
    // 请求期间用户已切到别的文件：丢弃过期结果
    if (mediaRequestId !== fileId) return
    mediaInfo.value = info
    // 回填到列表数据，使本会话内再次选中该文件时走同步分支（无请求、无加载态）
    fileStore.updateFileMediaInfo(fileId, info)
  } catch (error) {
    if (mediaRequestId !== fileId) return
    console.error('Failed to load media info:', error)
    mediaInfo.value = null
    mediaError.value = true
  } finally {
    if (mediaRequestId === fileId) {
      mediaLoading.value = false
    }
  }
}

// 列表数据里是否已带回媒体元数据（即后端此前已探测过该文件）。
// 视频看分辨率、音频看时长/比特率——音频本身没有分辨率，不能只判 width。
function hasMediaFields(file: FileSummary): boolean {
  if (file.type === 'video') {
    return file.width != null && file.height != null
  }
  return file.duration != null || file.bitrate != null
}

// 媒体属性的三态显示：加载中 / 请求失败 / 已取到值（取不到时为 '-'）
function mediaText(formatted: string): string {
  if (mediaLoading.value) return '读取中…'
  if (mediaError.value) return '读取失败'
  return formatted
}

// 时长格式化为 HH:MM:SS（不足 1 小时省略小时段）
function formatDuration(seconds?: number | null): string {
  if (!seconds || seconds <= 0 || !Number.isFinite(seconds)) return '-'
  const total = Math.round(seconds)
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total % 60
  const pad = (n: number) => String(n).padStart(2, '0')
  return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${m}:${pad(s)}`
}

// 分辨率格式化为「1920 × 1080」
function formatResolution(width?: number | null, height?: number | null): string {
  if (!width || !height) return '-'
  return `${width} × ${height}`
}

// 比特率格式化：≥1 Mbps 用 Mbps，否则用 kbps
function formatBitrate(bitrate?: number | null): string {
  if (!bitrate || bitrate <= 0) return '-'
  if (bitrate >= 1_000_000) return `${(bitrate / 1_000_000).toFixed(2)} Mbps`
  return `${Math.round(bitrate / 1000)} kbps`
}

async function handleVideoError(event: Event) {
  const video = event.target as HTMLVideoElement
  console.error('Video error:', video.error)
  // 转码流也可能因源编码异常/文件损坏失败：提示并提供系统播放器降级入口
  try {
    await ElMessageBox.confirm(
      '该视频无法在线播放，可能是格式不受支持或文件损坏。是否用系统播放器打开？',
      '无法在线播放',
      { confirmButtonText: '用系统播放器打开', cancelButtonText: '取消', type: 'warning' },
    )
    if (selectedFile.value) {
      await openFile()
    }
  } catch {
    // 用户取消，不做处理
  }
}

watch(() => selectedFile.value, (file) => {
  pathExpanded.value = false
  if (file && !showTagDialog.value) {
    selectedTagIds.value = [...file.tag_ids]
  }
})

// 详情始终跟随最后点选的活动文件，多选数量变化不影响预览和媒体信息。
watch(
  () => selectedFile.value?.id ?? null,
  loadMediaInfo,
  { immediate: true }
)

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

async function confirmRemoveTag(tag: { id: number; name: string; color?: string }) {
  if (!selectedFile.value || submitting.value) return
  const fileId = selectedFile.value.id
  const newTagIds = selectedFile.value.tag_ids.filter(id => id !== tag.id)
  submitting.value = true
  try {
    try {
      await ElMessageBox.confirm(`确定要移除标签 "${tag.name}" 吗？`, '确认移除', { type: 'warning' })
    } catch { return }
    await fileApi.updateTags(fileId, { tag_ids: newTagIds, mode: 'replace' })
    fileStore.updateFileTags(fileId, newTagIds)
    await tagStore.reloadTags()
    ElMessage.success('标签已移除')
  } catch { ElMessage.error('标签移除失败') }
  finally { submitting.value = false }
}

async function saveTags() {
  if (editFileId.value === null || submitting.value) return
  const fileId = editFileId.value
  const tagIds = [...selectedTagIds.value]
  submitting.value = true
  try {
    await fileApi.updateTags(fileId, { tag_ids: tagIds, mode: 'replace' })
    fileStore.updateFileTags(fileId, tagIds)
    await tagStore.reloadTags()
    showTagDialog.value = false
    ElMessage.success('标签更新成功')
  } catch { ElMessage.error('标签更新失败') }
  finally { submitting.value = false }
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
  object-fit: contain;
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

/* 文件名作为「打开文件」入口：与路径字段同一套悬停反馈 */
.name-link {
  position: relative;
  isolation: isolate;
  cursor: pointer;
  width: fit-content;
  max-width: 100%;
  padding: 2px 6px;
  margin: -2px -6px 12px;
  border-radius: 6px;
}

.name-link::before {
  content: '';
  position: absolute;
  inset: 0;
  z-index: -1;
  border-radius: 6px;
  background: linear-gradient(
    135deg,
    var(--color-accent-light) 0%,
    var(--color-bg-hover) 100%
  );
  box-shadow: 0 0 0 1px var(--color-accent-light);
  opacity: 0;
  transition: opacity 0.18s ease;
}

.name-link:hover::before,
.name-link:focus-visible::before {
  opacity: 1;
}

.name-link:focus-visible {
  outline: none;
}

.meta-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.meta-item {
  display: flex;
  /* 字段值自带 6px 左内边距（为悬停背景留出呼吸空间），
     故此处 gap 收窄，标签到文字的视觉间距仍约 8px */
  gap: 2px;
  /* 基线对齐：属性名与字段值的文字底部对齐；
     路径换行成多行时标签仍与首行基线对齐，不会下沉到末行 */
  align-items: baseline;
  font-size: 13px;
  line-height: 1.6;
}

/* 属性名与字段值统一字号/行高，仅颜色区分，保证左对齐后逐行文字底部齐平 */
.label {
  width: 72px;
  flex-shrink: 0;
  text-align: left;
  color: var(--color-text-tertiary);
}

.value {
  flex: 1;
  min-width: 0;
  text-align: left;
  color: var(--color-text-primary);
  /* 统一为可换行：长文本整体折行而非截断，避免与其他行字号不一致 */
  overflow-wrap: anywhere;
  word-break: break-word;
  /* 所有字段值共用同一内边距：链接悬停出现背景框时不产生位移，
     且各行文字起始位置保持一致（含非链接字段） */
  padding: 2px 6px;
  border-radius: 6px;
}

/* 可点击字段（文件名 / 路径）：常态与普通文字完全一致——不着色、不加下划线；
   仅在悬停时浮出圆角渐变背景作为可点击提示 */
.value-link {
  position: relative;
  /* 自成层叠上下文，使 z-index:-1 的伪元素停留在本元素内部
     （否则会沉到面板背景之下而不可见） */
  isolation: isolate;
  cursor: pointer;
  /* 收缩到内容宽度，避免短路径出现横贯整行的高亮块；长路径仍按容器宽度换行 */
  max-width: fit-content;
}

/* 渐变背景由伪元素承载：常态 opacity 0 完全不可见，
   悬停时淡入，避免直接给元素设 background-image 导致常态就有底色 */
.value-link::before {
  content: '';
  position: absolute;
  inset: 0;
  z-index: -1;
  border-radius: 6px;
  /* 沿用全局 .gradient-accent 的 135deg 走向；两端均为主题变量，深浅色自适应 */
  background: linear-gradient(
    135deg,
    var(--color-accent-light) 0%,
    var(--color-bg-hover) 100%
  );
  box-shadow: 0 0 0 1px var(--color-accent-light);
  opacity: 0;
  transition: opacity 0.18s ease;
}

.value-link:hover::before,
.value-link:focus-visible::before {
  opacity: 1;
}

.value-link:focus-visible {
  outline: none;
}

.path-value {
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.path-value.path-expanded { white-space: pre-wrap; overflow-wrap: anywhere; }
.path-actions { display: flex; gap: 8px; justify-content: flex-end; margin-bottom: 8px; }

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

/* 标签区作为面板末节，补足底部留白（原由操作按钮区提供） */
.tags-section:last-child {
  border-bottom: none;
  padding-bottom: 20px;
}
</style>
