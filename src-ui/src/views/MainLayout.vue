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
      
      <TagPanel />
    </aside>

    <!-- 主内容区 -->
    <main class="main-content">
      <!-- 顶部工具栏 -->
      <header class="toolbar">
        <div class="toolbar-left">
          <el-button
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
            />
            <el-button
              :type="fileStore.viewMode === 'list' ? 'primary' : ''"
              :icon="List"
              @click="fileStore.viewMode = 'list'"
            />
          </el-button-group>
          
          <el-button
            :icon="appStore.detailPanelVisible ? ArrowRight : ArrowLeft"
            circle
            @click="appStore.toggleDetailPanel()"
          />
          
          <el-button :icon="Setting" circle @click="$router.push('/settings')" />
        </div>
      </header>

      <!-- 文件浏览器 -->
      <div class="content-area">
        <BrowserView />
      </div>
    </main>

    <!-- 详情面板 -->
    <DetailPanel v-if="appStore.detailPanelVisible" />
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
} from '@element-plus/icons-vue'
import { useAppStore } from '../stores/app'
import { useFileStore } from '../stores/files'
import TagPanel from './TagPanel.vue'
import SearchBar from '../components/SearchBar.vue'
import BrowserView from './BrowserView.vue'
import DetailPanel from './DetailPanel.vue'

const appStore = useAppStore()
const fileStore = useFileStore()
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
