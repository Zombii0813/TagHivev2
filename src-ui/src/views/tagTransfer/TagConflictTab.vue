<template>
  <div class="tag-conflict-tab">
    <div v-if="!hasConflict" class="empty-hint">
      没有同名冲突的标签，将全部新建。
    </div>
    <div v-else class="conflict-list">
      <div v-for="t in conflictTags" :key="t.export_id" class="conflict-row">
        <div class="row-name">
          <span v-if="t.icon" class="row-icon">{{ t.icon }}</span>
          <span v-else class="row-dot" :style="{ backgroundColor: t.color || '#999' }"></span>
          <span>{{ t.name }}</span>
          <el-tag size="small" type="warning" effect="plain">已存在</el-tag>
        </div>
        <div class="row-actions">
          <el-radio-group
            :model-value="strategyFor(t.export_id)"
            @change="(v: string) => onStrategyChange(t.export_id, v as Strategy)"
            size="small"
          >
            <el-radio-button value="skip">跳过（复用）</el-radio-button>
            <el-radio-button value="rename">重命名新建</el-radio-button>
          </el-radio-group>
          <el-input
            v-if="strategyFor(t.export_id) === 'rename'"
            :model-value="renameFor(t.export_id, t.name)"
            size="small"
            style="width: 200px"
            @update:model-value="(v: string) => onRenameChange(t.export_id, v)"
          />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { ExportedTagPreview, ImportTagDecision } from '../../api/tags'

type Strategy = 'skip' | 'merge' | 'rename'

const props = defineProps<{
  tags: ExportedTagPreview[]
  decisions: Record<string, ImportTagDecision>
}>()

const emit = defineEmits<{
  (e: 'update', decision: ImportTagDecision): void
}>()

const conflictTags = computed(() => props.tags.filter(t => t.conflict))
const hasConflict = computed(() => conflictTags.value.length > 0)

function strategyFor(id: string): Strategy {
  return (props.decisions[id]?.strategy as Strategy) || 'skip'
}

function renameFor(id: string, fallback: string): string {
  return props.decisions[id]?.new_name || `${fallback} (导入)`
}

function onStrategyChange(id: string, strategy: Strategy) {
  emit('update', { export_id: id, strategy })
}

function onRenameChange(id: string, name: string) {
  emit('update', { export_id: id, strategy: 'rename', new_name: name })
}
</script>

<style scoped>
.tag-conflict-tab {
  padding: 8px 4px;
}
.empty-hint {
  color: var(--el-text-color-secondary);
  text-align: center;
  padding: 24px 0;
}
.conflict-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  max-height: 360px;
  overflow-y: auto;
}
.conflict-row {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px 12px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
}
.row-name {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 500;
}
.row-icon {
  font-size: 16px;
}
.row-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  display: inline-block;
}
.row-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}
</style>
