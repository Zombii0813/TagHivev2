<template>
  <div class="browser-context-bar" :class="{ 'has-selection': fileStore.hasSelection }" :role="fileStore.hasSelection ? 'toolbar' : 'region'" :aria-label="fileStore.hasSelection ? '所选文件操作' : '当前范围与筛选'">
    <div v-if="fileStore.hasSelection" class="selection-toolbar">
      <div class="context-description" :title="selectionSummary">
        <span class="selection-count">已选 {{ fileStore.selectedCount }} 项</span>
        <span class="selection-total">/ 共 {{ fileStore.totalCount }} 项</span>
        <span v-if="fileStore.hiddenSelectedCount" class="hidden-selection">含 {{ fileStore.hiddenSelectedCount }} 项未显示</span>
      </div>
    </div>
    <div v-else class="filter-summary">
      <span class="scope-text" :title="`范围：${scopeLabel}`">范围：{{ scopeLabel }}</span>
      <span v-for="filter in filters" :key="filter.label" class="filter-chip" :title="`${filter.label}：${filter.value}`">
        {{ filter.label }}：{{ filter.value }}
      </span>
    </div>

    <el-popover v-if="filters.length" placement="bottom-end" trigger="click" :width="320">
      <template #reference>
        <el-button class="filter-entry" size="small" :icon="Filter" :aria-label="`查看筛选条件，共 ${filterCount} 项`">
          筛选 · {{ filterCount }}
        </el-button>
      </template>
      <div class="filter-details">
        <strong>当前筛选</strong>
        <div class="filter-detail"><span>范围</span><span>{{ scopeLabel }}</span></div>
        <div v-for="filter in filters" :key="filter.label" class="filter-detail">
          <span>{{ filter.label }}</span><span>{{ filter.value }}</span>
        </div>
        <el-button size="small" @click="emit('clear-filters')">清除筛选</el-button>
      </div>
    </el-popover>

    <div v-if="fileStore.hasSelection" class="context-actions">
      <el-button class="manage-tags-action" size="small" :icon="CollectionTag" @click="emit('manage-tags')">批量管理标签</el-button>
      <el-button class="delete-action" size="small" type="danger" :icon="Delete" @click="emit('delete-selected')">批量删除</el-button>
      <el-dropdown trigger="click" placement="bottom-end">
        <el-button size="small" :icon="MoreFilled" circle aria-label="更多所选文件操作" title="更多操作" />
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item v-if="fileStore.hiddenSelectedCount" disabled>含 {{ fileStore.hiddenSelectedCount }} 项当前未显示</el-dropdown-item>
            <el-dropdown-item @click="emit('manage-tags')"><el-icon><CollectionTag /></el-icon>批量管理标签</el-dropdown-item>
            <el-dropdown-item @click="fileStore.selectAll()">全选已加载（{{ fileStore.files.length }}）</el-dropdown-item>
            <el-dropdown-item divided @click="emit('delete-selected')"><el-icon><Delete /></el-icon>批量删除</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
      <el-button size="small" :icon="Close" circle aria-label="取消选择" title="取消选择" @click="fileStore.clearSelection()" />
    </div>
    <el-button v-else-if="filters.length" class="clear-filters-action" size="small" @click="emit('clear-filters')">清除筛选</el-button>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Close, CollectionTag, Delete, Filter, MoreFilled } from '@element-plus/icons-vue'
import { useFileStore } from '../stores/files'
import { useTagStore } from '../stores/tags'

const emit = defineEmits<{
  'clear-filters': []
  'manage-tags': []
  'delete-selected': []
}>()
const fileStore = useFileStore()
const tagStore = useTagStore()
const typeLabels: Record<string, string> = { image: '图片', video: '视频', audio: '音频', doc: '文档' }
const scopeLabel = computed(() => {
  const tab = fileStore.activeTab
  if (tab.browseMode !== 'all' && tab.currentFolderPath) return tab.currentFolderPath
  return tab.isGlobalView ? '全部工作区' : tab.workspace || '尚未添加工作区'
})
const filters = computed(() => {
  const tab = fileStore.activeTab
  const values: { label: string; value: string }[] = []
  if (tab.searchText) values.push({ label: '名称含', value: tab.searchText })
  if (tab.searchType) values.push({ label: '类型', value: typeLabels[tab.searchType] || tab.searchType })
  if (tab.searchQuery.tags?.length) values.push({
    label: '标签',
    value: tab.searchQuery.tags.map(id => tagStore.tagMap.get(id)?.name || `#${id}`).join('、'),
  })
  return values
})
const filterCount = computed(() => Number(!!fileStore.activeTab.searchText) + Number(!!fileStore.activeTab.searchType) + (fileStore.activeTab.searchQuery.tags?.length || 0))
const selectionSummary = computed(() => `已选 ${fileStore.selectedCount} 项 / 共 ${fileStore.totalCount} 项${fileStore.hiddenSelectedCount ? `，含 ${fileStore.hiddenSelectedCount} 项当前未显示` : ''}`)
</script>

<style scoped>
.browser-context-bar {
  container-type: inline-size;
  display: flex;
  align-items: center;
  gap: 8px;
  height: 40px;
  flex: 0 0 40px;
  box-sizing: border-box;
  min-width: 0;
  padding: 0 14px;
  border-bottom: 1px solid var(--color-border);
  background: var(--color-bg-secondary);
  font-size: 12px;
  color: var(--color-text-secondary);
  overflow: hidden;
}
.browser-context-bar.has-selection { background: var(--color-accent-light); }
.filter-summary, .selection-toolbar, .context-description {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  min-width: 0;
  overflow: hidden;
  white-space: nowrap;
}
.scope-text, .filter-chip, .hidden-selection, .selection-count {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.scope-text { flex: 1; min-width: 60px; }
.filter-chip {
  flex: 0 1 auto;
  max-width: 180px;
  padding: 3px 6px;
  border-radius: var(--radius-sm);
  background: var(--color-bg-tertiary);
}
.selection-count { flex-shrink: 0; font-weight: 600; color: var(--color-text-primary); }
.selection-total { flex-shrink: 0; }
.context-actions { display: flex; align-items: center; gap: 6px; flex-shrink: 0; }
.context-actions :deep(.el-button + .el-button) { margin-left: 0; }
.filter-entry, .clear-filters-action { flex-shrink: 0; }
.filter-details { display: flex; flex-direction: column; align-items: flex-start; gap: 12px; max-height: min(60vh, 420px); overflow-y: auto; }
.filter-detail { display: grid; grid-template-columns: 42px minmax(0, 1fr); gap: 8px; width: 100%; }
.filter-detail > span:last-child { overflow-wrap: anywhere; }
@container (max-width: 680px) {
  .filter-chip, .selection-total, .delete-action { display: none; }
}
@container (max-width: 480px) {
  .manage-tags-action, .hidden-selection, .clear-filters-action { display: none; }
  .selection-count { flex-shrink: 1; }
}
</style>
