<template>
  <div
    class="file-list-item"
    :class="{ selected }"
  >
    <el-icon class="icon" :size="24">
      <Picture v-if="file.type === 'image'" />
      <Document v-else-if="file.type === 'doc'" />
      <VideoCamera v-else-if="file.type === 'video'" />
      <Headset v-else-if="file.type === 'audio'" />
      <Folder v-else />
    </el-icon>
    
    <div class="info">
      <div class="name">{{ file.name }}</div>
      <div class="path">{{ file.path }}</div>
    </div>
    
    <div class="tags">
      <span
        v-for="tag in tagsInfo"
        :key="tag.id"
        class="tag-chip"
        :style="{ backgroundColor: tag.color + '20', color: tag.color }"
      >
        {{ tag.name }}
      </span>
    </div>
    
    <div class="meta">
      <span class="size">{{ formatSize(file.size) }}</span>
      <span class="date">{{ formatDate(file.modified_at) }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Picture, Document, VideoCamera, Headset, Folder } from '@element-plus/icons-vue'
import { useTagStore } from '../stores/tags'
import type { FileItem } from '../types'
import { computed } from 'vue'

const props = defineProps<{
  file: FileItem
  selected: boolean
}>()

const tagStore = useTagStore()

// 缓存标签信息，避免重复计算
const tagsInfo = computed(() => {
  return props.file.tag_ids.map(tagId => {
    const tag = tagStore.getTagById(tagId)
    return {
      id: tagId,
      name: tag?.name || 'Unknown',
      color: tag?.color || '#ccc'
    }
  })
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
  return new Date(timestamp * 1000).toLocaleDateString()
}
</script>

<style scoped>
/* 行盒子约束在 RecycleScroller 固定的 60px 行高内（box-sizing + height:calc），
   通过上下外边距在相邻行高亮之间留出间隙、左右外边距做内嵌，
   配合圆角让选中/悬停高亮完整落在自身条目范围内，避免相邻高亮贴合重叠。 */
.file-list-item {
  display: flex;
  align-items: center;
  gap: 12px;
  box-sizing: border-box;
  height: 52px;
  margin: 4px 8px;
  padding: 6px 12px;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.2s ease;
}

.file-list-item:hover {
  background: var(--color-bg-secondary);
}

.file-list-item.selected {
  background: var(--color-accent-light);
  box-shadow: inset 0 0 0 1px var(--color-accent);
}

.icon {
  color: var(--color-text-tertiary);
  flex-shrink: 0;
}

.info {
  flex: 1;
  min-width: 0;
}

.name {
  font-size: 14px;
  color: var(--color-text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.path {
  font-size: 12px;
  color: var(--color-text-tertiary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin-top: 2px;
}

.tags {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}

.tag-chip {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 10px;
}

.meta {
  display: flex;
  gap: 16px;
  font-size: 12px;
  color: var(--color-text-secondary);
  flex-shrink: 0;
}
</style>
