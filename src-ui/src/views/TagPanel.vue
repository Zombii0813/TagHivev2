<template>
  <div class="tag-panel">
    <div class="panel-header">
      <h3>标签</h3>
      <el-button
        type="primary"
        size="small"
        :icon="Plus"
        @click="showCreateDialog = true"
      >
        新建
      </el-button>
    </div>

    <div class="tag-list" v-loading="tagStore.isLoading">
      <div
        v-for="tag in tagStore.tags"
        :key="tag.id"
        class="tag-item"
        :class="{ selected: tagStore.selectedTagIds.has(tag.id) }"
        :style="{ backgroundColor: tag.color + '20', borderColor: tag.color }"
        @click="handleTagClick(tag.id, $event)"
        @contextmenu.prevent="handleContextMenu(tag, $event)"
      >
        <span class="tag-dot" :style="{ backgroundColor: tag.color }"></span>
        <span class="tag-name">{{ tag.name }}</span>
        <span class="tag-count">{{ tag.file_count }}</span>
      </div>
    </div>

    <!-- 新建标签对话框 -->
    <el-dialog
      v-model="showCreateDialog"
      title="新建标签"
      width="400px"
    >
      <el-form :model="newTag" label-width="80px">
        <el-form-item label="名称">
          <el-input v-model="newTag.name" placeholder="输入标签名称" />
        </el-form-item>
        <el-form-item label="颜色">
          <el-color-picker v-model="newTag.color" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input
            v-model="newTag.description"
            type="textarea"
            placeholder="可选描述"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" @click="createTag">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Plus } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useTagStore } from '../stores/tags'
import { useFileStore } from '../stores/files'
import type { Tag } from '../types'

const tagStore = useTagStore()
const fileStore = useFileStore()

const showCreateDialog = ref(false)
const newTag = ref({
  name: '',
  color: '#409EFF',
  description: '',
})

onMounted(() => {
  tagStore.loadTags()
})

function handleTagClick(tagId: number, event: MouseEvent) {
  const multi = event.ctrlKey || event.metaKey
  tagStore.selectTag(tagId, multi)
  
  // 更新文件搜索
  if (tagStore.selectedTagIds.size > 0) {
    fileStore.search({
      tags: Array.from(tagStore.selectedTagIds),
      match_all_tags: false,
    })
  } else {
    fileStore.search({})
  }
}

async function createTag() {
  if (!newTag.value.name.trim()) {
    ElMessage.warning('请输入标签名称')
    return
  }
  
  try {
    await tagStore.createTag(
      newTag.value.name,
      newTag.value.color,
      newTag.value.description
    )
    ElMessage.success('标签创建成功')
    showCreateDialog.value = false
    newTag.value = { name: '', color: '#409EFF', description: '' }
  } catch (error) {
    ElMessage.error('标签创建失败')
  }
}

function handleContextMenu(tag: Tag, event: MouseEvent) {
  // 可以实现右键菜单
  console.log('Context menu for tag:', tag)
}
</script>

<style scoped>
.tag-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid var(--color-border);
}

.panel-header h3 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-secondary);
}

.tag-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.tag-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  margin-bottom: 4px;
  border-radius: 6px;
  border: 1px solid transparent;
  cursor: pointer;
  transition: all 0.2s ease;
}

.tag-item:hover {
  opacity: 0.8;
}

.tag-item.selected {
  border-width: 2px;
}

.tag-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.tag-name {
  flex: 1;
  font-size: 13px;
  color: var(--color-text-primary);
}

.tag-count {
  font-size: 11px;
  color: var(--color-text-tertiary);
  background: var(--color-bg-tertiary);
  padding: 2px 6px;
  border-radius: 10px;
}
</style>
