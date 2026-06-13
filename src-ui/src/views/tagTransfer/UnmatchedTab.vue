<template>
  <div class="unmatched-tab">
    <div class="toolbar">
      <el-button size="small" type="danger" plain @click="skipAll">
        全部跳过
      </el-button>
      <span class="meta">剩余未匹配: {{ preview.unmatched.length }}</span>
    </div>

    <div v-if="preview.unmatched.length === 0" class="empty-hint">
      所有未匹配项已处理完毕。
    </div>

    <div v-else class="split">
      <div class="left">
        <div class="left-title">未匹配文件（点击后在右侧选择目标）</div>
        <div class="entry-grid">
          <div
            v-for="entry in preview.unmatched"
            :key="entry.rel_path"
            class="entry-cell"
            :class="{ active: activeRelPath === entry.rel_path }"
            :title="entry.rel_path"
            @click="setActive(entry.rel_path)"
          >
            <div class="entry-thumb">
              <el-icon :size="40">
                <Document v-if="iconKind(entry.name) === 'doc'" />
                <VideoCamera v-else-if="iconKind(entry.name) === 'video'" />
                <Headset v-else-if="iconKind(entry.name) === 'audio'" />
                <Picture v-else-if="iconKind(entry.name) === 'image'" />
                <Document v-else />
              </el-icon>
            </div>
            <div class="entry-name">{{ entry.name }}</div>
            <div class="entry-tags">{{ entry.tag_export_ids.length }} 标签</div>
          </div>
        </div>
      </div>

      <div class="right">
        <div class="right-title">在工作区内选择目标文件</div>
        <WorkspaceFilePicker
          v-if="activeEntry"
          :key="activeEntry.rel_path"
          :workspace="workspace"
          :initial-keyword="activeEntry.name"
          @pick="onPickFile"
        />
        <div v-else class="empty-hint">从左侧选择一项以开始重定位</div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import {
  Document,
  Headset,
  Picture,
  VideoCamera,
} from '@element-plus/icons-vue'
import { tagApi, type ImportPreview } from '../../api/tags'
import type { FileSummary } from '../../types'
import WorkspaceFilePicker from '../../components/WorkspaceFilePicker.vue'

const props = defineProps<{
  preview: ImportPreview
  workspace: string
}>()
const emit = defineEmits<{
  (e: 'relocate', updated: ImportPreview): void
}>()

const activeRelPath = ref<string | null>(null)

watch(
  () => props.preview.unmatched,
  (list) => {
    if (!list.find(e => e.rel_path === activeRelPath.value)) {
      activeRelPath.value = list[0]?.rel_path ?? null
    }
  },
  { immediate: true },
)

const activeEntry = computed(
  () => props.preview.unmatched.find(e => e.rel_path === activeRelPath.value) || null,
)

function setActive(rel_path: string) {
  activeRelPath.value = rel_path
}

function iconKind(name: string): 'doc' | 'image' | 'video' | 'audio' | 'other' {
  const dot = name.lastIndexOf('.')
  if (dot < 0) return 'other'
  const ext = name.slice(dot + 1).toLowerCase()
  if (['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'svg', 'tif', 'tiff', 'avif', 'heic'].includes(ext)) return 'image'
  if (['mp4', 'mkv', 'mov', 'avi', 'webm', 'flv', 'wmv', 'm4v'].includes(ext)) return 'video'
  if (['mp3', 'wav', 'flac', 'aac', 'ogg', 'm4a'].includes(ext)) return 'audio'
  if (['pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'txt', 'md', 'rtf'].includes(ext)) return 'doc'
  return 'other'
}

async function skipAll() {
  try {
    const updated = await tagApi.importRelocate({
      token: props.preview.token,
      mode: 'skip_all',
    })
    emit('relocate', updated)
    ElMessage.info('已全部跳过')
  } catch (err: any) {
    ElMessage.error(`操作失败: ${err?.message ?? err}`)
  }
}

async function onPickFile(file: FileSummary) {
  if (!activeEntry.value) return
  try {
    const updated = await tagApi.importRelocate({
      token: props.preview.token,
      mode: 'manual',
      rel_path: activeEntry.value.rel_path,
      file_id: file.id,
    })
    emit('relocate', updated)
    ElMessage.success(`已关联到 ${file.name}`)
  } catch (err: any) {
    ElMessage.error(`关联失败: ${err?.message ?? err}`)
  }
}
</script>

<style scoped>
.unmatched-tab {
  padding: 8px 4px;
}
.toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}
.toolbar .meta {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-left: auto;
}
.empty-hint {
  text-align: center;
  color: var(--el-text-color-secondary);
  padding: 24px 0;
}
.split {
  display: grid;
  grid-template-columns: 320px 1fr;
  gap: 12px;
  min-height: 400px;
  max-height: 480px;
}
.left,
.right {
  display: flex;
  flex-direction: column;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 4px;
  overflow: hidden;
  min-height: 0;
}
.left-title,
.right-title {
  padding: 6px 10px;
  background: var(--el-fill-color-light);
  font-size: 12px;
  font-weight: 500;
  flex-shrink: 0;
}
.entry-grid {
  flex: 1 1 0;
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(88px, 1fr));
  gap: 4px;
  padding: 6px;
  align-content: start;
}
.entry-cell {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 6px 4px;
  border-radius: 4px;
  cursor: pointer;
  user-select: none;
}
.entry-cell:hover {
  background: var(--el-fill-color-light);
}
.entry-cell.active {
  background: var(--el-color-primary-light-9);
  outline: 1px solid var(--el-color-primary);
}
.entry-thumb {
  width: 56px;
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--el-fill-color);
  border-radius: 4px;
  flex-shrink: 0;
}
.entry-name {
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
.entry-tags {
  font-size: 10px;
  color: var(--el-text-color-placeholder);
  margin-top: 2px;
}
.right {
  padding: 10px;
}
</style>
