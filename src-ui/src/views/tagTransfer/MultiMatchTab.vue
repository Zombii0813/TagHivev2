<template>
  <div class="multi-match-tab">
    <div v-if="entries.length === 0" class="empty-hint">
      没有多匹配项，所有命中都是唯一的。
    </div>
    <div v-else class="multi-list">
      <div v-for="entry in entries" :key="entry.rel_path" class="multi-row">
        <div class="row-head">
          <div class="row-title">{{ entry.rel_path }}</div>
          <div class="row-meta">
            <span>{{ entry.candidate_file_ids.length }} 个候选</span>
            <el-button size="small" link @click="selectAll(entry)">全选</el-button>
            <el-button size="small" link @click="selectNone(entry)">全不选</el-button>
          </div>
        </div>
        <el-checkbox-group
          :model-value="selectionFor(entry.rel_path)"
          @update:model-value="(v: any) => onChange(entry.rel_path, v as number[])"
        >
          <div class="candidate-list">
            <el-checkbox
              v-for="fid in entry.candidate_file_ids"
              :key="fid"
              :label="fid"
              :value="fid"
            >
              <span class="candidate-line">
                <span class="candidate-id">#{{ fid }}</span>
                <span class="candidate-path">{{ candidatePath(fid) }}</span>
              </span>
            </el-checkbox>
          </div>
        </el-checkbox-group>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { apiClient } from '../../api/client'
import type { FileMatchEntryPreview } from '../../api/tags'

interface FileSummary {
  id: number
  path: string
  name: string
}

const props = defineProps<{
  entries: FileMatchEntryPreview[]
  decisions: Record<string, number[]>
}>()

const emit = defineEmits<{
  (e: 'update', rel_path: string, file_ids: number[]): void
}>()

const candidateMap = ref<Record<number, FileSummary>>({})

watch(
  () => props.entries,
  async (entries) => {
    const ids = new Set<number>()
    for (const e of entries) {
      for (const fid of e.candidate_file_ids) ids.add(fid)
    }
    for (const known of Object.keys(candidateMap.value)) ids.delete(Number(known))
    if (ids.size === 0) return
    for (const id of ids) {
      try {
        const f = await apiClient.get<FileSummary>(`/api/files/${id}`)
        candidateMap.value = { ...candidateMap.value, [id]: f }
      } catch {
        // 单条失败时静默忽略，UI 仍可显示 file #id
      }
    }
  },
  { immediate: true, deep: true },
)

function candidatePath(fid: number): string {
  return candidateMap.value[fid]?.path || `file #${fid}`
}

function selectionFor(rel_path: string): number[] {
  return props.decisions[rel_path] ?? []
}

function onChange(rel_path: string, ids: number[]) {
  emit('update', rel_path, ids)
}

function selectAll(entry: FileMatchEntryPreview) {
  emit('update', entry.rel_path, [...entry.candidate_file_ids])
}

function selectNone(entry: FileMatchEntryPreview) {
  emit('update', entry.rel_path, [])
}
</script>

<style scoped>
.multi-match-tab {
  padding: 8px 4px;
}
.empty-hint {
  color: var(--el-text-color-secondary);
  text-align: center;
  padding: 24px 0;
}
.multi-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  max-height: 360px;
  overflow-y: auto;
}
.multi-row {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  padding: 10px 12px;
}
.row-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.row-title {
  font-weight: 500;
}
.row-meta {
  display: flex;
  gap: 8px;
  align-items: center;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.candidate-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding-left: 4px;
}
.candidate-line {
  display: inline-flex;
  gap: 8px;
  align-items: center;
}
.candidate-id {
  color: var(--el-text-color-secondary);
  font-family: var(--el-font-family-monospace, monospace);
  font-size: 12px;
}
.candidate-path {
  font-size: 13px;
}
</style>
