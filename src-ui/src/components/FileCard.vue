<template>
  <div
    class="file-card"
    :class="{ selected }"
    :title="file.name"
  >
    <div class="thumbnail">
      <img v-if="isImage" :src="thumbnailUrl" :alt="file.name" loading="lazy" />
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
    <div v-if="file.tag_ids.length" class="tags-indicator">
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
import { computed } from 'vue'
import { Document, VideoCamera, Headset, Folder } from '@element-plus/icons-vue'
import { useTagStore } from '../stores/tags'
import type { FileItem } from '../types'

const props = defineProps<{
  file: FileItem
  selected: boolean
}>()

const tagStore = useTagStore()

const isImage = computed(() => props.file.type === 'image')

const thumbnailUrl = computed(() => {
  // 这里应该使用实际的缩略图服务
  return `file://${props.file.path}`
})

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
  padding: 12px;
  border-radius: 8px;
  border: 2px solid transparent;
  background: var(--color-bg-primary);
  cursor: pointer;
  transition: all 0.2s ease;
}

.file-card:hover {
  border-color: var(--color-accent);
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.1);
}

.file-card.selected {
  border-color: var(--color-accent);
  background: rgba(64, 158, 255, 0.05);
}

.thumbnail {
  aspect-ratio: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-bg-secondary);
  border-radius: 4px;
  overflow: hidden;
}

.thumbnail img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.info {
  margin-top: 8px;
}

.name {
  font-size: 13px;
  font-weight: 500;
  color: var(--color-text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 4px;
  font-size: 11px;
  color: var(--color-text-tertiary);
}

.tags-indicator {
  display: flex;
  gap: 4px;
  margin-top: 8px;
}

.tag-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}
</style>
