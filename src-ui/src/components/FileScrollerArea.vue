<template>
  <!-- Grid 模式 -->
  <RecycleScroller
    v-if="viewMode === 'grid'"
    class="scroller grid-view"
    :items="gridRows"
    :item-size="gridItemHeight"
    key-field="rowIndex"
    v-slot="{ item: row }"
  >
    <div class="grid-row" :style="gridRowStyle">
      <div
        v-for="file in row.files"
        :key="file.id"
        class="grid-cell"
        :class="{ 'file-drop-active': activeDropFileId === file.id }"
        :style="cellDropStyle(file.id)"
        :data-file-id="file.id"
        draggable="true"
        @dragstart="$emit('file-dragstart', file, $event)"
        @dragend="$emit('file-dragend')"
        @dragover.prevent.stop="$emit('file-drag-over', file.id, $event)"
        @dragleave="$emit('file-drag-leave', file.id)"
        @drop.prevent.stop="$emit('file-drop', file, $event)"
      >
        <FileCard
          :file="file"
          :selected="selectedIds.has(file.id)"
          :multi-select="multiSelectMode"
          :size="gridItemWidth"
          @click="$emit('file-click', file.id, $event)"
          @checkbox-click="(id: number) => $emit('checkbox-click', id)"
          @dblclick="$emit('file-dblclick', file)"
          @contextmenu.prevent="$emit('file-contextmenu', file, $event)"
        />
        <div
          v-if="activeDropFileId === file.id && dragTagMeta"
          class="tag-drop-badge"
        >
          <span class="tag-drop-badge-plus">+</span>
          <span v-if="dragTagMeta.icon" class="tag-drop-badge-icon">{{ dragTagMeta.icon }}</span>
          <span v-else class="tag-drop-badge-dot"></span>
          <span class="tag-drop-badge-name">{{ dragTagMeta.name }}</span>
        </div>
      </div>
    </div>
  </RecycleScroller>

  <!-- List 模式 -->
  <RecycleScroller
    v-else
    class="scroller list-view"
    :items="files"
    :item-size="60"
    key-field="id"
    v-slot="{ item }"
  >
    <div
      class="list-drop-target"
      :class="{ 'file-drop-active': activeDropFileId === item.id }"
      :style="cellDropStyle(item.id)"
      draggable="true"
      @dragstart="$emit('file-dragstart', item, $event)"
      @dragend="$emit('file-dragend')"
      @dragover.prevent.stop="$emit('file-drag-over', item.id, $event)"
      @dragleave="$emit('file-drag-leave', item.id)"
      @drop.prevent.stop="$emit('file-drop', item, $event)"
    >
      <FileListItem
        :file="item"
        :selected="selectedIds.has(item.id)"
        @click="$emit('file-click', item.id, $event)"
        @dblclick="$emit('file-dblclick', item)"
        @contextmenu.prevent="$emit('file-contextmenu', item, $event)"
      />
      <div
        v-if="activeDropFileId === item.id && dragTagMeta"
        :class="['tag-drop-badge', listBadgeModifier ? 'tag-drop-badge--list' : '']"
      >
        <span class="tag-drop-badge-plus">+</span>
        <span v-if="dragTagMeta.icon" class="tag-drop-badge-icon">{{ dragTagMeta.icon }}</span>
        <span v-else class="tag-drop-badge-dot"></span>
        <span class="tag-drop-badge-name">{{ dragTagMeta.name }}</span>
      </div>
    </div>
  </RecycleScroller>
</template>

<script setup lang="ts">
import { RecycleScroller } from 'vue-virtual-scroller'
import FileCard from './FileCard.vue'
import FileListItem from './FileListItem.vue'
import type { FileSummary } from '../types'
import type { TagDragMeta } from '../utils/drag'
import type { CSSProperties } from 'vue'

interface GridRow {
  rowIndex: number
  files: FileSummary[]
}

const props = defineProps<{
  viewMode: 'grid' | 'list'
  files: FileSummary[]
  gridRows: GridRow[]
  gridItemHeight: number
  gridItemWidth: number
  gridRowStyle: CSSProperties
  gridCellStyle: CSSProperties
  selectedIds: Set<number>
  multiSelectMode: boolean
  activeDropFileId: number | null
  dragTagMeta: TagDragMeta | null
  /** list 模式下 badge 是否使用 --list 修饰类（all 模式为 true） */
  listBadgeModifier?: boolean
}>()

defineEmits<{
  (e: 'file-click', fileId: number, evt: MouseEvent): void
  (e: 'file-dblclick', file: FileSummary): void
  (e: 'file-contextmenu', file: FileSummary, evt: MouseEvent): void
  (e: 'file-drag-over', fileId: number, evt: DragEvent): void
  (e: 'file-drag-leave', fileId: number): void
  (e: 'file-drop', file: FileSummary, evt: DragEvent): void
  (e: 'file-dragstart', file: FileSummary, evt: DragEvent): void
  (e: 'file-dragend'): void
  (e: 'checkbox-click', fileId: number): void
}>()

// 把拖拽中的标签颜色作为 CSS 变量注入到当前作为 drop 目标的单元格上，
// 让 drop 高亮（外发光、轮廓、徽章背景）都用该标签颜色，便于一眼识别正在添加的是哪个标签。
function cellDropStyle(fileId: number): CSSProperties {
  const isActive = props.activeDropFileId === fileId
  const tagColor = props.dragTagMeta?.color || '#409EFF'
  if (props.viewMode === 'grid') {
    return isActive
      ? { ...props.gridCellStyle, '--tag-color': tagColor } as CSSProperties
      : props.gridCellStyle
  }
  return isActive ? ({ '--tag-color': tagColor } as CSSProperties) : {}
}
</script>
