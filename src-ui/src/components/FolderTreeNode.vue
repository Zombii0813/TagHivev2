<template>
  <div class="folder-node-wrapper">
    <div
      class="tree-node"
      :class="{ 
        selected: selectedPath === folder.path,
        expanded: isExpanded
      }"
      :style="{ paddingLeft: `${level * 16 + 8}px` }"
      @click="handleClick"
    >
      <!-- 展开/收起图标 -->
      <span 
        class="expand-icon"
        :class="{ 'is-leaf': folder.children.length === 0 }"
        @click.stop="toggleExpand"
      >
        <el-icon v-if="folder.children.length > 0">
          <ArrowRight v-if="!isExpanded" />
          <ArrowDown v-else />
        </el-icon>
      </span>
      
      <!-- 文件夹图标 -->
      <el-icon class="node-icon folder-icon">
        <FolderOpened v-if="isExpanded" />
        <Folder v-else />
      </el-icon>
      
      <!-- 文件夹名称 -->
      <span class="node-name">{{ folder.name }}</span>
      
      <!-- 文件数量 -->
      <span class="file-count">({{ folder.file_count }})</span>
    </div>
    
    <!-- 子文件夹 -->
    <div v-if="isExpanded && folder.children.length > 0" class="tree-children">
      <FolderTreeNode
        v-for="child in folder.children"
        :key="child.path"
        :folder="child"
        :selected-path="selectedPath"
        :level="level + 1"
        @select="$emit('select', $event)"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { Folder, FolderOpened, ArrowRight, ArrowDown } from '@element-plus/icons-vue'
import type { FolderNode } from '../types'

const props = defineProps<{
  folder: FolderNode
  selectedPath: string
  level: number
}>()

const emit = defineEmits<{
  select: [path: string]
}>()

const isExpanded = ref(false)

// 监听 folder.is_expanded 初始值
watch(() => props.folder.is_expanded, (val) => {
  isExpanded.value = val
}, { immediate: true })

function toggleExpand() {
  if (props.folder.children.length > 0) {
    isExpanded.value = !isExpanded.value
  }
}

function handleClick() {
  emit('select', props.folder.path)
}
</script>

<style scoped>
.folder-node-wrapper {
  width: 100%;
}

.tree-node {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 5px 8px;
  border-radius: 4px;
  cursor: pointer;
  transition: background-color 0.2s;
  font-size: 13px;
  min-height: 28px;
}

.tree-node:hover {
  background-color: var(--color-bg-hover);
}

.tree-node.selected {
  background-color: var(--color-accent-light);
  color: var(--color-accent);
}

.expand-icon {
  width: 16px;
  height: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  cursor: pointer;
  border-radius: 3px;
  transition: background-color 0.2s;
}

.expand-icon:hover:not(.is-leaf) {
  background-color: var(--color-bg-hover);
}

.expand-icon.is-leaf {
  cursor: default;
}

.expand-icon .el-icon {
  font-size: 12px;
  color: var(--color-text-secondary);
}

.node-icon {
  font-size: 16px;
  flex-shrink: 0;
}

.folder-icon {
  color: #e6a23c;
}

.tree-node.selected .folder-icon {
  color: var(--color-accent);
}

.node-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.file-count {
  font-size: 11px;
  color: var(--color-text-secondary);
  flex-shrink: 0;
}

.tree-node.selected .file-count {
  color: var(--color-accent);
}

.tree-children {
  width: 100%;
}
</style>
