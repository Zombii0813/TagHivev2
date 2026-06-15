<template>
  <el-dialog
    v-if="dialogShown"
    v-model="dialogShown"
    :title="dialogTitle"
    width="900px"
    :close-on-click-modal="false"
    append-to-body
    @closed="handleClosed"
  >
    <!-- Step: preview 预览 + 三 Tab + 提交 -->
    <div v-if="step === 'preview' && preview" class="transfer-preview">
      <div class="preview-meta">
        <span>来源工作区: {{ preview.source_workspace || '(未知)' }}</span>
        <span>导出时间: {{ preview.exported_at || '—' }}</span>
      </div>
      <el-tabs v-model="activeTab" class="preview-tabs">
        <el-tab-pane :label="`标签冲突 (${conflictCount})`" name="tags">
          <TagConflictTab
            :tags="preview.tags"
            :decisions="tagDecisions"
            @update="onTagDecisionUpdate"
          />
        </el-tab-pane>
        <el-tab-pane :label="`多匹配 (${preview.multiple.length})`" name="multi">
          <MultiMatchTab
            :entries="preview.multiple"
            :decisions="fileDecisions"
            @update="onFileDecisionUpdate"
          />
        </el-tab-pane>
        <el-tab-pane :label="`未匹配 (${preview.unmatched.length})`" name="unmatched">
          <UnmatchedTab
            :preview="preview"
            :workspace="workspace"
            @relocate="onRelocate"
          />
        </el-tab-pane>
      </el-tabs>
      <div class="preview-summary">
        预计：创建 {{ summaryHint.tagsCreate }} 个标签 ·
        复用 {{ summaryHint.tagsReuse }} 个标签 ·
        关联 {{ summaryHint.filesLink }} 个文件 ·
        跳过 {{ summaryHint.filesSkip }} 个文件
      </div>
    </div>

    <!-- Step: done 显示结果 -->
    <div v-else-if="step === 'done' && summary" class="transfer-done">
      <el-result icon="success" title="导入完成">
        <template #sub-title>
          <div>新建标签 {{ summary.tags_created }} 个，复用 {{ summary.tags_reused }} 个</div>
          <div>关联文件 {{ summary.files_linked }} 个，跳过 {{ summary.files_skipped }} 个</div>
        </template>
      </el-result>
    </div>

    <template #footer>
      <el-button v-if="step === 'preview'" @click="closeDialog">取消</el-button>
      <el-button
        v-if="step === 'preview'"
        type="primary"
        :loading="committing"
        @click="commitImport"
      >
        确认导入
      </el-button>
      <el-button v-if="step === 'done'" @click="closeDialog">关闭</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { invoke } from '@tauri-apps/api/core'
import {
  tagApi,
  type ImportPreview,
  type ImportSummary,
  type ImportTagDecision,
  type ImportFileDecision,
} from '../api/tags'
import TagConflictTab from './tagTransfer/TagConflictTab.vue'
import MultiMatchTab from './tagTransfer/MultiMatchTab.vue'
import UnmatchedTab from './tagTransfer/UnmatchedTab.vue'

const props = defineProps<{
  modelValue: boolean
  workspace: string
  initialAction?: 'export' | 'import' | null
}>()
const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'imported'): void
}>()

type Step = 'preview' | 'done'
const step = ref<Step>('preview')
const committing = ref(false)
const preview = ref<ImportPreview | null>(null)
const summary = ref<ImportSummary | null>(null)
const activeTab = ref<'tags' | 'multi' | 'unmatched'>('tags')
const dialogShown = ref(false)  // 真正控制 el-dialog 是否渲染

const tagDecisions = ref<Record<string, ImportTagDecision>>({})
const fileDecisions = ref<Record<string, number[]>>({})

const dialogTitle = computed(() =>
  step.value === 'done' ? '导入结果' : '导入预览',
)

const conflictCount = computed(() =>
  preview.value ? preview.value.tags.filter(t => t.conflict).length : 0,
)

const summaryHint = computed(() => {
  if (!preview.value) return { tagsCreate: 0, tagsReuse: 0, filesLink: 0, filesSkip: 0 }
  let tagsReuse = 0
  let tagsCreate = 0
  for (const t of preview.value.tags) {
    const decision = tagDecisions.value[t.export_id]?.strategy
    if (t.conflict && (decision === 'skip' || decision === 'merge' || !decision)) {
      tagsReuse++
    } else {
      tagsCreate++
    }
  }
  let filesLink = 0
  let filesSkip = 0
  for (const e of preview.value.unique) {
    const decided = fileDecisions.value[e.rel_path]
    const ids = decided !== undefined ? decided : e.candidate_file_ids
    if (ids.length === 0) filesSkip++
    else filesLink += ids.length
  }
  for (const e of preview.value.multiple) {
    const ids = fileDecisions.value[e.rel_path] ?? []
    if (ids.length === 0) filesSkip++
    else filesLink += ids.length
  }
  filesSkip += preview.value.unmatched.length
  return { tagsCreate, tagsReuse, filesLink, filesSkip }
})

// 监听父组件触发的 initialAction，按动作分流；中间步骤不再有 idle 弹窗
watch(
  () => props.modelValue,
  (v) => {
    if (!v) {
      dialogShown.value = false
      return
    }
    resetState()
    if (props.initialAction === 'export') {
      runExport()
    } else if (props.initialAction === 'import') {
      runImport()
    } else {
      // 没有 initialAction 时不做任何事，立即收回 modelValue
      emit('update:modelValue', false)
    }
  },
)

function resetState() {
  preview.value = null
  summary.value = null
  tagDecisions.value = {}
  fileDecisions.value = {}
  step.value = 'preview'
}

async function runExport() {
  if (!props.workspace) {
    ElMessage.warning('请先选择工作区')
    emit('update:modelValue', false)
    return
  }
  let includeThumbnails = false
  try {
    await ElMessageBox.confirm(
      '是否在标签包内携带文件缩略图？携带后未匹配文件可显示原图预览，但包体会变大（仅图片/视频且本地已生成缩略图的文件生效）。',
      '导出选项',
      {
        confirmButtonText: '携带缩略图',
        cancelButtonText: '不携带',
        distinguishCancelAndClose: true,
        type: 'info',
      },
    )
    includeThumbnails = true
  } catch (action) {
    if (action === 'close') {
      emit('update:modelValue', false)
      return
    }
    includeThumbnails = false
  }
  try {
    const wsName = props.workspace.replace(/\\/g, '/').split('/').filter(Boolean).pop() || 'workspace'
    const ts = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19)
    const defaultName = `taghive-export-${wsName}-${ts}.thpack`
    const target = await invoke<string | null>('save_file_dialog', {
      defaultName,
      extension: 'thpack',
    })
    if (!target) {
      emit('update:modelValue', false)
      return
    }
    const data = await tagApi.exportPack(props.workspace, undefined, includeThumbnails)
    await invoke('write_binary_file', { path: target, content: Array.from(data) })
    ElMessage.success(`已导出到 ${target}`)
  } catch (err: any) {
    ElMessage.error(`导出失败: ${err?.message ?? err}`)
  } finally {
    emit('update:modelValue', false)
  }
}

async function runImport() {
  if (!props.workspace) {
    ElMessage.warning('请先选择工作区')
    emit('update:modelValue', false)
    return
  }
  try {
    const path = await invoke<string | null>('open_file_dialog', { extension: 'thpack' })
    if (!path) {
      emit('update:modelValue', false)
      return
    }
    const bytes = await invoke<number[]>('read_binary_file', { path })
    const u8 = new Uint8Array(bytes)
    const result = await tagApi.importPreview(props.workspace, u8)
    preview.value = result
    step.value = 'preview'
    activeTab.value = 'tags'
    dialogShown.value = true  // 仅当成功拿到预览后才打开弹窗
  } catch (err: any) {
    ElMessage.error(`导入预览失败: ${err?.message ?? err}`)
    emit('update:modelValue', false)
  }
}

function onTagDecisionUpdate(decision: ImportTagDecision) {
  tagDecisions.value = { ...tagDecisions.value, [decision.export_id]: decision }
}

function onFileDecisionUpdate(rel_path: string, file_ids: number[]) {
  fileDecisions.value = { ...fileDecisions.value, [rel_path]: file_ids }
}

function onRelocate(updated: ImportPreview) {
  preview.value = updated
}

function closeDialog() {
  dialogShown.value = false
  emit('update:modelValue', false)
}

async function commitImport() {
  if (!preview.value) return
  committing.value = true
  try {
    const tagDecs: ImportTagDecision[] = preview.value.tags
      .filter(t => t.conflict)
      .map(t => tagDecisions.value[t.export_id] ?? { export_id: t.export_id, strategy: 'skip' })
    const fileDecs: ImportFileDecision[] = []
    for (const [rel_path, file_ids] of Object.entries(fileDecisions.value)) {
      fileDecs.push({ rel_path, file_ids })
    }
    const result = await tagApi.importCommit({
      token: preview.value.token,
      tag_decisions: tagDecs,
      file_decisions: fileDecs,
    })
    summary.value = result
    step.value = 'done'
    emit('imported')
  } catch (err: any) {
    ElMessage.error(`导入失败: ${err?.message ?? err}`)
  } finally {
    committing.value = false
  }
}

function handleClosed() {
  // dialog 关闭后清理状态，但不重置 modelValue（已由 closeDialog 处理）
  if (!dialogShown.value && props.modelValue) {
    emit('update:modelValue', false)
  }
}
</script>

<style scoped>
.preview-meta {
  display: flex;
  gap: 24px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 12px;
}
.preview-tabs {
  min-height: 360px;
}
.preview-summary {
  margin-top: 12px;
  padding: 8px 12px;
  background: var(--el-fill-color-light);
  border-radius: 4px;
  font-size: 13px;
}
.transfer-done {
  padding: 24px 0;
}
</style>
