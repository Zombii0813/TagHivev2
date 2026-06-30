<template>
  <Teleport to="body">
    <!--
      ft-float: 固定定位 + transform 控制位置，悬浮在文件列表上方
      折叠态：仅显示一个可拖拽的毛玻璃图标
      展开态：毛玻璃面板，内含完整文件夹树
    -->
    <div
      ref="floatRef"
      class="ft-float"
      :class="{ expanded: isExpanded, dragging: isDragging }"
      :style="floatStyle"
    >
      <!-- 折叠图标（始终可见、可拖拽、可点击展开） -->
      <Transition name="ft-icon-fade">
        <div
          v-show="!isExpanded"
          class="ft-icon"
          title="展开目录导航"
          @mousedown.left="startDrag"
          @click="onIconClick"
        >
          <el-icon :size="22"><Files /></el-icon>
        </div>
      </Transition>

      <!-- 展开面板 -->
      <Transition name="ft-panel-pop">
        <div v-show="isExpanded" class="ft-panel">
        <!-- 标题栏：可拖拽移动；点击（非拖拽）即折叠 -->
        <div class="ft-header" title="点击折叠" @mousedown.left="startDrag" @click="onHeaderClick">
          <el-icon class="ft-header-icon"><Files /></el-icon>
          <span class="ft-title">目录导航</span>
        </div>

        <!-- 树滚动区 -->
        <div ref="bodyRef" class="ft-body">
          <div v-if="loading" class="ft-state">
            <el-icon class="ft-loading"><Loading /></el-icon>
            <span>加载中...</span>
          </div>

          <div v-else-if="treeRoots.length === 0" class="ft-state">
            <span>暂无文件夹</span>
          </div>

          <template v-else>
            <div v-for="root in treeRoots" :key="root.wsPath" class="ft-ws-block">
              <!-- 工作区根节点（可作为放置目标） -->
              <div
                class="ft-root-node"
                :class="{ selected: selectedPath === root.node.path, 'drop-active': dropActivePath === root.node.path }"
                @click="onSelect(root.node.path, root.wsPath)"
                @contextmenu.prevent="onNodeContextMenu({ folder: root.node, event: $event }, root.wsPath)"
                @dragover="onRootDragOver(root.node.path, $event)"
                @dragleave="onRootDragLeave(root.node.path)"
                @drop="onRootDrop(root.node.path, root.wsPath, $event)"
              >
                <el-icon class="ft-root-icon"><Folder /></el-icon>
                <span class="ft-root-name">{{ root.node.name }}</span>
                <span class="ft-root-count">({{ root.totalFiles }})</span>
              </div>

              <!-- 子树 -->
              <FolderTreeNode
                v-for="child in root.node.children"
                :key="child.path"
                :folder="child"
                :selected-path="selectedPath"
                :level="1"
                @select="(p: string) => onSelect(p, root.wsPath)"
                @contextmenu="(payload) => onNodeContextMenu(payload, root.wsPath)"
                @item-drop="(payload) => onChildItemDrop(payload, root.wsPath)"
              />
            </div>
          </template>
        </div>
      </div>
      </Transition>
    </div>

    <!-- 右键菜单 -->
    <el-popover
      :visible="ctxVisible"
      :virtual-ref="ctxTrigger"
      virtual-triggering
      trigger="contextmenu"
      placement="bottom-start"
      :width="148"
      popper-class="context-menu-popover"
      @update:visible="(v: boolean) => { if (!v) ctxVisible = false }"
    >
      <div class="context-menu">
        <div class="context-menu-item" @click="openCreateDialog">
          <el-icon><FolderAdd /></el-icon>
          <span>新建子目录</span>
        </div>
        <div class="context-menu-item" @click="emitFolderOp('move')">
          <el-icon><FolderOpened /></el-icon>
          <span>移动到...</span>
        </div>
        <div class="context-menu-item" @click="emitFolderOp('copy')">
          <el-icon><CopyDocument /></el-icon>
          <span>复制到...</span>
        </div>
      </div>
    </el-popover>

    <!-- 新建子目录对话框 -->
    <el-dialog
      v-model="showCreateDialog"
      title="新建子目录"
      width="400px"
      append-to-body
      destroy-on-close
    >
      <div class="create-dialog-hint">在 <strong>{{ ctxFolder?.name }}</strong> 下创建子目录</div>
      <el-input
        v-model="newName"
        placeholder="输入目录名称"
        maxlength="80"
        clearable
        style="margin-top: 12px"
        @keyup.enter="confirmCreate"
      />
      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" :loading="creating" :disabled="!newName.trim()" @click="confirmCreate">创建</el-button>
      </template>
    </el-dialog>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { Files, Folder, FolderAdd, FolderOpened, CopyDocument, Loading } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { invoke } from '@tauri-apps/api/core'
import { folderApi } from '../api/folders'
import { wsClient } from '../api/websocket'
import { useFileStore } from '../stores/files'
import type { FolderNode } from '../types'
import FolderTreeNode from './FolderTreeNode.vue'
import { hasItemDrag, getItemDrag } from '../utils/dragItems'

const fileStore = useFileStore()

// ─── Props & Emits ────────────────────────────────────────────
const props = defineProps<{
  rootPath?: string | null
  workspaces?: string[]
  boundary?: HTMLElement | null   // 拖拽边界容器（文件列表区域）
}>()

const emit = defineEmits<{
  select: [path: string, wsPath?: string]
  'folder-op': [payload: { mode: 'move' | 'copy'; path: string; wsPath: string }]
  'item-drop': [payload: { targetPath: string; targetWs: string; copy: boolean }]
}>()

// ─── 浮层状态 ─────────────────────────────────────────────────
const PANEL_W = 280   // 展开面板宽度，用于边界夹紧
const PANEL_H = 360   // 展开面板高度，用于边界夹紧
const ICON_SZ = 44    // 折叠图标尺寸

const floatRef = ref<HTMLElement>()
const bodyRef = ref<HTMLElement>()
const isExpanded = ref(false)
const isDragging = ref(false)
const posX = ref(-9999)
const posY = ref(-9999)
const posInitialized = ref(false)
// 区分「拖拽」与「点击」：拖拽超过阈值后不再触发展开
const dragMoved = ref(false)

const floatStyle = computed(() => ({
  transform: `translate(${posX.value}px, ${posY.value}px)`,
  visibility: (posInitialized.value ? 'visible' : 'hidden') as 'visible' | 'hidden',
}))

// ─── 数据 ─────────────────────────────────────────────────────
interface TreeRoot { node: FolderNode; wsPath: string; totalFiles: number }
const loading = ref(false)
const treeRoots = ref<TreeRoot[]>([])
const selectedPath = ref('')

function lastName(p: string) {
  return p.split(/[/\\]/).filter(Boolean).pop() || p
}

// 计算工作区总文件数（根目录直接文件 + 各子目录文件数）
function calcTotal(root: FolderNode): number {
  let count = root.file_count
  for (const child of root.children) count += child.file_count
  return count
}

async function loadOne(ws: string): Promise<TreeRoot | null> {
  try {
    const res = await folderApi.getTree(ws)
    const node: FolderNode = {
      name: lastName(ws),
      path: ws,
      file_count: res.root_file_count,
      children: res.folders,
      is_expanded: true,
    }
    return { node, wsPath: ws, totalFiles: calcTotal(node) }
  } catch (e) {
    console.error('FolderTreePanel: failed to load', ws, e)
    return null
  }
}

async function loadAll() {
  const list = props.workspaces?.length
    ? props.workspaces
    : (props.rootPath ? [props.rootPath] : [])
  if (!list.length) {
    treeRoots.value = []
    return
  }
  loading.value = true
  try {
    const results = await Promise.all(list.map(loadOne))
    treeRoots.value = results.filter((r): r is TreeRoot => r !== null)
  } finally {
    loading.value = false
  }
}

function onSelect(path: string, wsPath: string) {
  selectedPath.value = path
  emit('select', path, wsPath)
}

// 高亮并将当前浏览目录滚动到树窗可视区中心
async function highlightCurrentFolder() {
  const cur = fileStore.currentFolderPath
  if (!cur) return
  selectedPath.value = cur
  // 等待父链自动展开（FolderTreeNode 监听 selectedPath）后再滚动定位
  await nextTick()
  await nextTick()
  const body = bodyRef.value
  if (!body) return
  const norm = cur.replace(/\\/g, '/')
  // 根节点没有 data-folder-path，单独处理：滚到顶部
  const target = body.querySelector<HTMLElement>(`[data-folder-path="${cssEscape(norm)}"]`)
    || body.querySelector<HTMLElement>(`[data-folder-path="${cssEscape(cur)}"]`)
  if (target) {
    // 以条目为中心滚动
    const offset = target.offsetTop - body.clientHeight / 2 + target.clientHeight / 2
    body.scrollTo({ top: Math.max(0, offset), behavior: 'smooth' })
  } else {
    // 命中工作区根或未找到：回到顶部
    body.scrollTo({ top: 0, behavior: 'smooth' })
  }
}

// 转义属性选择器中的特殊字符（路径含空格、括号等）
function cssEscape(value: string): string {
  if (typeof CSS !== 'undefined' && CSS.escape) return CSS.escape(value)
  return value.replace(/["\\]/g, '\\$&')
}

// ─── 拖拽 ─────────────────────────────────────────────────────
function clampToBoundary(x: number, y: number) {
  const el = props.boundary
  if (!el) return { x, y }
  const rect = el.getBoundingClientRect()
  // 折叠态按图标尺寸夹紧，展开态按面板尺寸夹紧
  const w = isExpanded.value ? PANEL_W : ICON_SZ
  const h = isExpanded.value ? PANEL_H : ICON_SZ
  const cx = Math.max(rect.left, Math.min(x, rect.right - w))
  const cy = Math.max(rect.top, Math.min(y, rect.bottom - h))
  return { x: cx, y: cy }
}

function startDrag(e: MouseEvent) {
  isDragging.value = true
  dragMoved.value = false
  const ox = e.clientX - posX.value
  const oy = e.clientY - posY.value
  const startX = e.clientX
  const startY = e.clientY

  function onMove(ev: MouseEvent) {
    if (Math.abs(ev.clientX - startX) > 3 || Math.abs(ev.clientY - startY) > 3) {
      dragMoved.value = true
    }
    const { x, y } = clampToBoundary(ev.clientX - ox, ev.clientY - oy)
    posX.value = x
    posY.value = y
  }
  function onUp() {
    isDragging.value = false
    window.removeEventListener('mousemove', onMove)
    window.removeEventListener('mouseup', onUp)
  }
  window.addEventListener('mousemove', onMove)
  window.addEventListener('mouseup', onUp)
}

function onIconClick() {
  // 拖拽过程中产生的 click 不展开
  if (dragMoved.value) {
    dragMoved.value = false
    return
  }
  isExpanded.value = true
  // 展开后确保面板仍在边界内
  nextTick(() => {
    const { x, y } = clampToBoundary(posX.value, posY.value)
    posX.value = x
    posY.value = y
  })
  // 展开后把当前层级滚动到中心
  highlightCurrentFolder()
}

function onHeaderClick() {
  // 拖拽产生的 click 不折叠，仅纯点击折叠
  if (dragMoved.value) {
    dragMoved.value = false
    return
  }
  isExpanded.value = false
}

// ─── 右键菜单：新建子目录 ──────────────────────────────────────
const ctxVisible = ref(false)
const ctxTrigger = ref<HTMLElement>()
const ctxFolder = ref<FolderNode | null>(null)
const ctxWsPath = ref('')
const showCreateDialog = ref(false)
const newName = ref('')
const creating = ref(false)

const ctxAnchor = (() => {
  const el = document.createElement('div')
  el.style.cssText = 'position:fixed;left:-9999px;top:-9999px;width:1px;height:1px;pointer-events:none'
  document.body.appendChild(el)
  return el
})()

function onNodeContextMenu(payload: { folder: FolderNode; event: MouseEvent }, wsPath: string) {
  ctxFolder.value = payload.folder
  ctxWsPath.value = wsPath
  window.dispatchEvent(new Event('close-context-menus'))
  ctxAnchor.style.left = `${payload.event.clientX}px`
  ctxAnchor.style.top = `${payload.event.clientY}px`
  ctxTrigger.value = ctxAnchor
  ctxVisible.value = true
}

function openCreateDialog() {
  ctxVisible.value = false
  newName.value = ''
  showCreateDialog.value = true
}

// 触发文件夹移动/复制：把来源文件夹及其工作区交给父组件打开对话框
function emitFolderOp(mode: 'move' | 'copy') {
  ctxVisible.value = false
  const folder = ctxFolder.value
  const ws = ctxWsPath.value
  if (!folder || !ws) return
  emit('folder-op', { mode, path: folder.path, wsPath: ws })
}

// ─── 拖拽放置 ─────────────────────────────────────────────────
const dropActivePath = ref('')

function onRootDragOver(rootPath: string, event: DragEvent) {
  const drag = getItemDrag()
  if (!hasItemDrag(event) && !drag) return
  // 文件夹拖到自身不允许
  if (drag?.kind === 'folder' && drag.folderPath === rootPath) return
  event.preventDefault()
  dropActivePath.value = rootPath
  if (event.dataTransfer) {
    event.dataTransfer.dropEffect = event.ctrlKey || event.metaKey ? 'copy' : 'move'
  }
}

function onRootDragLeave(rootPath: string) {
  if (dropActivePath.value === rootPath) dropActivePath.value = ''
}

function onRootDrop(rootPath: string, wsPath: string, event: DragEvent) {
  if (!hasItemDrag(event) && !getItemDrag()) return
  event.preventDefault()
  dropActivePath.value = ''
  emit('item-drop', { targetPath: rootPath, targetWs: wsPath, copy: event.ctrlKey || event.metaKey })
}

// 子节点 drop 透传：补充目标工作区
function onChildItemDrop(payload: { targetPath: string; copy: boolean }, wsPath: string) {
  emit('item-drop', { targetPath: payload.targetPath, targetWs: wsPath, copy: payload.copy })
}

async function confirmCreate() {
  const name = newName.value.trim()
  const folder = ctxFolder.value
  const ws = ctxWsPath.value
  if (!name || !folder || !ws) return
  creating.value = true
  try {
    try {
      await folderApi.createFolder(ws, folder.path, name)
    } catch (err: any) {
      if (err?.response?.status !== 404) throw err
      // 后端不可用时回退到 Tauri 原生创建
      await invoke('create_folder', { path: `${folder.path.replace(/[/\\]+$/, '')}/${name}` })
    }
    showCreateDialog.value = false
    ElMessage.success(`已创建目录：${name}`)
    await loadAll()
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.detail || '创建目录失败')
  } finally {
    creating.value = false
  }
}

// ─── 定位与生命周期 ───────────────────────────────────────────
function initPosition() {
  const el = props.boundary
  if (!el) return
  const rect = el.getBoundingClientRect()
  if (rect.width === 0 && rect.height === 0) return
  // 默认停靠在左上角，留出少量边距
  posX.value = rect.left + 16
  posY.value = rect.top + 16
  posInitialized.value = true
}

function closeCtx() { ctxVisible.value = false }

let unsubFolderChanged: (() => void) | null = null

onMounted(async () => {
  window.addEventListener('close-context-menus', closeCtx)
  await nextTick()
  initPosition()
  await loadAll()
  await highlightCurrentFolder()
  // 目录树变更（移动/复制/新建目录等）后实时刷新
  unsubFolderChanged = wsClient.on<{ workspace: string }>('folder_tree_changed', async () => {
    await loadAll()
    await highlightCurrentFolder()
  })
})

onUnmounted(() => {
  window.removeEventListener('close-context-menus', closeCtx)
  if (unsubFolderChanged) { unsubFolderChanged(); unsubFolderChanged = null }
})

// 工作区/根路径变化时重载，并在边界就绪后初始化位置
watch(() => [props.rootPath, ...(props.workspaces ?? [])], async () => {
  await loadAll()
  await highlightCurrentFolder()
})
watch(() => props.boundary, async (el) => {
  if (el && !posInitialized.value) { await nextTick(); initPosition() }
})

// 当前浏览目录变化时（含切换工作区后恢复层级）同步高亮并居中
watch(() => fileStore.currentFolderPath, () => {
  highlightCurrentFolder()
})
</script>

<style scoped>
/* ─── 浮层根 ───────────────────────────────── */
.ft-float {
  position: fixed;
  top: 0;
  left: 0;
  z-index: 300;
  pointer-events: none;   /* 子元素按需开启 */
}

/* ─── 折叠图标 ─────────────────────────────── */
.ft-icon {
  pointer-events: all;
  width: 44px;
  height: 44px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  color: var(--color-accent);
  border-radius: 12px;
  /* 半透明 + 毛玻璃 */
  background: color-mix(in srgb, var(--color-bg-primary) 60%, transparent);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
  border: 1px solid color-mix(in srgb, var(--color-accent) 40%, transparent);
  box-shadow: 0 3px 12px rgba(0, 0, 0, 0.22);
  transition: transform 0.15s;
}
.ft-icon:hover { transform: scale(1.08); }
.ft-float.dragging .ft-icon { cursor: grabbing; transform: scale(1.1); }

/* ─── 展开面板 ─────────────────────────────── */
.ft-panel {
  pointer-events: all;
  width: 280px;
  max-height: 360px;
  display: flex;
  flex-direction: column;
  border-radius: 12px;
  overflow: hidden;
  /* 半透明 + 毛玻璃 */
  background: color-mix(in srgb, var(--color-bg-primary) 72%, transparent);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border: 1px solid color-mix(in srgb, var(--color-border) 80%, transparent);
  box-shadow: 0 8px 28px rgba(0, 0, 0, 0.28);
}

.ft-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 10px;
  cursor: pointer;
  user-select: none;
  border-bottom: 1px solid color-mix(in srgb, var(--color-border) 60%, transparent);
  background: color-mix(in srgb, var(--color-bg-secondary) 50%, transparent);
  transition: background-color 0.15s;
}
.ft-header:hover { background: color-mix(in srgb, var(--color-bg-secondary) 75%, transparent); }
.ft-float.dragging .ft-header { cursor: grabbing; }
.ft-header-icon { font-size: 16px; color: var(--color-accent); flex-shrink: 0; }
.ft-title { flex: 1; font-size: 13px; font-weight: 600; color: var(--color-text-primary); }

.ft-body {
  flex: 1;
  overflow-y: auto;
  padding: 6px;
  user-select: none;
}

.ft-state {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 16px;
  color: var(--color-text-secondary);
  font-size: 13px;
}
.ft-loading { animation: ft-rotate 1s linear infinite; }
@keyframes ft-rotate { from { transform: rotate(0); } to { transform: rotate(360deg); } }

.ft-ws-block + .ft-ws-block { margin-top: 6px; }

.ft-root-node {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 8px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  transition: background-color 0.2s;
}
.ft-root-node:hover { background-color: var(--color-bg-hover); }
.ft-root-node.selected { background-color: var(--color-accent-light); color: var(--color-accent); }
.ft-root-node.drop-active { background-color: var(--color-accent-light); outline: 2px dashed var(--color-accent); outline-offset: -2px; }
.ft-root-icon { font-size: 16px; color: #e6a23c; flex-shrink: 0; }
.ft-root-node.selected .ft-root-icon { color: var(--color-accent); }
.ft-root-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ft-root-count { font-size: 11px; color: var(--color-text-secondary); flex-shrink: 0; }
.ft-root-node.selected .ft-root-count { color: var(--color-accent); }

.context-menu { padding: 4px 0; }
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
.context-menu-item:hover { background-color: var(--color-bg-secondary); }
.create-dialog-hint { font-size: 13px; color: var(--color-text-secondary); }

/* ─── 展开/折叠过渡动画 ───────────────────────── */
/* 面板：从顶部栏方向缩放 + 淡入，营造"展开"观感 */
.ft-panel-pop-enter-active {
  transition: transform 0.2s cubic-bezier(0.34, 1.32, 0.64, 1), opacity 0.18s ease;
}
.ft-panel-pop-leave-active {
  transition: transform 0.15s ease, opacity 0.15s ease;
}
.ft-panel-pop-enter-from,
.ft-panel-pop-leave-to {
  opacity: 0;
  transform: scale(0.85);
  transform-origin: top left;
}

/* 折叠图标：淡入缩放 */
.ft-icon-fade-enter-active {
  transition: transform 0.2s cubic-bezier(0.34, 1.32, 0.64, 1), opacity 0.18s ease;
}
.ft-icon-fade-leave-active {
  transition: transform 0.12s ease, opacity 0.12s ease;
}
.ft-icon-fade-enter-from,
.ft-icon-fade-leave-to {
  opacity: 0;
  transform: scale(0.6);
}
</style>
