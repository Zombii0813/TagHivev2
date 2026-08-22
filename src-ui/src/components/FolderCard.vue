<template>
  <div
    class="folder-card"
    :class="{ 'drop-active': isDropActive }"
    :title="dir.name"
    :style="cardStyle"
    draggable="true"
    @dblclick="emit('open', dir)"
    @contextmenu.prevent="emit('contextmenu', dir, $event)"
    @dragstart="handleDragStart"
    @dragend="handleDragEnd"
    @dragenter="handleDragOver"
    @dragover="handleDragOver"
    @dragleave="handleDragLeave"
    @drop="handleDrop"
  >
    <div class="cover" :style="coverStyle">
      <!-- 自定义封面：单张铺满，优先于九宫格 -->
      <div v-if="dir.cover_path" class="cover-custom">
        <img
          :src="customCoverUrl"
          loading="lazy"
          draggable="false"
          @error="onImgError"
        />
      </div>
      <!-- 自动九宫格：2x2 拼图（不足则用占位铺满） -->
      <div v-else-if="coverIds.length" class="cover-grid" :class="`cover-grid--${coverIds.length}`">
        <div v-for="fid in coverIds" :key="fid" class="cover-cell">
          <img
            :src="thumbUrl(fid)"
            loading="lazy"
            draggable="false"
            @error="onImgError"
          />
        </div>
      </div>
      <!-- 空目录 / 无媒体：文件夹图标 -->
      <el-icon v-else :size="52" class="cover-empty">
        <Folder />
      </el-icon>

      <!-- 文件夹角标 -->
      <div class="folder-badge">
        <el-icon :size="14"><FolderOpened /></el-icon>
      </div>
    </div>

    <div class="info">
      <div class="name" :title="dir.name">{{ dir.name }}</div>
      <div class="meta">
        <span class="count">{{ dir.file_count }} 项</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { Folder, FolderOpened } from '@element-plus/icons-vue'
import { thumbnailApi } from '../api/thumbnails'
import type { ChildDir } from '../types'
import {
  setItemDragData,
  clearItemDragState,
  hasItemDrag,
  getItemDrag,
} from '../utils/dragItems'

const props = defineProps<{
  dir: ChildDir
  size?: number
}>()

const emit = defineEmits<{
  // 双击进入目录
  open: [dir: ChildDir]
  contextmenu: [dir: ChildDir, evt: MouseEvent]
  // 有文件/文件夹拖放到本目录卡片上；copy 由 Ctrl/Cmd 决定
  'item-drop': [payload: { targetPath: string; copy: boolean }]
}>()

// 拖拽悬停高亮
const isDropActive = ref(false)

// ─── 拖拽：本卡片作为「文件夹」拖拽源 ──────────────────────────
function handleDragStart(event: DragEvent) {
  setItemDragData(event, {
    kind: 'folder',
    folderPath: props.dir.path,
    label: props.dir.name,
  })
}

function handleDragEnd() {
  clearItemDragState()
  isDropActive.value = false
}

// ─── 拖拽：本卡片作为放置目标 ─────────────────────────────────
// 与 FolderTreeNode 同构：hasItemDrag 读 dataTransfer.types（drop 前唯一可靠的
// 来源判定），getItemDrag 读模块级兜底（部分场景 types 取不到）。
function handleDragOver(event: DragEvent) {
  if (!hasItemDrag(event) && !getItemDrag()) return
  const drag = getItemDrag()
  // 文件夹拖到自身上不允许
  if (drag?.kind === 'folder' && drag.folderPath === props.dir.path) return
  event.preventDefault()
  // 阻止冒泡到 .explorer-scroll 的空白区落点，否则会同时高亮两处
  event.stopPropagation()
  isDropActive.value = true
  if (event.dataTransfer) {
    event.dataTransfer.dropEffect = event.ctrlKey || event.metaKey ? 'copy' : 'move'
  }
}

function handleDragLeave(event: DragEvent) {
  // 在卡片内部子元素之间移动也会触发 dragleave，此时不应撤掉高亮
  const to = event.relatedTarget as Node | null
  const el = event.currentTarget as HTMLElement
  if (to && el.contains(to)) return
  isDropActive.value = false
}

function handleDrop(event: DragEvent) {
  if (!hasItemDrag(event) && !getItemDrag()) return
  event.preventDefault()
  event.stopPropagation()
  isDropActive.value = false
  emit('item-drop', { targetPath: props.dir.path, copy: event.ctrlKey || event.metaKey })
}

// 最多取 4 张拼 2x2 封面
const coverIds = computed(() => props.dir.cover_file_ids.slice(0, 4))

// 自定义封面 URL（按路径出图）
const customCoverUrl = computed(() =>
  props.dir.cover_path ? thumbnailApi.getThumbnailUrlByPath(props.dir.cover_path, 'medium') : ''
)

function thumbUrl(fileId: number): string {
  return thumbnailApi.getThumbnailUrl(fileId, 'small')
}

// 缩略图加载失败时隐藏该格，避免破图占位
function onImgError(e: Event) {
  const el = e.target as HTMLImageElement
  el.style.visibility = 'hidden'
}

const cardStyle = computed(() => {
  if (props.size) {
    return { width: `${props.size}px`, maxWidth: `${props.size}px` }
  }
  return {}
})

const coverStyle = computed(() => {
  if (props.size) {
    const inner = props.size - 20
    return { width: `${inner}px`, height: `${inner}px` }
  }
  return {}
})
</script>

<style scoped>
.folder-card {
  position: relative;
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

.folder-card:hover {
  transform: translateY(-4px) scale(1.02);
  border-color: var(--color-accent);
  box-shadow: var(--shadow-xl), var(--shadow-glow);
}

/* 拖拽悬停：作为放置目标时的高亮 */
.folder-card.drop-active {
  border-color: var(--color-accent);
  border-style: dashed;
  box-shadow: var(--shadow-xl), var(--shadow-glow);
}

.cover {
  position: relative;
  aspect-ratio: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  align-self: center;
  background: var(--color-bg-secondary);
  border-radius: var(--radius-md);
  overflow: hidden;
  flex-shrink: 0;
}

/* 自定义封面：单张铺满 */
.cover-custom {
  width: 100%;
  height: 100%;
}

.cover-custom img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.folder-card:hover .cover-custom img {
  transform: scale(1.05);
  transition: transform 0.3s ease;
}

/* 2x2 九宫格封面 */
.cover-grid {
  width: 100%;
  height: 100%;
  display: grid;
  gap: 2px;
  grid-template-columns: 1fr 1fr;
  grid-template-rows: 1fr 1fr;
  background: var(--color-bg-tertiary);
}

/* 单张封面铺满，两张横向平分，三张时第一张跨整行 */
.cover-grid--1 {
  grid-template-columns: 1fr;
  grid-template-rows: 1fr;
}
.cover-grid--2 {
  grid-template-rows: 1fr;
}
.cover-grid--3 .cover-cell:first-child {
  grid-column: span 2;
}

.cover-cell {
  overflow: hidden;
  background: var(--color-bg-secondary);
}

.cover-cell img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.folder-card:hover .cover-cell img {
  transform: scale(1.05);
  transition: transform 0.3s ease;
}

.cover-empty {
  color: var(--color-text-tertiary);
}

/* 左上角文件夹角标，区分于文件卡片 */
.folder-badge {
  position: absolute;
  top: 6px;
  left: 6px;
  width: 24px;
  height: 24px;
  border-radius: var(--radius-sm);
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  background: rgba(99, 102, 241, 0.85);
  box-shadow: var(--shadow-sm);
  backdrop-filter: blur(4px);
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
</style>
