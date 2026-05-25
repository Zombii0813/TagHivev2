<template>
  <div class="app-menu-bar">
    <el-dropdown
      v-for="menu in menus"
      :key="menu.label"
      trigger="click"
      placement="bottom-start"
      @command="handleCommand"
    >
      <span class="menu-trigger">{{ menu.label }}</span>
      <template #dropdown>
        <el-dropdown-menu>
          <template v-for="item in menu.items" :key="item.command || item.divided">
            <el-dropdown-item v-if="item.divided" divided disabled>
              <span class="menu-section-label">{{ item.label }}</span>
            </el-dropdown-item>
            <el-dropdown-item
              v-else
              :command="item.command"
              :disabled="item.disabled"
            >
              <el-icon v-if="item.icon" class="menu-item-icon">
                <component :is="item.icon" />
              </el-icon>
              <span>{{ item.label }}</span>
              <span v-if="item.shortcut" class="menu-item-shortcut">{{ item.shortcut }}</span>
            </el-dropdown-item>
          </template>
        </el-dropdown-menu>
      </template>
    </el-dropdown>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import {
  FolderAdd,
  Refresh,
  Download,
  Setting,
  Document,
  Search,
  CollectionTag,
  QuestionFilled,
  InfoFilled,
  SwitchButton,
} from '@element-plus/icons-vue'

interface MenuItem {
  label: string
  command?: string
  icon?: any
  shortcut?: string
  disabled?: boolean
  divided?: boolean
}

interface MenuGroup {
  label: string
  items: MenuItem[]
}

const emit = defineEmits<{
  (e: 'command', command: string): void
}>()

const menus = computed<MenuGroup[]>(() => [
  {
    label: '文件',
    items: [
      { label: '添加工作区', command: 'file:add-workspace', icon: FolderAdd },
      { label: '重新扫描当前工作区', command: 'file:rescan', icon: Refresh },
      { divided: true, label: '导入 / 导出' },
      { label: '导入文件…', command: 'file:import', icon: Download, disabled: true },
      { label: '导出标签数据…', command: 'file:export-tags', icon: Document, disabled: true },
      { divided: true, label: '会话' },
      { label: '退出', command: 'file:exit', icon: SwitchButton },
    ],
  },
  {
    label: '编辑',
    items: [
      { label: '查找文件', command: 'edit:focus-search', icon: Search, shortcut: 'Ctrl+F' },
      { label: '管理标签', command: 'edit:manage-tags', icon: CollectionTag },
      { divided: true, label: '选择' },
      { label: '全选当前列表', command: 'edit:select-all', shortcut: 'Ctrl+A', disabled: true },
      { label: '清除选择', command: 'edit:clear-selection', disabled: true },
    ],
  },
  {
    label: '工具',
    items: [
      { label: '查看日志…', command: 'tools:view-logs', icon: Document },
      { label: '打开数据目录', command: 'tools:open-data-dir', icon: FolderAdd, disabled: true },
      { divided: true, label: '系统' },
      { label: '设置', command: 'tools:settings', icon: Setting },
    ],
  },
  {
    label: '帮助',
    items: [
      { label: '使用文档', command: 'help:docs', icon: QuestionFilled, disabled: true },
      { label: '反馈问题', command: 'help:feedback', icon: QuestionFilled, disabled: true },
      { divided: true, label: '关于' },
      { label: '关于 TagHive', command: 'help:about', icon: InfoFilled },
    ],
  },
])

function handleCommand(command: string) {
  emit('command', command)
}
</script>

<style scoped>
.app-menu-bar {
  display: flex;
  align-items: center;
  gap: 2px;
  height: 32px;
  padding: 0 8px;
  background: var(--color-bg-primary);
  border-bottom: 1px solid var(--color-border);
  flex-shrink: 0;
  user-select: none;
  -webkit-app-region: drag;
}

.menu-trigger {
  display: inline-flex;
  align-items: center;
  height: 24px;
  padding: 0 10px;
  border-radius: 4px;
  font-size: 13px;
  color: var(--color-text-primary);
  cursor: default;
  transition: background-color 0.15s;
  -webkit-app-region: no-drag;
}

.menu-trigger:hover {
  background: var(--color-bg-secondary);
}

.menu-trigger:focus,
.menu-trigger:active {
  background: var(--color-primary-light, var(--color-bg-tertiary));
  outline: none;
}

.menu-item-icon {
  margin-right: 8px;
  font-size: 14px;
}

.menu-item-shortcut {
  margin-left: auto;
  padding-left: 16px;
  font-size: 12px;
  color: var(--color-text-secondary);
}

.menu-section-label {
  font-size: 11px;
  color: var(--color-text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
</style>
