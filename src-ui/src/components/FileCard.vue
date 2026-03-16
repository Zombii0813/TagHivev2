<template>
  <div
    class="file-card"
    :class="{ selected }"
    :title="file.name"
    :style="cardStyle"
  >
    <div class="thumbnail" :style="thumbnailStyle">
      <div v-if="hasThumbnail" class="image-container">
        <!-- 占位符 -->
        <div v-if="!imageLoaded" class="image-placeholder">
          <el-icon :size="32">
            <Picture v-if="file.type === 'image'" />
            <VideoCamera v-else-if="file.type === 'video'" />
          </el-icon>
          <div class="loading-spinner"></div>
        </div>
        <!-- 实际图片 -->
        <img 
          :src="thumbnailUrl" 
          :alt="file.name" 
          loading="lazy"
          @load="handleImageLoad"
          @error="handleImageError"
          :class="{ 'image-loaded': imageLoaded, 'image-error': imageError }"
        />
      </div>
      <el-icon v-else :size="48">
        <Document v-if="file.type === 'doc'" />
        <VideoCamera v-else-if="file.type === 'video'" />
        <Headset v-else-if="file.type === 'audio'" />
        <Folder v-else />
      </el-icon>
    </div>
    <div class="info">
      <div class="name" :title="file.name">{{ file.name }}</div>
      <div class="meta">
        <span class="size">{{ formatSize(file.size) }}</span>
        <span v-if="file.tag_ids.length" class="tag-count">
          {{ file.tag_ids.length }} 个标签
        </span>
      </div>
    </div>
    <div class="tags-indicator">
      <span
        v-for="tagId in file.tag_ids.slice(0, 3)"
        :key="tagId"
        class="tag-dot"
        :style="{ backgroundColor: getTagColor(tagId) }"
      ></span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { Document, VideoCamera, Headset, Folder, Picture } from '@element-plus/icons-vue'
import { useTagStore } from '../stores/tags'
import { thumbnailApi } from '../api/thumbnails'
import type { FileItem } from '../types'

const props = defineProps<{
  file: FileItem
  selected: boolean
  size?: number
}>()

const tagStore = useTagStore()
const imageLoaded = ref(false)
const imageError = ref(false)

const hasThumbnail = computed(() =>
  props.file.type === 'image' || props.file.type === 'video'
)

const thumbnailUrl = computed(() => {
  return thumbnailApi.getThumbnailUrl(props.file.id, 'medium')
})

// 计算缩略图尺寸（预留）
computed(() => {
  if (props.size) {
    return props.size - 16 // 减去 padding
  }
  return 200
})

// 卡片样式
const cardStyle = computed(() => {
  if (props.size) {
    return {
      width: `${props.size}px`,
      maxWidth: `${props.size}px`
    }
  }
  return {}
})

// 缩略图样式
const thumbnailStyle = computed(() => {
  if (props.size) {
    return {
      width: `${props.size - 16}px`, // 减去 padding
      height: `${props.size - 16}px`
    }
  }
  return {}
})

function handleImageLoad() {
  imageLoaded.value = true
  imageError.value = false
}

function handleImageError() {
  imageError.value = true
  imageLoaded.value = false
}

function formatSize(bytes: number): string {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i]
}

function getTagColor(tagId: number): string {
  const tag = tagStore.getTagById(tagId)
  return tag?.color || '#ccc'
}
</script>

<style scoped>
.file-card {
  display: flex;
  flex-direction: column;
  width: 100%;
  padding: 10px;
  border-radius: var(--radius-lg);
  border: 1px solid var(--glass-border);
  background: var(--glass-bg);
  backdrop-filter: var(--glass-blur);
  -webkit-backdrop-filter: var(--glass-blur);
  cursor: pointer;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  box-sizing: border-box;
  box-shadow: var(--shadow-sm);
}

.file-card:hover {
  transform: translateY(-4px) scale(1.02);
  border-color: var(--color-accent);
  box-shadow: var(--shadow-xl), var(--shadow-glow);
}

.file-card.selected {
  border-color: var(--color-accent);
  background: var(--color-accent-light);
  box-shadow: var(--shadow-glow);
  transform: translateY(-2px);
}

.file-card.selected .thumbnail {
  box-shadow: inset 0 0 0 2px var(--color-accent);
}

.thumbnail {
  width: 100%;
  aspect-ratio: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-bg-secondary);
  border-radius: var(--radius-md);
  overflow: hidden;
  flex-shrink: 0;
  transition: all 0.3s ease;
}

.image-container {
  width: 100%;
  height: 100%;
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
}

.image-placeholder {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, var(--color-bg-secondary) 0%, var(--color-bg-tertiary) 100%);
  z-index: 1;
  transition: opacity 0.3s ease;
}

.loading-spinner {
  width: 24px;
  height: 24px;
  margin-top: 8px;
  border: 2px solid rgba(99, 102, 241, 0.2);
  border-top: 2px solid var(--color-accent);
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

.thumbnail img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  opacity: 0;
  transition: opacity 0.4s ease, transform 0.3s ease;
  z-index: 2;
  image-rendering: -webkit-optimize-contrast;
  image-rendering: crisp-edges;
}

.thumbnail img.image-loaded {
  opacity: 1;
}

.thumbnail img.image-error {
  opacity: 0;
}

.file-card:hover .thumbnail img.image-loaded {
  transform: scale(1.05);
}

.image-container .image-loaded {
  opacity: 1;
}

.image-container .image-loaded ~ .image-placeholder {
  opacity: 0;
  pointer-events: none;
}

.info {
  margin-top: 10px;
  min-height: 40px;
}

.name {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  letter-spacing: -0.2px;
}

.meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 4px;
  font-size: 11px;
  color: var(--color-text-tertiary);
  font-weight: 500;
}

.tags-indicator {
  display: flex;
  gap: 4px;
  margin-top: 8px;
  min-height: 8px;
  align-items: center;
}

.tag-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
  transition: transform 0.2s ease;
}

.file-card:hover .tag-dot {
  transform: scale(1.2);
}

/* 选中动画 */
@keyframes selectPulse {
  0% { box-shadow: 0 0 0 0 rgba(99, 102, 241, 0.4); }
  70% { box-shadow: 0 0 0 10px rgba(99, 102, 241, 0); }
  100% { box-shadow: 0 0 0 0 rgba(99, 102, 241, 0); }
}

.file-card.selected {
  animation: selectPulse 0.6s ease-out;
}
</style>
