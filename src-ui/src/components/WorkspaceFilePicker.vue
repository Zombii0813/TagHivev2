<template>
  <div class="file-picker">
    <!-- 顶部工具条：返回 + 面包屑 / 搜索 -->
    <div class="picker-toolbar">
      <el-button
        size="small"
        :disabled="!searchMode && currentPath === workspace"
        @click="goUp"
      >
        <el-icon><ArrowLeft /></el-icon>
      </el-button>
      <div class="breadcrumb">
        <span
          v-for="(seg, i) in breadcrumbSegs"
          :key="seg.path"
          class="crumb"
          :class="{ last: i === breadcrumbSegs.length - 1 }"
          @click="searchMode ? exitSearch(seg.path) : goTo(seg.path)"
        >
          {{ seg.label }}
          <span v-if="i < breadcrumbSegs.length - 1" class="sep">/</span>
        </span>
      </div>
      <el-input
        v-model="keyword"
        :placeholder="placeholder || '搜索整个工作区...'"
        size="small"
        clearable
        :prefix-icon="Search"
        class="picker-search"
        @input="onKeywordChange"
      />
    </div>

    <!-- 主内容区：网格 -->
    <div v-if="loading" class="picker-status">加载中...</div>
    <div
      v-else-if="entries.length === 0"
      class="picker-status"
    >
      {{ searchMode ? '工作区内未找到匹配文件' : '此目录为空' }}
    </div>
    <div v-else class="picker-grid">
      <div
        v-for="entry in entries"
        :key="entry.kind + ':' + entry.path"
        class="grid-cell"
        :class="{ active: isActive(entry) }"
        :title="entry.name"
        @click="onClick(entry)"
        @dblclick="onDblClick(entry)"
      >
        <div class="thumb">
          <template v-if="entry.kind === 'folder'">
            <el-icon :size="44" color="#e0a93b"><Folder /></el-icon>
          </template>
          <template v-else>
            <img
              v-if="entry.fileType === 'image' || entry.fileType === 'video'"
              :src="thumbUrl(entry)"
              :alt="entry.name"
              loading="lazy"
              @error="onImgError"
            />
            <el-icon v-else :size="40">
              <Document v-if="entry.fileType === 'doc'" />
              <VideoCamera v-else-if="entry.fileType === 'video'" />
              <Headset v-else-if="entry.fileType === 'audio'" />
              <Picture v-else-if="entry.fileType === 'image'" />
              <Document v-else />
            </el-icon>
          </template>
        </div>
        <div class="cell-name">{{ entry.name }}</div>
        <div v-if="searchMode && entry.kind === 'file'" class="cell-rel">
          {{ relativePath(entry.path) }}
        </div>
      </div>
    </div>

    <!-- 底部确认 -->
    <div class="picker-footer">
      <el-button
        type="primary"
        size="small"
        :disabled="!selectedFile"
        @click="confirmSelected"
      >
        关联此文件
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import {
  ArrowLeft,
  Document,
  Folder,
  Headset,
  Picture,
  Search,
  VideoCamera,
} from '@element-plus/icons-vue'
import { fileApi } from '../api/files'
import { folderApi } from '../api/folders'
import { thumbnailApi } from '../api/thumbnails'
import type { FileSummary, FolderNode } from '../types'

const props = defineProps<{
  workspace: string
  initialKeyword?: string
  placeholder?: string
}>()
const emit = defineEmits<{
  (e: 'pick', file: FileSummary): void
}>()

interface FolderEntry {
  kind: 'folder'
  name: string
  path: string
}
interface FileEntry {
  kind: 'file'
  id: number
  name: string
  path: string
  fileType: string
}
type Entry = FolderEntry | FileEntry

const keyword = ref(props.initialKeyword || '')
const loading = ref(false)
const folders = ref<FolderEntry[]>([])
const files = ref<FileEntry[]>([])
const searchHits = ref<FileEntry[]>([])
const folderTree = ref<FolderNode[]>([])
const currentPath = ref<string>(props.workspace)
const selectedKey = ref<string | null>(null)

let searchSeq = 0
let debounceTimer: number | null = null

const searchMode = computed(() => keyword.value.trim().length > 0)

const entries = computed<Entry[]>(() => {
  if (searchMode.value) return searchHits.value
  return [...folders.value, ...files.value]
})

const selectedFile = computed<FileEntry | null>(() => {
  if (!selectedKey.value) return null
  for (const e of entries.value) {
    if (e.kind === 'file' && fileKey(e) === selectedKey.value) return e
  }
  return null
})

const breadcrumbSegs = computed(() => {
  const root = normalizePath(props.workspace)
  const segs: { label: string; path: string }[] = []
  const rootName = root.split('/').filter(Boolean).pop() || root
  segs.push({ label: rootName, path: root })
  if (searchMode.value) {
    segs.push({ label: '搜索结果', path: '__search__' })
    return segs
  }
  const cur = normalizePath(currentPath.value)
  if (cur !== root && cur.startsWith(root + '/')) {
    const rel = cur.slice(root.length + 1)
    const parts = rel.split('/').filter(Boolean)
    let acc = root
    for (const p of parts) {
      acc = `${acc}/${p}`
      segs.push({ label: p, path: acc })
    }
  }
  return segs
})

onMounted(async () => {
  await loadTree()
  if (props.initialKeyword && props.initialKeyword.trim()) {
    runSearch(props.initialKeyword.trim())
  } else {
    await loadCurrentDir()
  }
})

watch(
  () => props.initialKeyword,
  (v) => {
    keyword.value = v || ''
    if (v && v.trim()) runSearch(v.trim())
    else loadCurrentDir()
  },
)

watch(
  () => props.workspace,
  async () => {
    currentPath.value = props.workspace
    await loadTree()
    await loadCurrentDir()
  },
)

function normalizePath(p: string): string {
  return p.replace(/\\/g, '/').replace(/\/+$/, '')
}

function fileKey(e: FileEntry): string {
  return 'f:' + e.id
}
function folderKey(e: FolderEntry): string {
  return 'd:' + e.path
}

function isActive(e: Entry): boolean {
  if (!selectedKey.value) return false
  return selectedKey.value === (e.kind === 'file' ? fileKey(e) : folderKey(e))
}

async function loadTree() {
  try {
    const tree = await folderApi.getTree(props.workspace)
    folderTree.value = tree.folders
  } catch {
    folderTree.value = []
  }
}

function findNodeChildren(target: string): FolderNode[] {
  const norm = normalizePath(target)
  const root = normalizePath(props.workspace)
  if (norm === root) return folderTree.value
  const stack: FolderNode[] = [...folderTree.value]
  while (stack.length) {
    const n = stack.shift()!
    if (normalizePath(n.path) === norm) return n.children
    stack.push(...n.children)
  }
  return []
}

async function loadCurrentDir() {
  selectedKey.value = null
  loading.value = true
  try {
    const subFolders = findNodeChildren(currentPath.value)
    folders.value = subFolders.map(n => ({
      kind: 'folder' as const,
      name: n.name,
      path: n.path,
    }))
    const result = await folderApi.getContents(currentPath.value, 0, 500, 'name', false)
    files.value = result.files.map(f => ({
      kind: 'file' as const,
      id: f.id,
      name: f.name,
      path: f.path,
      fileType: f.type,
    }))
  } catch {
    folders.value = []
    files.value = []
  } finally {
    loading.value = false
  }
}

function onKeywordChange(v: string) {
  if (debounceTimer) window.clearTimeout(debounceTimer)
  if (!v || !v.trim()) {
    searchHits.value = []
    loadCurrentDir()
    return
  }
  debounceTimer = window.setTimeout(() => runSearch(v.trim()), 200)
}

async function runSearch(text: string) {
  selectedKey.value = null
  const seq = ++searchSeq
  loading.value = true
  try {
    const result = await fileApi.search({
      text,
      root: props.workspace,
      limit: 200,
      offset: 0,
      use_fts: false,
    })
    if (seq !== searchSeq) return
    searchHits.value = result.files.map(f => ({
      kind: 'file' as const,
      id: f.id,
      name: f.name,
      path: f.path,
      fileType: f.type,
    }))
  } catch {
    if (seq === searchSeq) searchHits.value = []
  } finally {
    if (seq === searchSeq) loading.value = false
  }
}

function goUp() {
  if (searchMode.value) {
    keyword.value = ''
    searchHits.value = []
    loadCurrentDir()
    return
  }
  const root = normalizePath(props.workspace)
  const cur = normalizePath(currentPath.value)
  if (cur === root) return
  const parent = cur.slice(0, cur.lastIndexOf('/')) || root
  goTo(parent)
}

function goTo(path: string) {
  currentPath.value = normalizePath(path)
  loadCurrentDir()
}

function exitSearch(path: string) {
  keyword.value = ''
  searchHits.value = []
  if (path && path !== '__search__') goTo(path)
  else loadCurrentDir()
}

function onClick(e: Entry) {
  selectedKey.value = e.kind === 'file' ? fileKey(e) : folderKey(e)
}

function onDblClick(e: Entry) {
  if (e.kind === 'folder') {
    goTo(e.path)
  } else {
    confirmPick(e)
  }
}

function thumbUrl(e: FileEntry): string {
  return thumbnailApi.getThumbnailUrl(e.id, 'medium')
}

function onImgError(ev: Event) {
  const img = ev.target as HTMLImageElement
  img.style.display = 'none'
}

function relativePath(p: string): string {
  if (!p) return ''
  const root = normalizePath(props.workspace)
  const norm = normalizePath(p)
  if (root && norm.startsWith(root + '/')) return norm.slice(root.length + 1)
  return norm
}

function confirmPick(e: FileEntry) {
  emit('pick', {
    id: e.id,
    name: e.name,
    path: e.path,
    type: e.fileType,
    size: 0,
    tag_ids: [],
  })
}

function confirmSelected() {
  if (selectedFile.value) confirmPick(selectedFile.value)
}
</script>

<style scoped>
.file-picker {
  display: flex;
  flex-direction: column;
  gap: 8px;
  height: 100%;
  min-height: 0;
}
.picker-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}
.picker-search {
  flex: 0 0 220px;
  margin-left: auto;
}
.breadcrumb {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--el-text-color-regular);
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.crumb {
  cursor: pointer;
  padding: 2px 4px;
  border-radius: 3px;
}
.crumb:hover {
  background: var(--el-fill-color-light);
}
.crumb.last {
  color: var(--el-text-color-primary);
  font-weight: 500;
  cursor: default;
}
.crumb.last:hover {
  background: transparent;
}
.crumb .sep {
  color: var(--el-text-color-placeholder);
  margin-left: 4px;
}
.picker-status {
  text-align: center;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  padding: 24px 0;
  flex: 1;
}
.picker-grid {
  flex: 1 1 0;
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(96px, 1fr));
  gap: 6px;
  padding: 6px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 4px;
  align-content: start;
}
.grid-cell {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 6px 4px;
  border-radius: 4px;
  cursor: pointer;
  user-select: none;
}
.grid-cell:hover {
  background: var(--el-fill-color-light);
}
.grid-cell.active {
  background: var(--el-color-primary-light-9);
  outline: 1px solid var(--el-color-primary);
}
.thumb {
  width: 64px;
  height: 64px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--el-fill-color-light);
  border-radius: 4px;
  overflow: hidden;
  flex-shrink: 0;
}
.thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.cell-name {
  margin-top: 4px;
  font-size: 11px;
  text-align: center;
  width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  word-break: break-all;
  line-height: 1.2;
}
.cell-rel {
  font-size: 10px;
  color: var(--el-text-color-placeholder);
  text-align: center;
  width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.picker-footer {
  display: flex;
  justify-content: flex-end;
}
</style>
