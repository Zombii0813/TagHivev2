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
        />

        <!-- 文件列表全宽 -->
        <div ref="scrollerRef" class="scroller-container">
          <!-- Grid 模式 -->
          <RecycleScroller
            v-if="fileStore.viewMode === 'grid'"
            class="scroller grid-view"
            :items="gridRows"
            :item-size="gridItemHeight"
            key-field="rowIndex"
            v-slot="{ item: row }"
          >
            <div class="grid-row" :style="gridRowStyle">
              <div
                v-for="file in row.files"
                :key="file.id"
                class="grid-cell"
                :class="{ 'file-drop-active': activeDropFileId === file.id }"
                :style="gridCellStyle"
                @dragover.prevent.stop="handleFileDragOver(file.id, $event)"
                @dragleave="handleFileDragLeave(file.id)"
                @drop.prevent.stop="handleFileDrop(file, $event)"
              >
                <FileCard
                  :file="file"
                  :selected="fileStore.selectedIds.has(file.id)"
                  :size="gridItemWidth"
                  @click="handleFileClick(file.id, $event)"
                  @dblclick="handleFileDblClick(file)"
                  @contextmenu.prevent="handleFileContextMenu(file, $event)"
                />
                <div
                  v-if="activeDropFileId === file.id && dragTagMeta"
                  class="tag-drop-badge"
                  :style="{ '--tag-color': dragTagMeta.color || '#409EFF' }"
                >
                  <span v-if="dragTagMeta.icon" class="tag-drop-badge-icon">{{ dragTagMeta.icon }}</span>
                  <span v-else class="tag-drop-badge-dot"></span>
                  <span class="tag-drop-badge-name">{{ dragTagMeta.name }}</span>
                </div>
              </div>
            </div>
          </RecycleScroller>

          <!-- List 模式 -->
          <RecycleScroller
            v-else
            class="scroller list-view"
            :items="fileStore.files"
            :item-size="60"
            key-field="id"
            v-slot="{ item }"
          >
            <div
              class="list-drop-target"
              :class="{ 'file-drop-active': activeDropFileId === item.id }"
              @dragover.prevent.stop="handleFileDragOver(item.id, $event)"
              @dragleave="handleFileDragLeave(item.id)"
              @drop.prevent.stop="handleFileDrop(item, $event)"
            >
              <FileListItem
                ref="fileListItemRefs"
                :file="item"
                :selected="fileStore.selectedIds.has(item.id)"
                @click="handleFileClick(item.id, $event)"
                @dblclick="handleFileDblClick(item)"
                @contextmenu.prevent="handleFileContextMenu(item, $event)"
              />
              <div
                v-if="activeDropFileId === item.id && dragTagMeta"
                class="tag-drop-badge"
                :style="{ '--tag-color': dragTagMeta.color || '#409EFF' }"
              >
                <span v-if="dragTagMeta.icon" class="tag-drop-badge-icon">{{ dragTagMeta.icon }}</span>
                <span v-else class="tag-drop-badge-dot"></span>
                <span class="tag-drop-badge-name">{{ dragTagMeta.name }}</span>
              </div>
            </div>
          </RecycleScroller>

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
        />

        <!-- 文件列表全宽 -->
        <div ref="scrollerRef" class="scroller-container">
          <!-- Grid 模式 -->
          <RecycleScroller
            v-if="fileStore.viewMode === 'grid'"
            class="scroller grid-view"
            :items="gridRows"
            :item-size="gridItemHeight"
            key-field="rowIndex"
            v-slot="{ item: row }"
          >
            <div class="grid-row" :style="gridRowStyle">
              <div
                v-for="file in row.files"
                :key="file.id"
                class="grid-cell"
                :class="{ 'file-drop-active': activeDropFileId === file.id }"
                :style="gridCellStyle"
                @dragover.prevent.stop="handleFileDragOver(file.id, $event)"
                @dragleave="handleFileDragLeave(file.id)"
                @drop.prevent.stop="handleFileDrop(file, $event)"
              >
                <FileCard
                  :file="file"
                  :selected="fileStore.selectedIds.has(file.id)"
                  :size="gridItemWidth"
                  @click="handleFileClick(file.id, $event)"
                  @dblclick="handleFileDblClick(file)"
                  @contextmenu.prevent="handleFileContextMenu(file, $event)"
                />
                <div
                  v-if="activeDropFileId === file.id && dragTagMeta"
                  class="tag-drop-badge"
                  :style="{ '--tag-color': dragTagMeta.color || '#409EFF' }"
                >
                  <span v-if="dragTagMeta.icon" class="tag-drop-badge-icon">{{ dragTagMeta.icon }}</span>
                  <span v-else class="tag-drop-badge-dot"></span>
                  <span class="tag-drop-badge-name">{{ dragTagMeta.name }}</span>
                </div>
              </div>
            </div>
          </RecycleScroller>

          <!-- List 模式 -->
          <RecycleScroller
            v-else
            class="scroller list-view"
            :items="fileStore.files"
            :item-size="60"
            key-field="id"
            v-slot="{ item }"
          >
            <div
              class="list-drop-target"
              :class="{ 'file-drop-active': activeDropFileId === item.id }"
              @dragover.prevent.stop="handleFileDragOver(item.id, $event)"
              @dragleave="handleFileDragLeave(item.id)"
              @drop.prevent.stop="handleFileDrop(item, $event)"
            >
              <FileListItem
                ref="fileListItemRefs"
                :file="item"
                :selected="fileStore.selectedIds.has(item.id)"
                @click="handleFileClick(item.id, $event)"
                @dblclick="handleFileDblClick(item)"
                @contextmenu.prevent="handleFileContextMenu(item, $event)"
              />
              <div
                v-if="activeDropFileId === item.id && dragTagMeta"
                class="tag-drop-badge"
                :style="{ '--tag-color': dragTagMeta.color || '#409EFF' }"
              >
                <span v-if="dragTagMeta.icon" class="tag-drop-badge-icon">{{ dragTagMeta.icon }}</span>
                <span v-else class="tag-drop-badge-dot"></span>
                <span class="tag-drop-badge-name">{{ dragTagMeta.name }}</span>
              </div>
            </div>
          </RecycleScroller>

          <!-- 加载更多提示 -->
          <div v-if="fileStore.hasMore && fileStore.isLoading" class="load-more">
            <el-icon class="loading-icon"><Loading /></el-icon>
            <span>加载中...</span>
          </div>
        </div>
      </div>
    </template>

    <!-- 文件列表 -->
    <template v-else>
      <div ref="scrollerRef" class="scroller-container">
        <!-- Grid 模式 - 使用 CSS Grid 布局 -->
        <RecycleScroller
          v-if="fileStore.viewMode === 'grid'"
          class="scroller grid-view"
          :items="gridRows"
          :item-size="gridItemHeight"
          key-field="rowIndex"
          v-slot="{ item: row }"
        >
          <div class="grid-row" :style="gridRowStyle">
            <div
              v-for="file in row.files"
              :key="file.id"
              class="grid-cell"
              :class="{ 'file-drop-active': activeDropFileId === file.id }"
              :style="gridCellStyle"
              @dragover.prevent.stop="handleFileDragOver(file.id, $event)"
              @dragleave="handleFileDragLeave(file.id)"
              @drop.prevent.stop="handleFileDrop(file, $event)"
            >
              <FileCard
                :file="file"
                :selected="fileStore.selectedIds.has(file.id)"
                :size="gridItemWidth"
                @click="handleFileClick(file.id, $event)"
                @dblclick="handleFileDblClick(file)"
                @contextmenu.prevent="handleFileContextMenu(file, $event)"
              />
              <div
                v-if="activeDropFileId === file.id && dragTagMeta"
                class="tag-drop-badge"
                :style="{ '--tag-color': dragTagMeta.color || '#409EFF' }"
              >
                <span v-if="dragTagMeta.icon" class="tag-drop-badge-icon">{{ dragTagMeta.icon }}</span>
                <span v-else class="tag-drop-badge-dot"></span>
                <span class="tag-drop-badge-name">{{ dragTagMeta.name }}</span>
              </div>
            </div>
          </div>
        </RecycleScroller>

        <RecycleScroller
          v-else
          class="scroller list-view"
          :items="fileStore.files"
          :item-size="60"
          key-field="id"
          v-slot="{ item }"
        >
          <div
            class="list-drop-target"
            :class="{ 'file-drop-active': activeDropFileId === item.id }"
            @dragover.prevent.stop="handleFileDragOver(item.id, $event)"
            @dragleave="handleFileDragLeave(item.id)"
            @drop.prevent.stop="handleFileDrop(item, $event)"
          >
            <FileListItem
              ref="fileListItemRefs"
              :file="item"
              :selected="fileStore.selectedIds.has(item.id)"
              @click="handleFileClick(item.id, $event)"
              @dblclick="handleFileDblClick(item)"
              @contextmenu.prevent="handleFileContextMenu(item, $event)"
            />
            <div
              v-if="activeDropFileId === item.id && dragTagMeta"
              class="tag-drop-badge tag-drop-badge--list"
              :style="{ '--tag-color': dragTagMeta.color || '#409EFF' }"
            >
              <span v-if="dragTagMeta.icon" class="tag-drop-badge-icon">{{ dragTagMeta.icon }}</span>
              <span v-else class="tag-drop-badge-dot"></span>
              <span class="tag-drop-badge-name">{{ dragTagMeta.name }}</span>
            </div>
          </div>
        </RecycleScroller>
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
              <span class="import-dialog-title">{{ fileOpMode === 'move' ? '移动文件' : '复制文件' }}</span>
              <span class="import-dialog-count">{{ contextMenuTargetIds.length }} 个文件</span>
            </div>
            <p class="import-dialog-description">
              请选择工作区中的目标目录，确认后会将文件{{ fileOpMode === 'move' ? '移动' : '复制' }}到该位置。
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
            <strong>{{ getFolderDisplayName(fileOpTargetDir || appStore.currentWorkspace || '') || '未选择' }}</strong>
            <span class="summary-path">{{ getRelativeImportPath(fileOpTargetDir || appStore.currentWorkspace || '') }}</span>
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
            <strong>{{ fileOpTargetDir || appStore.currentWorkspace }}</strong>
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
          <el-empty v-else description="当前工作区暂无可选目录" :image-size="80" />
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
import { RecycleScroller } from 'vue-virtual-scroller'
import 'vue-virtual-scroller/dist/vue-virtual-scroller.css'
import { invoke } from '@tauri-apps/api/core'
import { useAppStore } from '../stores/app'
import { useFileStore } from '../stores/files'
import { useTagStore } from '../stores/tags'
import FileCard from '../components/FileCard.vue'
import FileListItem from '../components/FileListItem.vue'
import HoneycombTree from '../components/HoneycombTree.vue'
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
import type { TagDragMeta } from '../utils/drag'

// 滚动加载配置
const SCROLL_THRESHOLD = 100 // 距离底部多少像素时触发加载


const appStore = useAppStore()
const fileStore = useFileStore()
const tagStore = useTagStore()

const scrollerRef = ref<HTMLElement | null>(null)
const fileListItemRefs = ref<InstanceType<typeof FileListItem>[]>([])
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
const fileOpTreeLoading = ref(false)
const fileOpSubmitting = ref(false)
const fileOpFolderTree = ref<FolderNode[]>([])
const showFileOpCreateFolder = ref(false)
const fileOpNewFolderName = ref('')
const fileOpCreatingFolder = ref(false)
const fileOpTreeRef = ref<InstanceType<typeof ElTree> | null>(null)

const currentImportDirectory = computed(() => {
  if (fileStore.browseMode === 'folder') {
    return fileStore.currentFolderPath || appStore.currentWorkspace
  }
  return appStore.currentWorkspace
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
  if (!appStore.currentWorkspace) return []
  return [{
    name: getFolderDisplayName(appStore.currentWorkspace),
    path: appStore.currentWorkspace,
    file_count: 0,
    children: fileOpFolderTree.value,
    is_expanded: true,
  }]
})

const fileOpDefaultExpandedKeys = computed(() => {
  const targetPath = fileOpTargetDir.value || appStore.currentWorkspace
  if (!targetPath || !appStore.currentWorkspace) return []
  const rootPath = appStore.currentWorkspace
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
const PADDING = 32 // 左右 padding 总和
const INFO_HEIGHT = 80 // 文件名等信息区域高度（包含标签区域）

// 计算每行显示的列数（根据固定卡片尺寸和容器宽度自动决定列数）
const gridColumns = computed(() => {
  if (containerWidth.value === 0) return 4
  const availableWidth = containerWidth.value - PADDING
  const columns = Math.floor((availableWidth + GAP) / (fileStore.gridItemSize + GAP))
  return Math.max(columns, 1) // 最少显示 1 列
})

// 卡片宽度固定为 gridItemSize
const gridItemWidth = computed(() => fileStore.gridItemSize)

// 计算每个 grid item 的高度
const gridItemHeight = computed(() => {
  return fileStore.gridItemSize + INFO_HEIGHT
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
const gridRowStyle = computed(() => ({
  display: 'flex',
  gap: `${GAP}px`,
  padding: `0 ${PADDING / 2}px`,
  height: `${gridItemHeight.value}px`
}))

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

// 处理滚动事件，实现无限滚动加载
function handleScroll(event: Event) {
  const target = event.target as HTMLElement
  if (!target) return

  const { scrollTop, scrollHeight, clientHeight } = target
  const distanceToBottom = scrollHeight - scrollTop - clientHeight

  // 当距离底部小于阈值时，加载更多
  if (distanceToBottom < SCROLL_THRESHOLD && fileStore.hasMore && !fileStore.isLoading) {
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

function getRelativeImportPath(path: string): string {
  if (!path || !appStore.currentWorkspace) {
    return '未选择目录'
  }

  const normalizedRoot = appStore.currentWorkspace.replace(/\\/g, '/')
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

    if (fileStore.browseMode === 'folder' && fileStore.currentFolderPath) {
      await fileStore.loadFolderContents(fileStore.currentFolderPath)
    } else {
      await fileStore.search({ root: appStore.currentWorkspace || undefined })
    }

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
  
  // 使用 ResizeObserver 监听容器大小变化
  if (scrollerRef.value && typeof ResizeObserver !== 'undefined') {
    resizeObserver = new ResizeObserver(() => {
      updateContainerWidth()
    })
    resizeObserver.observe(scrollerRef.value)
  }
  
  // 添加滚动监听
  if (scrollerRef.value) {
    scrollerRef.value.addEventListener('scroll', handleScroll)
  }
  
  if (appStore.currentWorkspace) {
    fileStore.search({ root: appStore.currentWorkspace })
  }
})

onUnmounted(() => {
  window.removeEventListener('resize', updateContainerWidth)
  window.removeEventListener('close-context-menus', closeFileContextMenu)
  
  // 移除 ResizeObserver
  if (resizeObserver) {
    resizeObserver.disconnect()
    resizeObserver = null
  }
  
  // 移除滚动监听
  if (scrollerRef.value) {
    scrollerRef.value.removeEventListener('scroll', handleScroll)
  }

  if (unlistenNativeDragDrop) {
    unlistenNativeDragDrop()
    unlistenNativeDragDrop = null
  }

  if (lastHandledExternalDropResetTimer) {
    clearTimeout(lastHandledExternalDropResetTimer)
    lastHandledExternalDropResetTimer = null
  }
})

// 监听工作区变化
watch(() => appStore.currentWorkspace, (newPath) => {
  if (newPath) {
    if (fileStore.browseMode === 'folder') {
      // 文件夹浏览模式：加载根目录内容
      fileStore.loadFolderContents(newPath)
    } else {
      // 全部文件模式：搜索所有文件
      fileStore.search({ root: newPath })
    }
  }
})

// 监听浏览模式变化
watch(() => fileStore.browseMode, async (newMode) => {
  if (!appStore.currentWorkspace) return
  
  if (newMode === 'folder') {
    // 切换到文件夹浏览模式：加载根目录内容
    await fileStore.loadFolderContents(appStore.currentWorkspace)
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
    
    // 重新添加滚动监听
    scrollerRef.value.removeEventListener('scroll', handleScroll)
    scrollerRef.value.addEventListener('scroll', handleScroll)
  }
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
        // 扫描完成后刷新文件列表
        fileStore.search({ root: path })
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
    // 范围选择
    const lastSelected = Array.from(fileStore.selectedIds).pop()
    if (lastSelected) {
      fileStore.selectRange(lastSelected, fileId)
    }
  } else {
    fileStore.selectFile(fileId, multi)
  }
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
  await fileStore.loadFolderContents(folderPath)
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
  fileOpTargetDir.value = currentImportDirectory.value || appStore.currentWorkspace || ''
  showFileOpCreateFolder.value = false
  fileOpNewFolderName.value = ''
  showFileOpDialog.value = true
  await loadFileOpFolderTree()
}

async function openCopyDialog() {
  fileContextMenuVisible.value = false
  fileOpMode.value = 'copy'
  fileOpTargetDir.value = currentImportDirectory.value || appStore.currentWorkspace || ''
  showFileOpCreateFolder.value = false
  fileOpNewFolderName.value = ''
  showFileOpDialog.value = true
  await loadFileOpFolderTree()
}

async function loadFileOpFolderTree() {
  if (!appStore.currentWorkspace) return
  fileOpTreeLoading.value = true
  try {
    const result = await folderApi.getTree(appStore.currentWorkspace)
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

function handleFileOpTargetSelect(node: FolderNode) {
  fileOpTargetDir.value = node.path
}

function toggleFileOpCreateFolder() {
  showFileOpCreateFolder.value = !showFileOpCreateFolder.value
  if (!showFileOpCreateFolder.value) fileOpNewFolderName.value = ''
}

async function createFolderInFileOpDialog() {
  const parentPath = fileOpTargetDir.value || appStore.currentWorkspace
  const folderName = fileOpNewFolderName.value.trim()
  if (!appStore.currentWorkspace || !parentPath || !folderName) return
  fileOpCreatingFolder.value = true
  try {
    let createdPath = ''
    try {
      const result = await folderApi.createFolder(appStore.currentWorkspace, parentPath, folderName)
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
  if (!fileOpTargetDir.value || !contextMenuTargetIds.value.length) return
  fileOpSubmitting.value = true
  try {
    if (fileOpMode.value === 'move') {
      const result = await fileApi.move(contextMenuTargetIds.value, fileOpTargetDir.value)
      ElMessage.success(`已移动 ${result.files.length} 个文件`)
    } else {
      const result = await fileApi.copy(contextMenuTargetIds.value, fileOpTargetDir.value)
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
  if (fileStore.browseMode === 'folder' && fileStore.currentFolderPath) {
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
}

.scroller {
  height: 100%;
}

.grid-view {
  padding: 16px 0;
}

/* 确保 RecycleScroller 的 item view 占满宽度 */
.grid-view :deep(.vue-recycle-scroller__item-view) {
  width: 100% !important;
  position: absolute !important;
  left: 0 !important;
}

/* Grid 行容器 */
.grid-row {
  box-sizing: border-box;
  align-items: flex-start;
}

/* Grid 单元格 */
.grid-cell {
  box-sizing: border-box;
}

.grid-cell.file-drop-active,
.list-drop-target.file-drop-active {
  border-radius: 12px;
  box-shadow: inset 0 0 0 2px color-mix(in srgb, var(--color-accent) 65%, transparent);
  background: color-mix(in srgb, var(--color-accent-light) 32%, transparent);
  animation: file-drop-pulse 0.6s ease infinite alternate;
}

/* 标签拖拽到文件时的徽章预览 */
.grid-cell,
.list-drop-target {
  position: relative;
}

.tag-drop-badge {
  position: absolute;
  bottom: 56px;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 4px 10px 4px 6px;
  border-radius: 20px;
  background: var(--tag-color, #409EFF);
  color: #fff;
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
  pointer-events: none;
  box-shadow: 0 2px 8px rgba(0,0,0,0.22);
  animation: tag-badge-appear 0.18s cubic-bezier(0.34, 1.56, 0.64, 1) both;
  z-index: 10;
}

.tag-drop-badge--list {
  bottom: auto;
  top: 50%;
  left: auto;
  right: 16px;
  transform: translateY(-50%);
}

.tag-drop-badge-icon {
  font-size: 14px;
  line-height: 1;
}

.tag-drop-badge-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: rgba(255,255,255,0.8);
  flex-shrink: 0;
}

.tag-drop-badge-name {
  max-width: 80px;
  overflow: hidden;
  text-overflow: ellipsis;
}

@keyframes tag-badge-appear {
  from {
    opacity: 0;
    transform: translateX(-50%) scale(0.6);
  }
  to {
    opacity: 1;
    transform: translateX(-50%) scale(1);
  }
}

@keyframes file-drop-pulse {
  from { box-shadow: inset 0 0 0 2px color-mix(in srgb, var(--color-accent) 50%, transparent); }
  to   { box-shadow: inset 0 0 0 2px color-mix(in srgb, var(--color-accent) 90%, transparent), 0 0 12px color-mix(in srgb, var(--color-accent) 25%, transparent); }
}

.list-drop-target {
  transition: background-color 0.2s ease, box-shadow 0.2s ease;
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
}

.import-tree-panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--color-border);
  background: color-mix(in srgb, var(--color-bg-secondary) 90%, transparent);
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
