<template>
  <div class="main-layout">
    <!-- 侧边栏 -->
    <aside class="sidebar" :class="{ collapsed: appStore.sidebarCollapsed }">
      <div class="sidebar-header">
        <h1 class="logo">
          <el-icon><CollectionTag /></el-icon>
          <span v-if="!appStore.sidebarCollapsed">TagHive</span>
        </h1>
      </div>
      
      <div class="sidebar-content">
        <TagPanel />
      </div>
    </aside>

    <!-- 主内容区 -->
    <main class="main-content">
      <!-- 顶部工具栏 -->
      <header class="toolbar">
        <div class="toolbar-left">
          <el-button
            v-if="!isMobile"
            :icon="appStore.sidebarCollapsed ? Expand : Fold"
            circle
            @click="appStore.toggleSidebar()"
          />
          <SearchBar />
        </div>
        
        <div class="toolbar-right">
          <!-- 排序下拉菜单 -->
          <el-dropdown @command="handleSortCommand" trigger="click">
            <el-button :title="'排序'">
              <el-icon>
                <component :is="getSortIcon()" />
              </el-icon>
              <span class="sort-label">{{ getSortLabel() }}</span>
              <el-icon class="el-icon--right"><arrow-down /></el-icon>
            </el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="name_asc">
                  <el-icon><Sort /></el-icon> 名称升序
                </el-dropdown-item>
                <el-dropdown-item command="name_desc">
                  <el-icon><SortDown /></el-icon> 名称降序
                </el-dropdown-item>
                <el-dropdown-item divided command="modified_at_desc">
                  <el-icon><SortDown /></el-icon> 日期降序（最新）
                </el-dropdown-item>
                <el-dropdown-item command="modified_at_asc">
                  <el-icon><Sort /></el-icon> 日期升序（最早）
                </el-dropdown-item>
                <el-dropdown-item divided command="size_desc">
                  <el-icon><SortDown /></el-icon> 大小降序
                </el-dropdown-item>
                <el-dropdown-item command="size_asc">
                  <el-icon><Sort /></el-icon> 大小升序
                </el-dropdown-item>
                <el-dropdown-item divided command="duration_desc">
                  <el-icon><SortDown /></el-icon> 时长降序
                </el-dropdown-item>
                <el-dropdown-item command="duration_asc">
                  <el-icon><Sort /></el-icon> 时长升序
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>

          <el-button-group>
            <el-button
              :type="fileStore.viewMode === 'grid' ? 'primary' : ''"
              :icon="Grid"
              @click="fileStore.viewMode = 'grid'"
              :title="'网格视图'"
            />
            <el-button
              :type="fileStore.viewMode === 'list' ? 'primary' : ''"
              :icon="List"
              @click="fileStore.viewMode = 'list'"
              :title="'列表视图'"
            />
          </el-button-group>
          
          <el-button
            :icon="appStore.detailPanelVisible ? ArrowRight : ArrowLeft"
            circle
            @click="appStore.toggleDetailPanel()"
            :title="appStore.detailPanelVisible ? '隐藏详情' : '显示详情'"
          />
          
          <el-button 
            :icon="appStore.isDark ? Sunny : Moon" 
            circle 
            @click="appStore.toggleTheme()"
            :title="appStore.isDark ? '切换到浅色模式' : '切换到深色模式'" 
          />
          <el-button :icon="Setting" circle @click="$router.push('/settings')" :title="'设置'" />
        </div>
      </header>

      <!-- 文件浏览器 -->
      <div class="content-area">
        <BrowserView />
      </div>

      <!-- 底部状态栏 -->
      <footer class="status-bar">
        <div class="status-bar-left">
          <span v-if="fileStore.isLoading" class="status-text">
            <el-icon class="loading-icon"><Loading /></el-icon> 加载中...
          </span>
        </div>
        <div class="status-bar-right">
          <span class="status-text" v-if="fileStore.selectedCount > 0">
            已选中 {{ fileStore.selectedCount }} 个文件 / 共 {{ fileStore.totalCount }} 个文件
          </span>
          <span class="status-text" v-else>
            共 {{ fileStore.totalCount }} 个文件
          </span>
        </div>
      </footer>
    </main>

    <!-- 详情面板 -->
    <DetailPanel v-if="appStore.detailPanelVisible && !isMobile" />
    
    <!-- 批量操作面板 -->
    <BatchOperations />
  </div>
</template>

<script setup lang="ts">
import {
  CollectionTag,
  Expand,
  Fold,
  Grid,
  List,
  ArrowRight,
  ArrowLeft,
  ArrowDown,
  Setting,
  Sunny,
  Moon,
  Sort,
  SortUp,
  SortDown,
  Loading,
} from '@element-plus/icons-vue'
import { useAppStore } from '../stores/app'
import { useFileStore } from '../stores/files'
import TagPanel from './TagPanel.vue'
import SearchBar from '../components/SearchBar.vue'
import BrowserView from './BrowserView.vue'
import DetailPanel from './DetailPanel.vue'
import BatchOperations from '../components/BatchOperations.vue'
import { ref, onMounted, onUnmounted } from 'vue'

const appStore = useAppStore()
const fileStore = useFileStore()

// 检测是否为移动设备
const isMobile = ref(false)

// 计算属性：根据屏幕宽度判断是否为移动设备
const checkIsMobile = () => {
  isMobile.value = window.innerWidth < 768
}

onMounted(() => {
  checkIsMobile()
  window.addEventListener('resize', checkIsMobile)
})

onUnmounted(() => {
  window.removeEventListener('resize', checkIsMobile)
})

// 排序选项映射
const sortOptions: Record<string, { field: string; desc: boolean; label: string }> = {
  name_asc: { field: 'name', desc: false, label: '名称升序' },
  name_desc: { field: 'name', desc: true, label: '名称降序' },
  modified_at_asc: { field: 'modified_at', desc: false, label: '日期升序' },
  modified_at_desc: { field: 'modified_at', desc: true, label: '日期降序' },
  size_asc: { field: 'size', desc: false, label: '大小升序' },
  size_desc: { field: 'size', desc: true, label: '大小降序' },
  duration_asc: { field: 'duration', desc: false, label: '时长升序' },
  duration_desc: { field: 'duration', desc: true, label: '时长降序' },
}

// 处理排序命令
const handleSortCommand = (command: string) => {
  const option = sortOptions[command]
  if (option) {
    fileStore.setSortBy(option.field)
    fileStore.sortDesc = option.desc
  }
}

// 获取当前排序图标
const getSortIcon = () => {
  if (fileStore.sortDesc) {
    return SortDown
  }
  return SortUp
}

// 获取当前排序标签
const getSortLabel = () => {
  const currentField = fileStore.sortBy
  const currentDesc = fileStore.sortDesc
  
  for (const [key, option] of Object.entries(sortOptions)) {
    if (option.field === currentField && option.desc === currentDesc) {
      return option.label
    }
  }
  
  // 默认显示
  const fieldLabels: Record<string, string> = {
    name: '名称',
    modified_at: '日期',
    size: '大小',
    duration: '时长',
  }
  const fieldLabel = fieldLabels[currentField] || currentField
  return currentDesc ? `${fieldLabel}降序` : `${fieldLabel}升序`
}
</script>

<style scoped>
.main-layout {
  display: flex;
  height: 100vh;
  overflow: hidden;
}

.sidebar {
  width: var(--sidebar-width);
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  border-right: 1px solid var(--color-border);
  background: var(--color-bg-secondary);
  transition: width 0.3s ease;
}

.sidebar-content {
  flex: 1;
  overflow-y: auto;
}

/* 移动设备适配 */
@media (max-width: 768px) {
  .sidebar {
    flex-direction: row;
    height: 60px;
  }
  
  .sidebar-content {
    flex: 1;
    overflow-x: auto;
    overflow-y: hidden;
  }
  
  .sidebar.collapsed {
    width: 100% !important;
  }
}

.sidebar.collapsed {
  width: 60px;
}

.sidebar-header {
  padding: 16px;
  border-bottom: 1px solid var(--color-border);
}

.logo {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 18px;
  font-weight: 600;
  color: var(--color-text-primary);
  margin: 0;
}

.logo .el-icon {
  font-size: 24px;
  color: var(--color-accent);
}

.main-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  background: var(--color-bg-primary);
}

.toolbar {
  height: var(--header-height);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 16px;
  border-bottom: 1px solid var(--color-border);
  background: var(--color-bg-secondary);
  min-width: 0;
  flex-shrink: 0;
}

.toolbar-left,
.toolbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.toolbar-right {
  flex-wrap: nowrap;
}

/* 排序按钮样式 */
.toolbar-right .el-dropdown {
  flex-shrink: 0;
}

.toolbar-right .el-button-group {
  flex-shrink: 0;
}

.sort-label {
  margin-left: 4px;
  font-size: 13px;
  white-space: nowrap;
}

/* 响应式：小屏幕时隐藏排序文字 */
@media (max-width: 900px) {
  .sort-label {
    display: none;
  }
}

/* 响应式：更小的屏幕时调整间距 */
@media (max-width: 768px) {
  .toolbar {
    padding: 0 8px;
  }
  
  .toolbar-left,
  .toolbar-right {
    gap: 4px;
  }
}

.content-area {
  flex: 1;
  overflow: hidden;
  position: relative;
}

/* 底部状态栏 */
.status-bar {
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 16px;
  border-top: 1px solid var(--color-border);
  background: var(--color-bg-secondary);
  flex-shrink: 0;
  font-size: 12px;
  color: var(--color-text-secondary);
}

.status-bar-left,
.status-bar-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.status-text {
  display: flex;
  align-items: center;
  gap: 4px;
}

.loading-icon {
  animation: rotate 1s linear infinite;
}

@keyframes rotate {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

/* 响应式：小屏幕时调整状态栏 */
@media (max-width: 768px) {
  .status-bar {
    padding: 0 8px;
    font-size: 11px;
  }
}
</style>
