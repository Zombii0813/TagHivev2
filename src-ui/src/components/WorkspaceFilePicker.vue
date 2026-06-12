<template>
  <div class="file-picker">
    <el-input
      v-model="keyword"
      :placeholder="placeholder || '搜索文件名...'"
      size="small"
      clearable
      :prefix-icon="Search"
      @input="onKeywordChange"
    />
    <div v-if="loading" class="picker-status">搜索中...</div>
    <div v-else-if="hits.length === 0 && !!keyword" class="picker-status">
      工作区内未找到匹配文件
    </div>
    <div v-else class="picker-list">
      <div
        v-for="f in hits"
        :key="f.id"
        class="picker-item"
        :class="{ active: selected === f.id }"
        @click="select(f)"
        @dblclick="confirmPick(f)"
      >
        <div class="item-name">{{ f.name }}</div>
        <div class="item-path">{{ relativePath(f.path) }}</div>
      </div>
    </div>
    <div class="picker-footer">
      <el-button
        type="primary"
        size="small"
        :disabled="selected == null"
        @click="confirmSelected"
      >
        关联此文件
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { Search } from '@element-plus/icons-vue'
import { fileApi } from '../api/files'
import type { FileSummary } from '../types'

const props = defineProps<{
  workspace: string
  initialKeyword?: string
  placeholder?: string
}>()
const emit = defineEmits<{
  (e: 'pick', file: FileSummary): void
}>()

const keyword = ref(props.initialKeyword || '')
const hits = ref<FileSummary[]>([])
const loading = ref(false)
const selected = ref<number | null>(null)

let searchSeq = 0
let debounceTimer: number | null = null

watch(
  () => props.initialKeyword,
  (v) => {
    keyword.value = v || ''
    runSearch(keyword.value)
  },
)

function onKeywordChange(v: string) {
  if (debounceTimer) window.clearTimeout(debounceTimer)
  debounceTimer = window.setTimeout(() => runSearch(v), 200)
}

async function runSearch(text: string) {
  selected.value = null
  if (!text || !text.trim()) {
    hits.value = []
    loading.value = false
    return
  }
  const seq = ++searchSeq
  loading.value = true
  try {
    const result = await fileApi.search({
      text: text.trim(),
      root: props.workspace,
      limit: 50,
      offset: 0,
      use_fts: true,
    })
    if (seq !== searchSeq) return
    hits.value = result.files
  } catch {
    if (seq === searchSeq) hits.value = []
  } finally {
    if (seq === searchSeq) loading.value = false
  }
}

function relativePath(p: string): string {
  if (!p) return ''
  const root = props.workspace.replace(/\\/g, '/').replace(/\/$/, '')
  const norm = p.replace(/\\/g, '/')
  if (root && norm.startsWith(root + '/')) return norm.slice(root.length + 1)
  return norm
}

function select(f: FileSummary) {
  selected.value = f.id
}

function confirmPick(f: FileSummary) {
  emit('pick', f)
}

function confirmSelected() {
  const f = hits.value.find(h => h.id === selected.value)
  if (f) emit('pick', f)
}
</script>

<style scoped>
.file-picker {
  display: flex;
  flex-direction: column;
  gap: 8px;
  height: 100%;
  min-height: 320px;
}
.picker-status {
  text-align: center;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  padding: 12px 0;
}
.picker-list {
  flex: 1;
  overflow-y: auto;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 4px;
}
.picker-item {
  padding: 8px 10px;
  cursor: pointer;
  border-bottom: 1px solid var(--el-border-color-extra-light);
}
.picker-item:hover {
  background: var(--el-fill-color-light);
}
.picker-item.active {
  background: var(--el-color-primary-light-9);
  border-left: 3px solid var(--el-color-primary);
}
.item-name {
  font-size: 13px;
  font-weight: 500;
}
.item-path {
  font-size: 11px;
  color: var(--el-text-color-secondary);
  margin-top: 2px;
  word-break: break-all;
}
.picker-footer {
  display: flex;
  justify-content: flex-end;
}
</style>
