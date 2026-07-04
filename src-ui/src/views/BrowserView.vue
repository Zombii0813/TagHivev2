<template>
  <div
    class="browser-view"
    :class="{ 'external-drop-active': externalDropActive }"
    @dragenter.prevent="handleExternalDragEnter"
    @dragover.prevent="handleExternalDragOver"
    @dragleave="handleExternalDragLeave"
    @drop.prevent="handleExternalDrop"
  >
    <!-- 空状态：无工作区时显示引导 -->
    <div v-if="appStore.workspaces.length === 0" class="empty-state-container">
      <EmptyState
        icon="folder"
        title="开始管理您的文件"
        description="选择一个文件夹作为工作区，开始使用 TagHive 管理您的文件和标签"
        action-text="选择文件夹"
        hint="支持图片、视频、音频、文档等多种文件类型"
        @action="selectWorkspace"
      />
    </div>

    <!-- 文件夹浏览模式 - 全局视图（多工作区蜂巢） -->
    <template v-else-if="fileStore.browseMode === 'folder' && appStore.isGlobalView">
      <div class="tree-view-container">
        <!-- 蜂巢导航（teleport 到 body，浮动在全局） -->
        <HoneycombTree
          :workspaces="appStore.workspaces"
          :boundary="scrollerRef"
          @select="handleFolderSelect"
          @switch-workspace="handleSwitchWorkspaceFromTree"
          @folder-op="handleFolderOp"
          @item-drop="handleTreeItemDrop"
        />

        <!-- 文件列表全宽 -->
        <div ref="scrollerRef" class="scroller-container" @mousedown="handleGridMouseDown">
          <!-- 框选遮罩 -->
          <div v-if="lasso.active" class="lasso-rect" :style="lassoStyle" />
          <FileScrollerArea
            :view-mode="fileStore.viewMode"
            :files="fileStore.files"
            :grid-rows="gridRows"
            :grid-item-height="gridItemHeight"
            :grid-item-width="gridItemWidth"
            :grid-row-style="gridRowStyle"
            :grid-cell-style="gridCellStyle"
            :selected-ids="fileStore.selectedIds"
            :multi-select-mode="multiSelectMode"
            :active-drop-file-id="activeDropFileId"
            :drag-tag-meta="dragTagMeta"
            @file-click="handleFileClick"
            @file-dblclick="handleFileDblClick"
            @file-contextmenu="handleFileContextMenu"
            @file-drag-over="handleFileDragOver"
            @file-drag-leave="handleFileDragLeave"
            @file-drop="handleFileDrop"
            @checkbox-click="handleCheckboxClick"
            @file-dragstart="handleFileDragStart"
            @file-dragend="handleItemDragEnd"
            @load-more="handleLoadMore"
          />

          <!-- 加载更多提示 -->
          <div v-if="fileStore.hasMore && fileStore.isLoading" class="load-more">
            <el-icon class="loading-icon"><Loading /></el-icon>
            <span>加载中...</span>
          </div>
        </div>
      </div>
    </template>

    <!-- 文件夹浏览模式（仅单工作区时有效） -->
    <template v-else-if="fileStore.browseMode === 'folder' && appStore.currentWorkspace">
      <div class="tree-view-container">
        <!-- 蜂巢导航（teleport 到 body，浮动在全局） -->
        <HoneycombTree
          :root-path="appStore.currentWorkspace"
          :boundary="scrollerRef"
          @select="handleFolderSelect"
          @folder-op="handleFolderOp"
          @item-drop="handleTreeItemDrop"
        />

        <!-- 文件列表全宽 -->
        <div ref="scrollerRef" class="scroller-container" @mousedown="handleGridMouseDown">
          <!-- 框选遮罩 -->
          <div v-if="lasso.active" class="lasso-rect" :style="lassoStyle" />
          <FileScrollerArea
            :view-mode="fileStore.viewMode"
            :files="fileStore.files"
            :grid-rows="gridRows"
            :grid-item-height="gridItemHeight"
            :grid-item-width="gridItemWidth"
            :grid-row-style="gridRowStyle"
            :grid-cell-style="gridCellStyle"
            :selected-ids="fileStore.selectedIds"
            :multi-select-mode="multiSelectMode"
            :active-drop-file-id="activeDropFileId"
            :drag-tag-meta="dragTagMeta"
            @file-click="handleFileClick"
            @file-dblclick="handleFileDblClick"
            @file-contextmenu="handleFileContextMenu"
            @file-drag-over="handleFileDragOver"
            @file-drag-leave="handleFileDragLeave"
            @file-drop="handleFileDrop"
            @checkbox-click="handleCheckboxClick"
            @file-dragstart="handleFileDragStart"
            @file-dragend="handleItemDragEnd"
            @load-more="handleLoadMore"
          />

          <!-- 加载更多提示 -->
          <div v-if="fileStore.hasMore && fileStore.isLoading" class="load-more">
            <el-icon class="loading-icon"><Loading /></el-icon>
            <span>加载中...</span>
          </div>
        </div>
      </div>
    </template>

    <!-- 文件夹树窗模式 - 全局视图（多工作区） -->
    <template v-else-if="fileStore.browseMode === 'tree' && appStore.isGlobalView">
      <div class="tree-view-container">
        <FolderTreePanel
          :workspaces="appStore.workspaces"
          :boundary="scrollerRef"
          @select="handleFolderSelect"
          @folder-op="handleFolderOp"
          @item-drop="handleTreeItemDrop"
        />
        <div ref="scrollerRef" class="scroller-container" @mousedown="handleGridMouseDown">
          <div v-if="lasso.active" class="lasso-rect" :style="lassoStyle" />
          <FileScrollerArea
            :view-mode="fileStore.viewMode"
            :files="fileStore.files"
            :grid-rows="gridRows"
            :grid-item-height="gridItemHeight"
            :grid-item-width="gridItemWidth"
            :grid-row-style="gridRowStyle"
            :grid-cell-style="gridCellStyle"
            :selected-ids="fileStore.selectedIds"
            :multi-select-mode="multiSelectMode"
            :active-drop-file-id="activeDropFileId"
            :drag-tag-meta="dragTagMeta"
            @file-click="handleFileClick"
            @file-dblclick="handleFileDblClick"
            @file-contextmenu="handleFileContextMenu"
            @file-drag-over="handleFileDragOver"
            @file-drag-leave="handleFileDragLeave"
            @file-drop="handleFileDrop"
            @checkbox-click="handleCheckboxClick"
            @file-dragstart="handleFileDragStart"
            @file-dragend="handleItemDragEnd"
            @load-more="handleLoadMore"
          />
          <div v-if="fileStore.hasMore && fileStore.isLoading" class="load-more">
            <el-icon class="loading-icon"><Loading /></el-icon>
            <span>加载中...</span>
          </div>
        </div>
      </div>
    </template>

    <!-- 文件夹树窗模式（仅单工作区时有效） -->
    <template v-else-if="fileStore.browseMode === 'tree' && appStore.currentWorkspace">
      <div class="tree-view-container">
        <FolderTreePanel
          :root-path="appStore.currentWorkspace"
          :boundary="scrollerRef"
          @select="handleFolderSelect"
          @folder-op="handleFolderOp"
          @item-drop="handleTreeItemDrop"
        />
        <div ref="scrollerRef" class="scroller-container" @mousedown="handleGridMouseDown">
          <div v-if="lasso.active" class="lasso-rect" :style="lassoStyle" />
          <FileScrollerArea
            :view-mode="fileStore.viewMode"
            :files="fileStore.files"
            :grid-rows="gridRows"
            :grid-item-height="gridItemHeight"
            :grid-item-width="gridItemWidth"
            :grid-row-style="gridRowStyle"
            :grid-cell-style="gridCellStyle"
            :selected-ids="fileStore.selectedIds"
            :multi-select-mode="multiSelectMode"
            :active-drop-file-id="activeDropFileId"
            :drag-tag-meta="dragTagMeta"
            @file-click="handleFileClick"
            @file-dblclick="handleFileDblClick"
            @file-contextmenu="handleFileContextMenu"
            @file-drag-over="handleFileDragOver"
            @file-drag-leave="handleFileDragLeave"
            @file-drop="handleFileDrop"
            @checkbox-click="handleCheckboxClick"
            @file-dragstart="handleFileDragStart"
            @file-dragend="handleItemDragEnd"
            @load-more="handleLoadMore"
          />
          <div v-if="fileStore.hasMore && fileStore.isLoading" class="load-more">
            <el-icon class="loading-icon"><Loading /></el-icon>
            <span>加载中...</span>
          </div>
        </div>
      </div>
    </template>

    <!-- 文件列表（all 模式） -->
    <template v-else>
      <div ref="scrollerRef" class="scroller-container" @mousedown="handleGridMouseDown">
        <!-- 框选遮罩 -->
        <div v-if="lasso.active" class="lasso-rect" :style="lassoStyle" />
        <FileScrollerArea
          :view-mode="fileStore.viewMode"
          :files="fileStore.files"
          :grid-rows="gridRows"
          :grid-item-height="gridItemHeight"
          :grid-item-width="gridItemWidth"
          :grid-row-style="gridRowStyle"
          :grid-cell-style="gridCellStyle"
          :selected-ids="fileStore.selectedIds"
          :multi-select-mode="multiSelectMode"
          :active-drop-file-id="activeDropFileId"
          :drag-tag-meta="dragTagMeta"
          :list-badge-modifier="true"
          @file-click="handleFileClick"
          @file-dblclick="handleFileDblClick"
          @file-contextmenu="handleFileContextMenu"
          @file-drag-over="handleFileDragOver"
          @file-drag-leave="handleFileDragLeave"
          @file-drop="handleFileDrop"
          @checkbox-click="handleCheckboxClick"
          @load-more="handleLoadMore"
        />
      </div>

      <!-- 加载更多提示 -->
      <div v-if="fileStore.hasMore && fileStore.isLoading" class="load-more">
        <el-icon class="loading-icon"><Loading /></el-icon>
        <span>加载中...</span>
      </div>
    </template>

    <!-- 文件右键菜单 -->
    <el-popover
      :visible="fileContextMenuVisible"
      :virtual-ref="fileContextMenuTrigger"
      virtual-triggering
      trigger="contextmenu"
      placement="bottom-start"
      :width="168"
      popper-class="context-menu-popover"
      @update:visible="onFileContextMenuVisibleChange"
    >
      <div class="context-menu">
        <div
          class="context-menu-item"
          :class="{ disabled: contextMenuTargetIds.length !== 1 }"
          @click="contextMenuTargetIds.length === 1 && openRenameDialog()"
        >
          <el-icon><Edit /></el-icon>
          <span>重命名</span>
        </div>
        <div class="context-menu-item" @click="openMoveDialog()">
          <el-icon><FolderOpened /></el-icon>
          <span>移动到...</span>
        </div>
        <div class="context-menu-item" @click="openCopyDialog()">
          <el-icon><CopyDocument /></el-icon>
          <span>复制到...</span>
        </div>
        <div
          class="context-menu-item"
          :class="{ disabled: contextMenuTargetIds.length !== 1 }"
          @click="contextMenuTargetIds.length === 1 && showInExplorer()"
        >
          <el-icon><Search /></el-icon>
          <span>在资源管理器中显示</span>
        </div>
        <div class="context-menu-divider" />
        <div class="context-menu-item delete" @click="deleteContextMenuFiles()">
          <el-icon><Delete /></el-icon>
          <span>删除</span>
        </div>
      </div>
    </el-popover>

    <!-- 重命名对话框 -->
    <el-dialog
      v-model="showRenameDialog"
      title="重命名文件"
      width="420px"
      append-to-body
      destroy-on-close
    >
      <el-input
        v-model="renameNewName"
        placeholder="输入新文件名（含扩展名）"
        maxlength="255"
        clearable
        @keyup.enter="confirmRename"
      />
      <template #footer>
        <el-button @click="showRenameDialog = false">取消</el-button>
        <el-button type="primary" :loading="renameSubmitting" :disabled="!renameNewName.trim()" @click="confirmRename">确定</el-button>
      </template>
    </el-dialog>

    <!-- 移动/复制目录选择对话框 -->
    <el-dialog
      v-model="showFileOpDialog"
      :title="fileOpMode === 'move' ? '选择移动目标目录' : '选择复制目标目录'"
      width="680px"
      destroy-on-close
      class="import-target-dialog"
    >
      <div class="import-dialog-body">
        <div class="import-dialog-hero">
          <div>
            <div class="import-dialog-title-row">
              <span class="import-dialog-title">{{ fileOpHeroTitle }}</span>
              <span class="import-dialog-count">{{ fileOpHeroCount }}</span>
            </div>
            <p class="import-dialog-description">
              请选择工作区中的目标目录，确认后会将{{ fileOpFolderSource ? '文件夹' : '文件' }}{{ fileOpMode === 'move' ? '移动' : '复制' }}到该位置。
            </p>
          </div>
          <div class="import-dialog-workspace import-dialog-workspace-select">
            <span class="workspace-label">目标工作区</span>
            <el-select
              v-model="fileOpTargetWorkspace"
              size="small"
              :disabled="fileOpTreeLoading || fileOpSubmitting"
              @change="handleFileOpWorkspaceChange"
            >
              <el-option
                v-for="ws in appStore.workspaces"
                :key="ws"
                :label="getFolderDisplayName(ws)"
                :value="ws"
              >
                <span class="workspace-option-name">{{ getFolderDisplayName(ws) }}</span>
                <span class="workspace-option-path">{{ ws }}</span>
              </el-option>
            </el-select>
          </div>
        </div>

        <div class="import-target-summary-card">
          <div class="summary-main">
            <span class="summary-label">当前目标</span>
            <strong>{{ getFolderDisplayName(fileOpTargetDir || fileOpTargetWorkspace || '') || '未选择' }}</strong>
            <span class="summary-path">{{ getRelativeImportPath(fileOpTargetDir || fileOpTargetWorkspace || '', fileOpTargetWorkspace) }}</span>
          </div>
          <div class="summary-actions">
            <el-button text @click="toggleFileOpCreateFolder">
              {{ showFileOpCreateFolder ? '收起新建' : '新建目录' }}
            </el-button>
          </div>
        </div>

        <div v-if="showFileOpCreateFolder" class="create-folder-panel">
          <div class="create-folder-info">
            <span>在</span>
            <strong>{{ fileOpTargetDir || fileOpTargetWorkspace }}</strong>
            <span>下创建目录</span>
          </div>
          <div class="create-folder-form">
            <el-input
              v-model="fileOpNewFolderName"
              placeholder="输入新目录名称"
              maxlength="80"
              clearable
              @keyup.enter="createFolderInFileOpDialog"
            />
            <el-button
              type="primary"
              :loading="fileOpCreatingFolder"
              :disabled="!fileOpNewFolderName.trim() || fileOpCreatingFolder"
              @click="createFolderInFileOpDialog"
            >
              创建
            </el-button>
          </div>
        </div>

        <div class="import-tree-panel">
          <div class="import-tree-panel-header">
            <span>目录层级</span>
            <span class="import-tree-tip">显示工作区内全部目录，支持空目录与新建目录</span>
          </div>
          <div v-if="fileOpTreeLoading" class="import-dialog-loading">
            <el-icon class="loading-icon"><Loading /></el-icon>
            <span>正在加载目录...</span>
          </div>
          <el-tree
            v-else-if="fileOpTreeData.length"
            ref="fileOpTreeRef"
            :data="fileOpTreeData"
            node-key="path"
            :default-expanded-keys="fileOpDefaultExpandedKeys"
            highlight-current
            :expand-on-click-node="false"
            :current-node-key="fileOpTargetDir"
            :props="{ label: 'name', children: 'children' }"
            @node-click="handleFileOpTargetSelect"
          >
            <template #default="{ data }">
              <div class="import-tree-node">
                <div class="import-tree-main">
                  <span class="import-tree-name">{{ data.name }}</span>
                  <span class="import-tree-meta">{{ getRelativeImportPath(data.path) }}</span>
                </div>
                <span class="import-tree-badge">{{ data.file_count }} 文件</span>
              </div>
            </template>
          </el-tree>
          <el-empty v-else description="该工作区暂无可选目录" :image-size="80" />
        </div>
      </div>

      <template #footer>
        <el-button @click="showFileOpDialog = false">取消</el-button>
        <el-button
          type="primary"
          :disabled="!fileOpTargetDir || fileOpSubmitting"
          :loading="fileOpSubmitting"
          @click="confirmFileOp"
        >
          确认{{ fileOpMode === 'move' ? '移动' : '复制' }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 原有拖拽导入对话框 -->
    <el-dialog
      v-model="showImportDialog"
      title="选择移动目标目录"
      width="680px"
      destroy-on-close
      class="import-target-dialog"
    >
      <div class="import-dialog-body">
        <div class="import-dialog-hero">
          <div>
            <div class="import-dialog-title-row">
              <span class="import-dialog-title">拖入文件准备移动</span>
              <span class="import-dialog-count">{{ pendingImportPaths.length }} 个文件</span>
            </div>
            <p class="import-dialog-description">
              请选择工作区中的目标目录，确认后会将拖入文件移动到该位置。
            </p>
          </div>
          <div class="import-dialog-workspace">
            <span class="workspace-label">工作区</span>
            <strong>{{ getFolderDisplayName(appStore.currentWorkspace || '') }}</strong>
          </div>
        </div>

        <div class="import-target-summary-card">
          <div class="summary-main">
            <span class="summary-label">当前目标</span>
            <strong>{{ getFolderDisplayName(selectedImportTarget || appStore.currentWorkspace || '') || '未选择' }}</strong>
            <span class="summary-path">{{ getRelativeImportPath(selectedImportTarget || appStore.currentWorkspace || '') }}</span>
          </div>
          <div class="summary-actions">
            <el-button text @click="toggleCreateFolderInline">
              {{ showCreateFolderInline ? '收起新建' : '新建目录' }}
            </el-button>
          </div>
        </div>

        <div v-if="showCreateFolderInline" class="create-folder-panel">
          <div class="create-folder-info">
            <span>在</span>
            <strong>{{ selectedImportTarget || appStore.currentWorkspace }}</strong>
            <span>下创建目录</span>
          </div>
          <div class="create-folder-form">
            <el-input
              v-model="newFolderName"
              placeholder="输入新目录名称"
              maxlength="80"
              clearable
              @keyup.enter="createFolderUnderSelectedTarget"
            />
            <el-button
              type="primary"
              :loading="creatingFolder"
              :disabled="!canCreateFolder"
              @click="createFolderUnderSelectedTarget"
            >
              创建
            </el-button>
          </div>
        </div>

        <div class="import-tree-panel">
          <div class="import-tree-panel-header">
            <span>目录层级</span>
            <span class="import-tree-tip">显示工作区内全部目录，支持空目录与新建目录</span>
          </div>

          <div v-if="importTreeLoading" class="import-dialog-loading">
            <el-icon class="loading-icon"><Loading /></el-icon>
            <span>正在加载目录...</span>
          </div>

          <el-tree
            v-else-if="importTreeData.length"
            ref="importTreeRef"
            :data="importTreeData"
            node-key="path"
            :default-expanded-keys="defaultExpandedImportKeys"
            highlight-current
            :expand-on-click-node="false"
            :current-node-key="selectedImportTarget"
            :props="{ label: 'name', children: 'children' }"
            @node-click="handleImportTargetSelect"
          >
            <template #default="{ data }">
              <div class="import-tree-node">
                <div class="import-tree-main">
                  <span class="import-tree-name">{{ data.name }}</span>
                  <span class="import-tree-meta">{{ getRelativeImportPath(data.path) }}</span>
                </div>
                <span class="import-tree-badge">{{ data.file_count }} 文件</span>
              </div>
            </template>
          </el-tree>

          <el-empty v-else description="当前工作区暂无可选目录" :image-size="80" />
        </div>
      </div>

      <template #footer>
        <el-button @click="closeImportDialog">取消</el-button>
        <el-button
          type="primary"
          :disabled="!selectedImportTarget || !pendingImportPaths.length || importSubmitting"
          :loading="importSubmitting"
          @click="confirmImportToSelectedDirectory"
        >
          确认移动
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, watch, ref, onUnmounted, nextTick } from 'vue'
import 'vue-virtual-scroller/dist/vue-virtual-scroller.css'
import { invoke } from '@tauri-apps/api/core'
import { useAppStore } from '../stores/app'
import { useFileStore } from '../stores/files'
import { useTagStore } from '../stores/tags'
import FileScrollerArea from '../components/FileScrollerArea.vue'
import HoneycombTree from '../components/HoneycombTree.vue'
import FolderTreePanel from '../components/FolderTreePanel.vue'
import EmptyState from '../components/EmptyState.vue'
import type { FileSummary, FolderNode } from '../types'
import { open } from '@tauri-apps/plugin-shell'
import { fileApi } from '../api/files'
import { folderApi } from '../api/folders'
import { wsClient } from '../api/websocket'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Loading, Edit, Delete, FolderOpened, CopyDocument, Search } from '@element-plus/icons-vue'
import type { ElTree } from 'element-plus'
import { getDraggedTagId, getDroppedFilePaths, hasExternalFiles, hasTagDrag, isTagDragInProgress, clearTagDragState, getDragMeta } from '../utils/drag'
import { setItemDragData, clearItemDragState, getItemDrag } from '../utils/dragItems'
import type { TagDragMeta } from '../utils/drag'


const appStore = useAppStore()
const fileStore = useFileStore()
const tagStore = useTagStore()

const scrollerRef = ref<HTMLElement | null>(null)
const containerWidth = ref(0)
const activeDropFileId = ref<number | null>(null)
const dragTagMeta = ref<TagDragMeta | null>(null)
const externalDropActive = ref(false)
const pendingImportPaths = ref<string[]>([])
const showImportDialog = ref(false)
const importTreeLoading = ref(false)
const importSubmitting = ref(false)
const creatingFolder = ref(false)
const showCreateFolderInline = ref(false)
const newFolderName = ref('')
const importFolderTree = ref<FolderNode[]>([])
const selectedImportTarget = ref('')
const lastHandledExternalDropSignature = ref('')
const importTreeRef = ref<InstanceType<typeof ElTree> | null>(null)

// 文件右键菜单状态
const fileContextMenuVisible = ref(false)
const fileContextMenuTrigger = ref<HTMLElement>()
const contextMenuTargetIds = ref<number[]>([])
const contextMenuTargetFile = ref<FileSummary | null>(null)

// 右键菜单锚点（单例，始终存在于 DOM，避免删除时闪烁）
const fileContextMenuAnchor = (() => {
  const el = document.createElement('div')
  el.style.cssText = 'position:fixed;left:-9999px;top:-9999px;width:1px;height:1px;pointer-events:none'
  document.body.appendChild(el)
  return el
})()

// 重命名对话框状态
const showRenameDialog = ref(false)
const renameNewName = ref('')
const renameSubmitting = ref(false)

// 移动/复制对话框状态
const showFileOpDialog = ref(false)
const fileOpMode = ref<'move' | 'copy'>('move')
const fileOpTargetDir = ref('')
const fileOpTargetWorkspace = ref('')
const fileOpTreeLoading = ref(false)
const fileOpSubmitting = ref(false)
const fileOpFolderTree = ref<FolderNode[]>([])
const showFileOpCreateFolder = ref(false)
const fileOpNewFolderName = ref('')
const fileOpCreatingFolder = ref(false)
const fileOpTreeRef = ref<InstanceType<typeof ElTree> | null>(null)
// 文件夹来源：非空时表示本次移动/复制的对象是一个文件夹（其路径），否则为文件
const fileOpFolderSource = ref<string | null>(null)
const fileOpFolderSourceWs = ref<string>('')

const currentImportDirectory = computed(() => {
  if (fileStore.browseMode === 'folder' || fileStore.browseMode === 'tree') {
    return fileStore.currentFolderPath || appStore.currentWorkspace
  }
  return appStore.currentWorkspace
})

// 移动/复制对话框标题与计数（区分文件夹来源与文件来源）
const fileOpHeroTitle = computed(() => {
  const verb = fileOpMode.value === 'move' ? '移动' : '复制'
  return fileOpFolderSource.value ? `${verb}文件夹` : `${verb}文件`
})
const fileOpHeroCount = computed(() => {
  if (fileOpFolderSource.value) {
    return getFolderDisplayName(fileOpFolderSource.value)
  }
  return `${contextMenuTargetIds.value.length} 个文件`
})

const importTreeData = computed<FolderNode[]>(() => {
  if (!appStore.currentWorkspace) {
    return []
  }

  return [{
    name: getFolderDisplayName(appStore.currentWorkspace),
    path: appStore.currentWorkspace,
    file_count: 0,
    children: importFolderTree.value,
    is_expanded: true,
  }]
})

const defaultExpandedImportKeys = computed(() => {
  const targetPath = selectedImportTarget.value || appStore.currentWorkspace
  if (!targetPath || !appStore.currentWorkspace) {
    return []
  }

  const rootPath = appStore.currentWorkspace
  const normalizedRoot = rootPath.replace(/\\/g, '/')
  const normalizedTarget = targetPath.replace(/\\/g, '/')

  if (!normalizedTarget.startsWith(normalizedRoot)) {
    return [rootPath]
  }

  const relative = normalizedTarget.slice(normalizedRoot.length).replace(/^\/+/, '')
  const keys = [rootPath]
  let currentPath = normalizedRoot

  relative.split('/').filter(Boolean).forEach((segment) => {
    currentPath = `${currentPath}/${segment}`
    keys.push(currentPath)
  })

  return keys
})

const canCreateFolder = computed(() => {
  return !!(newFolderName.value.trim() && (selectedImportTarget.value || appStore.currentWorkspace) && !creatingFolder.value)
})

// 移动/复制对话框的目录树数据
const fileOpTreeData = computed<FolderNode[]>(() => {
  const ws = fileOpTargetWorkspace.value
  if (!ws) return []
  return [{
    name: getFolderDisplayName(ws),
    path: ws,
    file_count: 0,
    children: fileOpFolderTree.value,
    is_expanded: true,
  }]
})

const fileOpDefaultExpandedKeys = computed(() => {
  const rootPath = fileOpTargetWorkspace.value
  const targetPath = fileOpTargetDir.value || rootPath
  if (!targetPath || !rootPath) return []
  const normalizedRoot = rootPath.replace(/\\/g, '/')
  const normalizedTarget = targetPath.replace(/\\/g, '/')
  if (!normalizedTarget.startsWith(normalizedRoot)) return [rootPath]
  const relative = normalizedTarget.slice(normalizedRoot.length).replace(/^\/+/, '')
  const keys = [rootPath]
  let currentPath = normalizedRoot
  relative.split('/').filter(Boolean).forEach((segment) => {
    currentPath = `${currentPath}/${segment}`
    keys.push(currentPath)
  })
  return keys
})

// ResizeObserver 实例
let resizeObserver: ResizeObserver | null = null
let unlistenNativeDragDrop: (() => void) | null = null
let lastHandledExternalDropResetTimer: ReturnType<typeof setTimeout> | null = null

// Grid 布局配置
const GAP = 16 // 间距
const GAP_Y = 16 // 行间距（仅 grid-view 有效，list-view 行内无垂直间距）
const INFO_HEIGHT = 80 // 文件名等信息区域高度（包含标签区域）
const GRID_PADDING_X = 10 // grid-view 左右内边距（与 .grid-view CSS 保持一致），列数计算需扣除
// 行内垂直 padding：给 hover 时 translateY(-4px) scale(1.04) 留呼吸空间，
// 避免溢出 row 高度后被 vue-virtual-scroller 内置的 overflow:hidden 裁掉。
const ROW_PADDING_Y = 12

// 计算每行显示的列数（根据固定卡片尺寸和容器宽度自动决定列数）
const gridColumns = computed(() => {
  if (containerWidth.value === 0) return 4
  const usable = Math.max(containerWidth.value - GRID_PADDING_X * 2, fileStore.gridItemSize)
  const columns = Math.floor((usable + GAP) / (fileStore.gridItemSize + GAP))
  return Math.max(columns, 1) // 最少显示 1 列
})

// 卡片宽度固定为 gridItemSize
const gridItemWidth = computed(() => fileStore.gridItemSize)

// 计算每个 grid item 的高度（含 row 上下 padding，给 hover 上浮预留缓冲）
const gridItemHeight = computed(() => {
  return fileStore.gridItemSize + INFO_HEIGHT + ROW_PADDING_Y * 2 - GAP_Y
})

// 将文件列表按行分组
interface GridRow {
  rowIndex: number
  files: FileSummary[]
}

const gridRows = computed<GridRow[]>(() => {
  const rows: GridRow[] = []
  const files = fileStore.files
  const columns = gridColumns.value
  
  for (let i = 0; i < files.length; i += columns) {
    rows.push({
      rowIndex: Math.floor(i / columns),
      files: files.slice(i, i + columns)
    })
  }
  
  return rows
})

// Grid 行样式
// 每行宽度固定为 columns * itemWidth + (columns-1) * gap，
// 通过 margin: 0 auto 让整行相对滚动容器水平居中（两边留白对称），
// 行内使用 flex-start，最后一行未填满时单元格靠左而非居中。
// 上下 padding 给 hover 上浮 + 阴影留呼吸空间（高度已在 gridItemHeight 中预留）。
const gridRowStyle = computed(() => {
  const columns = gridColumns.value
  const rowWidth = columns * gridItemWidth.value + (columns - 1) * GAP
  return {
    display: 'flex',
    gap: `${GAP}px`,
    justifyContent: 'flex-start',
    width: `${rowWidth}px`,
    margin: '0 auto',
    height: `${gridItemHeight.value}px`,
    paddingTop: `${ROW_PADDING_Y}px`,
    paddingBottom: `${ROW_PADDING_Y}px`,
  }
})

// Grid 单元格样式
const gridCellStyle = computed(() => ({
  flex: '0 0 auto',
  width: `${gridItemWidth.value}px`
}))

// 监听容器宽度变化
function updateContainerWidth() {
  if (scrollerRef.value) {
    containerWidth.value = scrollerRef.value.clientWidth
  }
}

// 触底加载更多。真正滚动的是 RecycleScroller 自身（内部 overflow:auto），
// 其 @scroll-end 在最后一个 item 可见时触发，故由 FileScrollerArea 透传上来。
// 按当前浏览上下文分发到对应的分页加载：文件夹/树窗模式走目录内分页，
// 其余（全部文件 / 标签过滤）走搜索分页。
function handleLoadMore() {
  if (!fileStore.hasMore || fileStore.isLoading) return

  const inFolderContext =
    (fileStore.browseMode === 'folder' || fileStore.browseMode === 'tree') &&
    !tagStore.hasSelection &&
    !!fileStore.currentFolderPath

  if (inFolderContext) {
    fileStore.loadMoreFolderContents()
  } else {
    fileStore.loadMore()
  }
}

function normalizeDroppedPaths(paths: string[]): string[] {
  return Array.from(new Set(paths.map(path => path.trim()).filter(Boolean)))
}

function getFolderDisplayName(path: string): string {
  const parts = path.split(/[/\\]/)
  return parts[parts.length - 1] || path
}

function getRelativeImportPath(path: string, rootOverride?: string): string {
  const root = rootOverride || appStore.currentWorkspace
  if (!path || !root) {
    return '未选择目录'
  }

  const normalizedRoot = root.replace(/\\/g, '/')
  const normalizedPath = path.replace(/\\/g, '/')

  if (normalizedPath === normalizedRoot) {
    return '工作区根目录'
  }

  if (!normalizedPath.startsWith(normalizedRoot)) {
    return normalizedPath
  }

  return normalizedPath.slice(normalizedRoot.length).replace(/^\/+/, '') || '工作区根目录'
}

function markExternalDropHandled(paths: string[]) {
  const signature = `${currentImportDirectory.value || ''}::${[...paths].sort().join('|')}`
  lastHandledExternalDropSignature.value = signature

  if (lastHandledExternalDropResetTimer) {
    clearTimeout(lastHandledExternalDropResetTimer)
  }

  lastHandledExternalDropResetTimer = setTimeout(() => {
    if (lastHandledExternalDropSignature.value === signature) {
      lastHandledExternalDropSignature.value = ''
    }
  }, 600)
}

function isDuplicateExternalDrop(paths: string[]): boolean {
  const signature = `${currentImportDirectory.value || ''}::${[...paths].sort().join('|')}`
  return signature.length > 2 && signature === lastHandledExternalDropSignature.value
}

async function importExternalFiles(paths: string[], targetDir: string) {
  const normalizedPaths = normalizeDroppedPaths(paths)

  if (!normalizedPaths.length) {
    return
  }

  try {
    const result = await fileApi.importToDirectory(normalizedPaths, targetDir)

    await refreshFileList()

    ElMessage.success(`已移动 ${result.files.length} 个文件到 ${result.target_dir}`)
  } catch (error) {
    console.error('Failed to import dropped files:', error)
    ElMessage.error('拖拽导入文件失败')
  }
}

async function loadImportFolderTree() {
  if (!appStore.currentWorkspace) {
    importFolderTree.value = []
    return
  }

  importTreeLoading.value = true
  try {
    const result = await folderApi.getTree(appStore.currentWorkspace)
    importFolderTree.value = result.folders
  } catch (error) {
    console.error('Failed to load import folder tree:', error)
    ElMessage.error('加载目标目录失败')
    importFolderTree.value = []
  } finally {
    importTreeLoading.value = false
    await nextTick()
    if (selectedImportTarget.value) {
      importTreeRef.value?.setCurrentKey(selectedImportTarget.value)
    }
  }
}

async function promptImportTarget(paths: string[]) {
  const normalizedPaths = normalizeDroppedPaths(paths)

  if (!normalizedPaths.length) {
    return
  }

  if (isDuplicateExternalDrop(normalizedPaths)) {
    return
  }

  if (!appStore.currentWorkspace) {
    ElMessage.warning('请先选择工作区，再拖入文件')
    return
  }

  markExternalDropHandled(normalizedPaths)
  pendingImportPaths.value = normalizedPaths
  selectedImportTarget.value = currentImportDirectory.value || appStore.currentWorkspace
  showCreateFolderInline.value = false
  newFolderName.value = ''
  showImportDialog.value = true
  await loadImportFolderTree()
}

function handleImportTargetSelect(node: FolderNode) {
  selectedImportTarget.value = node.path
}

function toggleCreateFolderInline() {
  showCreateFolderInline.value = !showCreateFolderInline.value
  if (!showCreateFolderInline.value) {
    newFolderName.value = ''
  }
}

function closeImportDialog() {
  showImportDialog.value = false
  pendingImportPaths.value = []
  importSubmitting.value = false
  creatingFolder.value = false
  showCreateFolderInline.value = false
  newFolderName.value = ''
}

async function createFolderUnderSelectedTarget() {
  const parentPath = selectedImportTarget.value || appStore.currentWorkspace
  const folderName = newFolderName.value.trim()

  if (!appStore.currentWorkspace || !parentPath || !folderName) {
    return
  }

  creatingFolder.value = true
  try {
    let createdPath = ''
    let createdName = folderName

    try {
      const result = await folderApi.createFolder(appStore.currentWorkspace, parentPath, folderName)
      createdPath = result.path
      createdName = result.name
    } catch (error: any) {
      const statusCode = error?.response?.status
      if (statusCode !== 404) {
        throw error
      }

      const targetPath = `${parentPath.replace(/[\\/]+$/, '')}/${folderName}`
      await invoke('create_folder', { path: targetPath })
      createdPath = targetPath.replace(/\\/g, '/')
    }

    await loadImportFolderTree()
    selectedImportTarget.value = createdPath
    importTreeRef.value?.setCurrentKey(createdPath)
    newFolderName.value = ''
    showCreateFolderInline.value = false
    ElMessage.success(`已创建目录：${createdName}`)
  } catch (error: any) {
    const message = error?.response?.data?.detail || '创建目录失败'
    console.error('Failed to create folder:', error)
    ElMessage.error(message)
  } finally {
    creatingFolder.value = false
  }
}

async function confirmImportToSelectedDirectory() {
  if (!selectedImportTarget.value || !pendingImportPaths.value.length) {
    return
  }

  importSubmitting.value = true
  try {
    await importExternalFiles(pendingImportPaths.value, selectedImportTarget.value)
    closeImportDialog()
  } finally {
    importSubmitting.value = false
  }
}

onMounted(() => {
  updateContainerWidth()
  window.addEventListener('resize', updateContainerWidth)
  window.addEventListener('close-context-menus', closeFileContextMenu)
  window.addEventListener('keydown', handleGlobalKeyDown)
  
  // 使用 ResizeObserver 监听容器大小变化
  if (scrollerRef.value && typeof ResizeObserver !== 'undefined') {
    resizeObserver = new ResizeObserver(() => {
      updateContainerWidth()
    })
    resizeObserver.observe(scrollerRef.value)
  }
  
  if (appStore.currentWorkspace) {
    if (fileStore.browseMode === 'tree') {
      // 树窗模式：FolderTreePanel 不自动 emit，初始挂载时按记忆层级加载文件列表
      const ws = appStore.currentWorkspace
      const remembered = fileStore.getRememberedFolder(ws)
      const target = remembered && findOwnerWorkspace(remembered) === ws ? remembered : ws
      fileStore.loadFolderContents(target)
    } else {
      fileStore.search({ root: appStore.currentWorkspace })
    }
    // 当前工作区不可达（如外部移动硬盘未连接）时提示用户，
    // 仍展示数据库中的缓存数据，避免误以为数据丢失。
    if (appStore.unavailableWorkspaces.has(appStore.currentWorkspace)) {
      ElMessage.warning('当前工作区暂时不可访问（如移动硬盘未连接），显示的是已缓存数据，重新连接后扫描即可同步')
    }
  }
})

onUnmounted(() => {
  window.removeEventListener('resize', updateContainerWidth)
  window.removeEventListener('close-context-menus', closeFileContextMenu)
  window.removeEventListener('keydown', handleGlobalKeyDown)
  
  // 移除 ResizeObserver
  if (resizeObserver) {
    resizeObserver.disconnect()
    resizeObserver = null
  }
  
  if (unlistenNativeDragDrop) {
    unlistenNativeDragDrop()
    unlistenNativeDragDrop = null
  }

  if (lastHandledExternalDropResetTimer) {
    clearTimeout(lastHandledExternalDropResetTimer)
    lastHandledExternalDropResetTimer = null
  }

  // 清理右键菜单锚点 DOM，避免组件多次挂载残留
  if (fileContextMenuAnchor.parentNode) {
    fileContextMenuAnchor.parentNode.removeChild(fileContextMenuAnchor)
  }
})

// 监听工作区变化
watch(() => appStore.currentWorkspace, (newPath) => {
  if (newPath) {
    if (fileStore.browseMode === 'folder') {
      // 文件夹浏览模式：由 HoneycombTree 加载完目录树后 emit 记忆层级，
      // 经 handleFolderSelect 恢复文件列表，这里不重复加载，避免闪烁与竞争。
    } else if (fileStore.browseMode === 'tree') {
      // 树窗模式：FolderTreePanel 不自动 emit，这里恢复该工作区上次浏览的层级
      const remembered = fileStore.getRememberedFolder(newPath)
      const target = remembered && findOwnerWorkspace(remembered) === newPath ? remembered : newPath
      fileStore.loadFolderContents(target)
    } else {
      // 全部文件模式：搜索所有文件
      fileStore.search({ root: newPath })
    }
  }
})

// 监听浏览模式变化
watch(() => fileStore.browseMode, async (newMode) => {
  if (!appStore.currentWorkspace) return
  
  if (newMode === 'folder' || newMode === 'tree') {
    // 切换到文件夹浏览/树窗模式：恢复该工作区上次浏览的层级
    const ws = appStore.currentWorkspace
    const remembered = fileStore.getRememberedFolder(ws)
    const target = remembered && findOwnerWorkspace(remembered) === ws ? remembered : ws
    await fileStore.loadFolderContents(target)
  } else {
    // 切换到全部文件模式：搜索所有文件
    await fileStore.search({ root: appStore.currentWorkspace })
  }
  
  // 等待 DOM 更新后重新设置 ResizeObserver
  await nextTick()
  
  // 清理旧的 ResizeObserver
  if (resizeObserver) {
    resizeObserver.disconnect()
    resizeObserver = null
  }
  
  // 更新容器宽度
  updateContainerWidth()
  
  // 重新设置 ResizeObserver
  if (scrollerRef.value && typeof ResizeObserver !== 'undefined') {
    resizeObserver = new ResizeObserver(() => {
      updateContainerWidth()
    })
    resizeObserver.observe(scrollerRef.value)
  }
})

// 当选中数量归零时，自动退出多选模式
watch(() => fileStore.selectedCount, (count) => {
  if (count === 0) multiSelectMode.value = false
})

async function selectWorkspace() {
  console.log('[BrowserView] selectWorkspace called')
  try {
    const path = await appStore.selectFolder()
    console.log('[BrowserView] selectFolder returned:', path)
    if (path) {
      // 连接 WebSocket
      wsClient.connect()
      
      // 订阅扫描完成事件
      const unsubscribeCompleted = wsClient.on<{ path: string; total: number }>('scan_completed', (data) => {
        ElMessage.success(`扫描完成，共 ${data.total} 个文件`)
        // 扫描完成后刷新文件列表：保持当前浏览模式
        if (fileStore.browseMode === 'folder' || fileStore.browseMode === 'tree') {
          const targetPath = fileStore.currentFolderPath || path
          fileStore.loadFolderContents(targetPath)
        } else {
          fileStore.search({ root: path })
        }
        unsubscribeCompleted()
      })
      
      const unsubscribeError = wsClient.on<{ message: string }>('scan_error', (error) => {
        ElMessage.error(`扫描失败: ${error.message}`)
        unsubscribeError()
      })
      
      // 开始扫描
      wsClient.startScan(path)
    }
  } catch (error) {
    console.error('[BrowserView] Error in selectWorkspace:', error)
  }
}

function handleFileClick(fileId: number, event: MouseEvent) {
  const multi = event.ctrlKey || event.metaKey
  const range = event.shiftKey

  if (range && fileStore.selectedIds.size > 0) {
    // Shift 点击：范围选择，进入多选模式
    const lastSelected = Array.from(fileStore.selectedIds).pop()
    if (lastSelected) {
      fileStore.selectRange(lastSelected, fileId)
    }
    multiSelectMode.value = true
  } else if (multi) {
    // Ctrl/Meta 点击：追加/取消单个，进入多选模式
    fileStore.selectFile(fileId, true)
    multiSelectMode.value = true
  } else if (multiSelectMode.value) {
    // 已在多选模式：直接追加选中（无需按 Ctrl）
    fileStore.selectFile(fileId, true)
  } else {
    // 普通点击：单选，不进入多选模式（选择框不高亮）
    fileStore.selectFile(fileId, false)
    multiSelectMode.value = false
  }
}

// 复选框点击：进入多选模式，切换该文件的选中状态
function handleCheckboxClick(fileId: number) {
  fileStore.selectFile(fileId, true)
  multiSelectMode.value = true
}

// Ctrl+A 全选，进入多选模式
function handleGlobalKeyDown(e: KeyboardEvent) {
  if ((e.ctrlKey || e.metaKey) && e.key === 'a') {
    const active = document.activeElement
    // 焦点在输入框时不拦截
    if (active && (active.tagName === 'INPUT' || active.tagName === 'TEXTAREA')) return
    e.preventDefault()
    fileStore.selectAll()
    multiSelectMode.value = true
  }
}

// ─── 多选模式 ────────────────────────────────────────────────
// 点击选择框 / Ctrl+点击 / Shift+点击 / 框选 / Ctrl+A 时激活
// 普通单击卡片时不激活（选择框不高亮）
const multiSelectMode = ref(false)

// ─── 框选（lasso）────────────────────────────────────────────
interface LassoState { active: boolean; x0: number; y0: number; x1: number; y1: number }
const lasso = ref<LassoState>({ active: false, x0: 0, y0: 0, x1: 0, y1: 0 })

const lassoStyle = computed(() => {
  const { x0, y0, x1, y1 } = lasso.value
  const l = Math.min(x0, x1), t = Math.min(y0, y1)
  const w = Math.abs(x1 - x0), h = Math.abs(y1 - y0)
  return { left: `${l}px`, top: `${t}px`, width: `${w}px`, height: `${h}px` }
})

function handleGridMouseDown(e: MouseEvent) {
  // 只响应左键在空白处的拖拽（不是在卡片上）
  if (e.button !== 0) return
  const target = e.target as HTMLElement
  if (target.closest('.file-card') || target.closest('.select-checkbox')) return
  // 点击/拖动滚动条时不触发框选、也不清除已有多选：滚动条落在虚拟滚动器
  // 内容区（clientWidth/clientHeight，不含滚动条）之外，据此识别并跳过。
  const scroller = target.closest<HTMLElement>('.vue-recycle-scroller')
  if (scroller) {
    const sr = scroller.getBoundingClientRect()
    const onVScrollbar = e.clientX >= sr.left + scroller.clientWidth
    const onHScrollbar = e.clientY >= sr.top + scroller.clientHeight
    if (onVScrollbar || onHScrollbar) return
  }
  if (fileStore.viewMode !== 'grid') return

  const container = scrollerRef.value
  if (!container) return

  // 阻止浏览器在 mousedown 上开启文本选择，避免框选时连带选中页面文字
  e.preventDefault()

  const rect = container.getBoundingClientRect()
  // 框选起点以容器左上角为原点（.scroller-container 自身不滚动，滚动发生在内部
  // 的虚拟滚动器；横向亦无滚动条，因此坐标无需叠加 scrollTop）
  const x0 = e.clientX - rect.left
  const y0 = e.clientY - rect.top
  const additive = e.ctrlKey || e.metaKey

  // 清除现有选择（除非按住 Ctrl），并退出多选模式
  if (!additive) {
    fileStore.clearSelection()
    multiSelectMode.value = false
  }

  lasso.value = { active: false, x0, y0, x1: x0, y1: y0 }

  // mousemove 在 window 上监听，仍可能让浏览器尝试选中沿途的文本节点。
  // 给 body 加禁用 user-select 的类，框选结束再移除
  document.body.classList.add('taghive-lasso-active')

  // 命中检测：以鼠标视口坐标（clientX/clientY）为右下角，遍历所有 grid-cell
  // 判断是否与框选矩形相交。抽成独立函数，move 与 up 均调用一次，
  // 确保鼠标松开的最终位置（尤其是快速甩到最右列时）一定被纳入判定。
  const applyHitTest = (clientX: number, clientY: number) => {
    const lx0 = Math.min(e.clientX, clientX)
    const ly0 = Math.min(e.clientY, clientY)
    const lx1 = Math.max(e.clientX, clientX)
    const ly1 = Math.max(e.clientY, clientY)

    const cells = container.querySelectorAll<HTMLElement>('.grid-cell')
    cells.forEach(cell => {
      const cr = cell.getBoundingClientRect()
      const hit = cr.left < lx1 && cr.right > lx0 && cr.top < ly1 && cr.bottom > ly0
      const id = parseInt(cell.dataset.fileId!)
      if (!isNaN(id)) {
        if (hit) fileStore.selectedIds.add(id)
        else if (!additive) fileStore.selectedIds.delete(id)
      }
    })
  }

  const onMove = (ev: MouseEvent) => {
    const x1 = ev.clientX - rect.left
    const y1 = ev.clientY - rect.top
    const moved = Math.abs(x1 - x0) > 4 || Math.abs(y1 - y0) > 4
    lasso.value = { active: moved, x0, y0, x1, y1 }

    if (!moved) return
    applyHitTest(ev.clientX, ev.clientY)
  }

  const onUp = (ev: MouseEvent) => {
    // 若已进入拖拽框选，用松开位置再做一次命中检测，补齐最后一次 mousemove
    // 未覆盖到的区域（快速拖拽时 mouseup 常落在最后一次 move 之外）
    if (lasso.value.active) {
      applyHitTest(ev.clientX, ev.clientY)
    }
    // 框选结束后，若选中了文件则进入多选模式
    if (lasso.value.active && fileStore.selectedIds.size > 0) {
      multiSelectMode.value = true
    }
    lasso.value.active = false
    document.body.classList.remove('taghive-lasso-active')
    window.removeEventListener('mousemove', onMove)
    window.removeEventListener('mouseup', onUp)
  }

  window.addEventListener('mousemove', onMove)
  window.addEventListener('mouseup', onUp)
}

async function handleFileDblClick(file: FileSummary) {
  // 打开文件
  try {
    await open(file.path)
  } catch (error) {
    console.error('Failed to open file:', error)
  }
}

// 处理文件夹选择
// 全局视图多工作区树：记录当前激活的工作区（高亮用）
const activeMultiTreeWorkspace = ref<string>('')

async function handleFolderSelect(folderPath: string, _wsPath?: string) {
  // 记录选中的工作区（用于高亮）
  for (const ws of appStore.workspaces) {
    const normalized = ws.replace(/\\/g, '/')
    if (folderPath.replace(/\\/g, '/').startsWith(normalized)) {
      activeMultiTreeWorkspace.value = ws
      break
    }
  }
  // 记住该工作区当前浏览到的层级，供切换工作区后恢复
  const ownerWs = _wsPath || findOwnerWorkspace(folderPath)
  if (ownerWs) fileStore.rememberFolder(ownerWs, folderPath)
  // 切换目录时清除标签过滤，避免状态不一致
  tagStore.clearSelection()
  await fileStore.loadFolderContents(folderPath)
}

// 根据文件夹路径反查所属工作区根
function findOwnerWorkspace(folderPath: string): string | undefined {
  const target = folderPath.replace(/\\/g, '/')
  // 取最长匹配前缀，避免嵌套工作区误判
  let best: string | undefined
  for (const ws of appStore.workspaces) {
    const normalized = ws.replace(/\\/g, '/')
    if (target === normalized || target.startsWith(normalized + '/')) {
      if (!best || normalized.length > best.replace(/\\/g, '/').length) best = ws
    }
  }
  return best
}

function handleSwitchWorkspaceFromTree(wsPath: string) {
  // 全局视图中点击工作区节点 → 切换到该工作区标签页
  appStore.switchWorkspace(wsPath)
  tagStore.loadTags(wsPath)
  tagStore.clearSelection()
  fileStore.search({ root: wsPath })
}

// 文件夹树右键「移动/复制到...」：打开目录选择对话框（文件夹来源）
function handleFolderOp(payload: { mode: 'move' | 'copy'; path: string; wsPath: string }) {
  openFolderOpDialog(payload.mode, payload.path, payload.wsPath)
}

// ─── 拖拽移动/复制 ────────────────────────────────────────────
// 文件卡片/列表项开始拖拽：写入选中文件 ids（拖的项不在选中集时仅含自身）
function handleFileDragStart(file: FileSummary, event: DragEvent) {
  const fileIds = fileStore.selectedIds.has(file.id)
    ? Array.from(fileStore.selectedIds)
    : [file.id]
  setItemDragData(event, {
    kind: 'file',
    fileIds,
    label: fileIds.length > 1 ? `${fileIds.length} 个文件` : file.name,
  })
}

function handleItemDragEnd() {
  clearItemDragState()
}

// 拖拽放置到文件夹树节点：执行移动/复制（Ctrl=复制）
async function handleTreeItemDrop(payload: { targetPath: string; targetWs: string; copy: boolean }) {
  const drag = getItemDrag()
  clearItemDragState()
  if (!drag) return
  const { targetPath, targetWs, copy } = payload
  try {
    if (drag.kind === 'file' && drag.fileIds?.length) {
      if (copy) {
        const r = await fileApi.copy(drag.fileIds, targetPath, targetWs)
        ElMessage.success(`已复制 ${r.files.length} 个文件`)
      } else {
        const r = await fileApi.move(drag.fileIds, targetPath, targetWs)
        ElMessage.success(`已移动 ${r.files.length} 个文件`)
      }
    } else if (drag.kind === 'folder' && drag.folderPath) {
      // 防止把文件夹拖到自身或子目录
      const src = drag.folderPath.replace(/\\/g, '/')
      const dst = targetPath.replace(/\\/g, '/')
      if (dst === src || dst.startsWith(src + '/')) {
        ElMessage.warning('不能移动到文件夹自身或其子目录')
        return
      }
      if (copy) {
        await folderApi.copyFolder(drag.folderPath, targetPath)
        ElMessage.success('已复制文件夹')
      } else {
        await folderApi.moveFolder(drag.folderPath, targetPath, targetWs)
        ElMessage.success('已移动文件夹')
      }
    }
    await refreshFileList()
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || (copy ? '复制失败' : '移动失败'))
  }
}

// ===== 文件右键菜单 =====

function handleFileContextMenu(file: FileSummary, event: MouseEvent) {
  // 关闭其他面板的右键菜单
  window.dispatchEvent(new Event('close-context-menus'))
  // 若右键文件不在选中集合，先单选该文件
  if (!fileStore.selectedIds.has(file.id)) {
    fileStore.selectFile(file.id, false)
  }
  contextMenuTargetFile.value = file
  contextMenuTargetIds.value = Array.from(fileStore.selectedIds)
  fileContextMenuAnchor.style.left = `${event.clientX}px`
  fileContextMenuAnchor.style.top = `${event.clientY}px`
  fileContextMenuTrigger.value = fileContextMenuAnchor
  fileContextMenuVisible.value = true
}

function onFileContextMenuVisibleChange(val: boolean) {
  if (!val) fileContextMenuVisible.value = false
}

function closeFileContextMenu() {
  fileContextMenuVisible.value = false
}

function openRenameDialog() {
  fileContextMenuVisible.value = false
  const file = contextMenuTargetFile.value
  if (!file) return
  renameNewName.value = file.name
  showRenameDialog.value = true
}

async function confirmRename() {
  const file = contextMenuTargetFile.value
  if (!file || !renameNewName.value.trim()) return
  renameSubmitting.value = true
  try {
    await fileApi.rename(file.id, renameNewName.value.trim())
    showRenameDialog.value = false
    ElMessage.success('重命名成功')
    await refreshFileList()
  } catch (error: any) {
    const msg = error?.response?.data?.detail || '重命名失败'
    ElMessage.error(msg)
  } finally {
    renameSubmitting.value = false
  }
}

async function openMoveDialog() {
  fileContextMenuVisible.value = false
  fileOpMode.value = 'move'
  fileOpFolderSource.value = null
  fileOpTargetWorkspace.value = appStore.currentWorkspace || appStore.workspaces[0] || ''
  fileOpTargetDir.value = currentImportDirectory.value || fileOpTargetWorkspace.value
  showFileOpCreateFolder.value = false
  fileOpNewFolderName.value = ''
  showFileOpDialog.value = true
  await loadFileOpFolderTree()
}

async function openCopyDialog() {
  fileContextMenuVisible.value = false
  fileOpMode.value = 'copy'
  fileOpFolderSource.value = null
  fileOpTargetWorkspace.value = appStore.currentWorkspace || appStore.workspaces[0] || ''
  fileOpTargetDir.value = currentImportDirectory.value || fileOpTargetWorkspace.value
  showFileOpCreateFolder.value = false
  fileOpNewFolderName.value = ''
  showFileOpDialog.value = true
  await loadFileOpFolderTree()
}

// 打开文件夹移动/复制对话框（由文件夹树右键菜单触发）
async function openFolderOpDialog(mode: 'move' | 'copy', folderPath: string, sourceWs: string) {
  fileOpMode.value = mode
  fileOpFolderSource.value = folderPath
  fileOpFolderSourceWs.value = sourceWs
  // 默认目标工作区优先选「非来源工作区」的首个，便于跨工作区操作
  const otherWs = appStore.workspaces.find(ws => ws !== sourceWs)
  fileOpTargetWorkspace.value = otherWs || sourceWs || appStore.workspaces[0] || ''
  // 目标目录走该工作区的浏览记忆
  fileOpTargetDir.value = resolveDefaultTargetDir(fileOpTargetWorkspace.value)
  showFileOpCreateFolder.value = false
  fileOpNewFolderName.value = ''
  showFileOpDialog.value = true
  await loadFileOpFolderTree()
}

// 计算某工作区在对话框中的默认目标目录：优先上次浏览层级，否则工作区根
function resolveDefaultTargetDir(workspace: string): string {
  if (!workspace) return ''
  const remembered = fileStore.getRememberedFolder(workspace)
  if (remembered && findOwnerWorkspace(remembered) === workspace) {
    return remembered
  }
  return workspace
}

async function loadFileOpFolderTree() {
  const ws = fileOpTargetWorkspace.value
  if (!ws) return
  fileOpTreeLoading.value = true
  try {
    const result = await folderApi.getTree(ws)
    fileOpFolderTree.value = result.folders
  } catch {
    ElMessage.error('加载目录失败')
    fileOpFolderTree.value = []
  } finally {
    fileOpTreeLoading.value = false
    await nextTick()
    if (fileOpTargetDir.value) {
      fileOpTreeRef.value?.setCurrentKey(fileOpTargetDir.value)
    }
  }
}

async function handleFileOpWorkspaceChange(workspace: string) {
  fileOpTargetWorkspace.value = workspace
  // 切换工作区后，目标目录默认回到该工作区上次浏览的层级（无记忆则工作区根）
  fileOpTargetDir.value = resolveDefaultTargetDir(workspace)
  showFileOpCreateFolder.value = false
  fileOpNewFolderName.value = ''
  await loadFileOpFolderTree()
}

function handleFileOpTargetSelect(node: FolderNode) {
  fileOpTargetDir.value = node.path
}

function toggleFileOpCreateFolder() {
  showFileOpCreateFolder.value = !showFileOpCreateFolder.value
  if (!showFileOpCreateFolder.value) fileOpNewFolderName.value = ''
}

async function createFolderInFileOpDialog() {
  const ws = fileOpTargetWorkspace.value
  const parentPath = fileOpTargetDir.value || ws
  const folderName = fileOpNewFolderName.value.trim()
  if (!ws || !parentPath || !folderName) return
  fileOpCreatingFolder.value = true
  try {
    let createdPath = ''
    try {
      const result = await folderApi.createFolder(ws, parentPath, folderName)
      createdPath = result.path
    } catch (error: any) {
      if (error?.response?.status !== 404) throw error
      const targetPath = `${parentPath.replace(/[\/\\]+$/, '')}/${folderName}`
      await invoke('create_folder', { path: targetPath })
      createdPath = targetPath.replace(/\\/g, '/')
    }
    await loadFileOpFolderTree()
    fileOpTargetDir.value = createdPath
    fileOpTreeRef.value?.setCurrentKey(createdPath)
    fileOpNewFolderName.value = ''
    showFileOpCreateFolder.value = false
    ElMessage.success(`已创建目录：${folderName}`)
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || '创建目录失败')
  } finally {
    fileOpCreatingFolder.value = false
  }
}

async function confirmFileOp() {
  // 文件夹来源：校验目标目录；文件来源：校验目标目录 + 选中文件
  if (!fileOpTargetDir.value) return
  if (!fileOpFolderSource.value && !contextMenuTargetIds.value.length) return
  const targetWs = fileOpTargetWorkspace.value || undefined
  fileOpSubmitting.value = true
  try {
    if (fileOpFolderSource.value) {
      // 文件夹整体移动/复制
      if (fileOpMode.value === 'move') {
        await folderApi.moveFolder(fileOpFolderSource.value, fileOpTargetDir.value, targetWs)
        ElMessage.success('已移动文件夹')
      } else {
        await folderApi.copyFolder(fileOpFolderSource.value, fileOpTargetDir.value)
        ElMessage.success('已复制文件夹')
      }
    } else if (fileOpMode.value === 'move') {
      const result = await fileApi.move(contextMenuTargetIds.value, fileOpTargetDir.value, targetWs)
      ElMessage.success(`已移动 ${result.files.length} 个文件`)
    } else {
      const result = await fileApi.copy(contextMenuTargetIds.value, fileOpTargetDir.value, targetWs)
      ElMessage.success(`已复制 ${result.files.length} 个文件`)
    }
    showFileOpDialog.value = false
    await refreshFileList()
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || `${fileOpMode.value === 'move' ? '移动' : '复制'}失败`)
  } finally {
    fileOpSubmitting.value = false
  }
}

async function showInExplorer() {
  fileContextMenuVisible.value = false
  const file = contextMenuTargetFile.value
  if (!file) return
  try {
    const folder = file.path.replace(/[/\\][^/\\]+$/, '')
    await invoke('open_folder', { path: folder, filePath: file.path })
  } catch {
    ElMessage.error('无法打开资源管理器')
  }
}

async function deleteContextMenuFiles() {
  fileContextMenuVisible.value = false
  const ids = contextMenuTargetIds.value
  if (!ids.length) return
  try {
    await ElMessageBox.confirm(
      `确定要删除选中的 ${ids.length} 个文件吗？文件将被移入回收站。`,
      '删除确认',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }
    )
  } catch {
    return
  }
  try {
    for (const id of ids) {
      await fileApi.delete(id)
    }
    ElMessage.success(`已删除 ${ids.length} 个文件`)
    fileStore.clearSelection()
    await refreshFileList()
  } catch {
    ElMessage.error('删除失败')
  }
}

async function refreshFileList() {
  // 处于标签过滤态时：保留过滤条件，按当前 searchQuery 重跑搜索；
  // 不能走 loadFolderContents（按目录直查、不带 tag 过滤）也不能传 { root } 重置 query。
  if (tagStore.hasSelection) {
    await fileStore.search({
      ...fileStore.searchQuery,
      tags: Array.from(tagStore.effectiveTagIds),
      match_all_tags: false,
    })
    return
  }
  if ((fileStore.browseMode === 'folder' || fileStore.browseMode === 'tree') && fileStore.currentFolderPath) {
    await fileStore.loadFolderContents(fileStore.currentFolderPath)
  } else {
    await fileStore.search({ root: appStore.currentWorkspace || undefined })
  }
}

function clearDropIndicators() {
  activeDropFileId.value = null
  dragTagMeta.value = null
  externalDropActive.value = false
}

function handleFileDragOver(fileId: number, event: DragEvent) {
  if (!isTagDragInProgress() && !hasTagDrag(event)) {
    return
  }

  activeDropFileId.value = fileId
  dragTagMeta.value = getDragMeta()
  if (event.dataTransfer) {
    event.dataTransfer.dropEffect = 'copy'
  }
}

function handleFileDragLeave(fileId: number) {
  if (activeDropFileId.value === fileId) {
    activeDropFileId.value = null
  }
}

async function handleFileDrop(file: FileSummary, event: DragEvent) {
  const draggedTagId = getDraggedTagId(event)
  if (draggedTagId === null) {
    return
  }

  const targetFileIds = fileStore.selectedIds.has(file.id)
    ? Array.from(fileStore.selectedIds)
    : [file.id]

  try {
    await tagStore.assignTagsToFiles(targetFileIds, [draggedTagId])
    const tag = tagStore.getTagById(draggedTagId)
    ElMessage.success(
      targetFileIds.length > 1
        ? `已为 ${targetFileIds.length} 个文件添加标签「${tag?.name || '未命名标签'}」`
        : `已为文件添加标签「${tag?.name || '未命名标签'}」`
    )
  } catch (error) {
    console.error('Failed to drop tag onto file:', error)
    ElMessage.error('拖拽标签到文件失败')
  } finally {
    clearDropIndicators()
    clearTagDragState()
  }
}

function handleExternalDragEnter(event: DragEvent) {
  if (isTagDragInProgress() || hasTagDrag(event)) {
    // 标签拖拽进入：设置允许拖放，避免禁止图标
    if (event.dataTransfer) {
      event.dataTransfer.dropEffect = 'copy'
    }
    return
  }

  if (hasExternalFiles(event)) {
    externalDropActive.value = true
  }
}

function handleExternalDragOver(event: DragEvent) {
  if (isTagDragInProgress() || hasTagDrag(event)) {
    // 标签拖拽经过：设置允许拖放，避免禁止图标
    if (event.dataTransfer) {
      event.dataTransfer.dropEffect = 'copy'
    }
    return
  }

  if (hasExternalFiles(event)) {
    externalDropActive.value = true
    if (event.dataTransfer) {
      event.dataTransfer.dropEffect = currentImportDirectory.value ? 'move' : 'none'
    }
  }
}

function handleExternalDragLeave(event: DragEvent) {
  if (event.currentTarget === event.target) {
    externalDropActive.value = false
  }
}

async function handleExternalDrop(event: DragEvent) {
  if (isTagDragInProgress() || hasTagDrag(event)) {
    clearDropIndicators()
    return
  }

  const paths = normalizeDroppedPaths(getDroppedFilePaths(event))
  externalDropActive.value = false

  if (!paths.length) {
    return
  }

  await promptImportTarget(paths)
}
</script>

<style scoped>
.browser-view {
  height: 100%;
  overflow: hidden;
  position: relative;
}

.browser-view.external-drop-active::after {
  content: '拖入文件后选择要移动到的目录';
  position: absolute;
  inset: 16px;
  border: 2px dashed var(--color-accent);
  border-radius: 12px;
  background: color-mix(in srgb, var(--color-accent-light) 38%, transparent);
  color: var(--color-accent);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  font-weight: 600;
  pointer-events: none;
  z-index: 10;
}

.empty-state {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
}

.scroller-container {
  height: 100%;
  width: 100%;
  position: relative;
}

.scroller {
  height: 100%;
}

/* vue-virtual-scroller 的 __item-wrapper 默认 overflow: hidden（库内置硬编码），
   item-view 又是 absolute 定位，无法靠 wrapper padding 让上浮的 hover 效果露出。
   实际生效方案是在 grid-row 内部留出垂直 padding，
   让卡片 hover 时 translateY(-4px) scale(1.04) 仍在 row 高度内。 */

/* 确保 RecycleScroller 的 item view 占满宽度 */
.grid-view :deep(.vue-recycle-scroller__item-view) {
  width: 100% !important;
  position: absolute !important;
  left: 0 !important;
}

/* 框选遮罩 */
.lasso-rect {
  position: absolute;
  border: 1px solid var(--color-accent);
  background: color-mix(in srgb, var(--color-accent) 12%, transparent);
  pointer-events: none;
  z-index: 10;
  border-radius: 3px;
}

/* Grid 行容器 */
.browser-view :deep(.grid-row) {
  box-sizing: border-box;
  align-items: flex-start;
}

/* Grid 单元格 */
.browser-view :deep(.grid-cell) {
  box-sizing: border-box;
  position: relative;
}

.browser-view :deep(.list-drop-target) {
  position: relative;
  transition: background-color 0.2s ease, box-shadow 0.2s ease;
}

.browser-view :deep(.grid-cell.file-drop-active),
.browser-view :deep(.list-drop-target.file-drop-active) {
  border-radius: 14px;
  box-shadow:
    inset 0 0 0 2px var(--tag-color, var(--color-accent)),
    0 0 0 4px color-mix(in srgb, var(--tag-color, var(--color-accent)) 18%, transparent),
    0 6px 24px color-mix(in srgb, var(--tag-color, var(--color-accent)) 28%, transparent);
  background: color-mix(in srgb, var(--tag-color, var(--color-accent)) 12%, transparent);
  animation: file-drop-pulse 0.9s ease-in-out infinite alternate;
  transition: box-shadow 0.18s ease, background-color 0.18s ease;
}

/* 命中状态下放大文件卡片，配合徽章营造"被吸附"的感觉 */
.browser-view :deep(.grid-cell.file-drop-active .file-card) {
  transform: translateY(-4px) scale(1.04);
  border-color: var(--tag-color, var(--color-accent));
  box-shadow:
    0 12px 28px color-mix(in srgb, var(--tag-color, var(--color-accent)) 28%, transparent),
    0 0 0 1px color-mix(in srgb, var(--tag-color, var(--color-accent)) 35%, transparent);
}

.browser-view :deep(.tag-drop-badge) {
  position: absolute;
  bottom: 56px;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 12px 5px 8px;
  border-radius: 999px;
  background: var(--tag-color, #409EFF);
  color: #fff;
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
  pointer-events: none;
  box-shadow:
    0 4px 14px color-mix(in srgb, var(--tag-color, #409EFF) 45%, transparent),
    0 1px 0 rgba(255, 255, 255, 0.3) inset;
  border: 1px solid color-mix(in srgb, #ffffff 40%, transparent);
  animation: tag-badge-appear 0.22s cubic-bezier(0.34, 1.56, 0.64, 1) both;
  z-index: 10;
}

.browser-view :deep(.tag-drop-badge--list) {
  bottom: auto;
  top: 50%;
  left: auto;
  right: 16px;
  transform: translateY(-50%);
  animation-name: tag-badge-appear-list;
}

.browser-view :deep(.tag-drop-badge-plus) {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.92);
  color: var(--tag-color, #409EFF);
  font-size: 13px;
  font-weight: 800;
  line-height: 1;
}

.browser-view :deep(.tag-drop-badge-icon) {
  font-size: 14px;
  line-height: 1;
}

.browser-view :deep(.tag-drop-badge-dot) {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: rgba(255,255,255,0.85);
  flex-shrink: 0;
}

.browser-view :deep(.tag-drop-badge-name) {
  max-width: 100px;
  overflow: hidden;
  text-overflow: ellipsis;
}

@keyframes tag-badge-appear {
  from {
    opacity: 0;
    transform: translateX(-50%) translateY(6px) scale(0.7);
  }
  to {
    opacity: 1;
    transform: translateX(-50%) translateY(0) scale(1);
  }
}

@keyframes tag-badge-appear-list {
  from {
    opacity: 0;
    transform: translateY(-50%) translateX(8px) scale(0.7);
  }
  to {
    opacity: 1;
    transform: translateY(-50%) translateX(0) scale(1);
  }
}

@keyframes file-drop-pulse {
  from {
    box-shadow:
      inset 0 0 0 2px color-mix(in srgb, var(--tag-color, var(--color-accent)) 60%, transparent),
      0 0 0 4px color-mix(in srgb, var(--tag-color, var(--color-accent)) 14%, transparent),
      0 4px 18px color-mix(in srgb, var(--tag-color, var(--color-accent)) 22%, transparent);
  }
  to {
    box-shadow:
      inset 0 0 0 2px var(--tag-color, var(--color-accent)),
      0 0 0 6px color-mix(in srgb, var(--tag-color, var(--color-accent)) 22%, transparent),
      0 8px 26px color-mix(in srgb, var(--tag-color, var(--color-accent)) 36%, transparent);
  }
}

.list-view {
  padding: 8px 0;
}

.load-more {
  padding: 16px;
  text-align: center;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: var(--color-text-secondary);
  font-size: 14px;
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

/* 树形视图样式 */
.tree-view-container {
  position: relative;
  height: 100%;
  overflow: hidden;
}

.folder-tree-panel {
  width: 280px;
  flex-shrink: 0;
  border-right: 1px solid var(--color-border);
  background: var(--color-bg-secondary);
  overflow-y: auto;
}

/* 全局视图：多工作区并列树面板 */
.folder-tree-panel--multi {
  width: 320px;
  display: flex;
  flex-direction: column;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 0;
}

.multi-workspace-tree {
  border-bottom: 1px solid var(--color-border);
  flex-shrink: 0;
}

.multi-workspace-tree--active > .multi-workspace-label {
  color: var(--color-accent);
}

.multi-workspace-label {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  font-size: 12px;
  font-weight: 600;
  color: var(--color-text-secondary);
  background: var(--color-bg-tertiary);
  border-bottom: 1px solid var(--color-border);
  letter-spacing: 0.02em;
  text-transform: uppercase;
  position: sticky;
  top: 0;
  z-index: 1;
  user-select: none;
}

.multi-workspace-label span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tree-view-container .scroller-container {
  width: 100%;
  height: 100%;
}

.import-dialog-body {
  display: flex;
  flex-direction: column;
  gap: 16px;
  flex: 1 1 auto;
  min-height: 0;
  overflow: hidden;
}

.import-dialog-hero {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  padding: 16px 18px;
  border-radius: 16px;
  background: linear-gradient(135deg, color-mix(in srgb, var(--color-accent-light) 50%, transparent), var(--color-bg-secondary));
  border: 1px solid color-mix(in srgb, var(--color-accent) 18%, transparent);
}

.import-dialog-title-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 6px;
}

.import-dialog-title {
  font-size: 16px;
  font-weight: 700;
  color: var(--color-text-primary);
}

.import-dialog-count {
  padding: 2px 10px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--color-accent) 14%, transparent);
  color: var(--color-accent);
  font-size: 12px;
  font-weight: 600;
}

.import-dialog-description {
  margin: 0;
  color: var(--color-text-secondary);
  line-height: 1.6;
}

.import-dialog-workspace {
  min-width: 150px;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  justify-content: center;
  gap: 4px;
  word-break: break-all;
}

.import-dialog-workspace-select {
  min-width: 220px;
}

.import-dialog-workspace-select :deep(.el-select) {
  width: 100%;
}

.workspace-option-name {
  font-weight: 500;
  margin-right: 8px;
}

.workspace-option-path {
  font-size: 12px;
  color: var(--color-text-secondary);
}

.workspace-label,
.summary-label,
.import-tree-tip {
  font-size: 12px;
  color: var(--color-text-secondary);
}

.import-target-summary-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 16px;
  border-radius: 14px;
  border: 1px solid var(--color-border);
  background: var(--color-bg-secondary);
}

.summary-main {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.summary-path {
  font-size: 12px;
  color: var(--color-text-secondary);
  word-break: break-all;
}

.summary-actions {
  flex-shrink: 0;
}

.create-folder-panel {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 14px 16px;
  border-radius: 14px;
  background: color-mix(in srgb, var(--color-bg-secondary) 88%, transparent);
  border: 1px dashed color-mix(in srgb, var(--color-accent) 25%, transparent);
}

.create-folder-info {
  font-size: 13px;
  color: var(--color-text-secondary);
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.create-folder-form {
  display: flex;
  gap: 10px;
}

.import-tree-panel {
  border: 1px solid var(--color-border);
  border-radius: 16px;
  overflow: hidden;
  background: var(--color-bg-primary);
  /* flex-basis 表示首选高度（弹窗够大时占 500px），同时允许在空间不足时收缩；
     min-height 必须显式归零以覆盖 flex 默认的「不小于内容」下限。 */
  flex: 1 1 500px;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.import-tree-panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--color-border);
  background: color-mix(in srgb, var(--color-bg-secondary) 90%, transparent);
  flex-shrink: 0;
}

.import-dialog-loading {
  min-height: 180px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: var(--color-text-secondary);
  padding: 24px;
}

.import-tree-node {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  width: 100%;
  min-width: 0;
  padding: 6px 0;
}

.import-tree-main {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.import-tree-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text-primary);
}

.import-tree-meta {
  font-size: 11px;
  color: var(--color-text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.import-tree-badge {
  flex-shrink: 0;
  font-size: 11px;
  color: var(--color-text-secondary);
  padding: 2px 8px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--color-accent-light) 35%, transparent);
}

.import-tree-panel :deep(.el-tree) {
  padding: 8px 10px 14px;
  flex: 1 1 auto;
  min-height: 0;
  overflow: auto;
}

.import-tree-panel > .import-dialog-loading,
.import-tree-panel > .el-empty {
  flex: 1 1 auto;
  min-height: 0;
  overflow: auto;
}

.import-tree-panel :deep(.el-tree-node__content) {
  height: auto;
  min-height: 40px;
  border-radius: 10px;
  padding-right: 8px;
}

.import-tree-panel :deep(.el-tree--highlight-current .el-tree-node.is-current > .el-tree-node__content) {
  background: color-mix(in srgb, var(--color-accent-light) 42%, transparent);
}

.import-tree-panel :deep(.el-tree-node__content:hover) {
  background: color-mix(in srgb, var(--color-bg-secondary) 92%, transparent);
}

/* 响应式：小屏幕时调整文件夹树宽度 */
@media (max-width: 768px) {
  .folder-tree-panel {
    width: 200px;
  }

  .import-dialog-hero,
  .import-target-summary-card,
  .import-tree-panel-header,
  .create-folder-form {
    flex-direction: column;
    align-items: stretch;
  }

  .import-dialog-workspace {
    align-items: flex-start;
  }
}

@media (max-width: 480px) {
  .folder-tree-panel {
    width: 160px;
  }

  .folder-tree-panel--multi {
    width: 200px;
  }
}

.context-menu {
  padding: 4px 0;
}

.context-menu-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  cursor: pointer;
  font-size: 13px;
  border-radius: 6px;
  transition: background-color 0.15s;
}

.context-menu-item:hover:not(.disabled) {
  background-color: var(--color-bg-secondary);
}

.context-menu-item.disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.context-menu-item.delete {
  color: var(--color-danger);
}

.context-menu-item.delete:hover {
  background-color: var(--color-danger-light);
}

.context-menu-divider {
  height: 1px;
  background-color: var(--color-border);
  margin: 4px 0;
}
</style>

<!-- 非 scoped 块：el-dialog 通过 teleport 渲染到组件根之外，scoped attr 无法透传，
     需要全局选择器才能限制其整体高度并让仅目录树内部滚动。 -->
<style>
.import-target-dialog {
  display: flex;
  flex-direction: column;
  max-height: calc(100vh - 80px);
  margin-top: 40px !important;
  margin-bottom: 40px !important;
}

.import-target-dialog .el-dialog__body {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  padding-top: 12px;
  padding-bottom: 12px;
}

.import-target-dialog .el-dialog__header,
.import-target-dialog .el-dialog__footer {
  flex-shrink: 0;
}
</style>
