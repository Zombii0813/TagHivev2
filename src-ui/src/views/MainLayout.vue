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
  Setting,
  Sunny,
  Moon,
} from '@element-plus/icons-vue'
import { useAppStore } from '../stores/app'
import { useFileStore } from '../stores/files'
import TagPanel from './TagPanel.vue'
import SearchBar from '../components/SearchBar.vue'
import BrowserView from './BrowserView.vue'
import DetailPanel from './DetailPanel.vue'
import BatchOperations from '../components/BatchOperations.vue'
import { ref, onMounted, onUnmounted, computed } from 'vue'

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
}

.toolbar-left,
.toolbar-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.content-area {
  flex: 1;
  overflow: hidden;
  position: relative;
}
</style>
