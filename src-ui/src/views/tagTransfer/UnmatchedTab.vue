<template>
  <div class="unmatched-tab">
    <div class="toolbar">
      <el-button size="small" :icon="Refresh" @click="autoRelocate">
        按相对路径重新尝试
      </el-button>
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
        <div class="left-title">未匹配文件</div>
        <div class="entry-list">
          <div
            v-for="entry in preview.unmatched"
            :key="entry.rel_path"
            class="entry-row"
            :class="{ active: activeRelPath === entry.rel_path }"
            @click="setActive(entry.rel_path)"
          >
            <div class="entry-name">{{ entry.name }}</div>
            <div class="entry-rel">{{ entry.rel_path }}</div>
            <div class="entry-tags">关联标签: {{ entry.tag_export_ids.length }}</div>
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
import { Refresh } from '@element-plus/icons-vue'
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

async function autoRelocate() {
  try {
    const updated = await tagApi.importRelocate({
      token: props.preview.token,
      mode: 'auto_rel_path',
    })
    emit('relocate', updated)
    const recovered = props.preview.unmatched.length - updated.unmatched.length
    ElMessage.success(`按相对路径命中 ${recovered} 项`)
  } catch (err: any) {
    ElMessage.error(`重定位失败: ${err?.message ?? err}`)
  }
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
  min-height: 360px;
  max-height: 420px;
}
.left,
.right {
  display: flex;
  flex-direction: column;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 4px;
  overflow: hidden;
}
.left-title,
.right-title {
  padding: 6px 10px;
  background: var(--el-fill-color-light);
  font-size: 12px;
  font-weight: 500;
}
.entry-list {
  flex: 1;
  overflow-y: auto;
}
.entry-row {
  padding: 8px 10px;
  border-bottom: 1px solid var(--el-border-color-extra-light);
  cursor: pointer;
}
.entry-row:hover {
  background: var(--el-fill-color-light);
}
.entry-row.active {
  background: var(--el-color-primary-light-9);
  border-left: 3px solid var(--el-color-primary);
}
.entry-name {
  font-size: 13px;
  font-weight: 500;
}
.entry-rel {
  font-size: 11px;
  color: var(--el-text-color-secondary);
  margin-top: 2px;
  word-break: break-all;
}
.entry-tags {
  font-size: 11px;
  color: var(--el-text-color-placeholder);
  margin-top: 2px;
}
.right {
  padding: 10px;
}
</style>
