<template>
  <div class="tabs-bar">
    <!-- 滚动容器：标签条与 + 按钮同处其中，+ 始终紧跟最后一个标签一起滚动 -->
    <div ref="scrollRef" class="tabs-scroll" @wheel="handleWheel">
      <TransitionGroup name="tab" tag="div" class="tabs-strip" role="tablist" aria-label="浏览标签页">
        <div
          v-for="tab in fileStore.tabList"
          :key="tab.id"
          :data-tab-id="tab.id"
          role="tab"
          :aria-selected="tab.id === fileStore.activeTabId"
          :tabindex="tab.id === fileStore.activeTabId ? 0 : -1"
          @keydown="handleTabKey(tab.id, $event)"
          :class="[
            'tab-item',
            { active: tab.id === fileStore.activeTabId, 'drop-active': dropHoverTabId === tab.id },
          ]"
          :style="tabStyle(tab)"
          :title="tabTooltip(tab)"
          @click="handleSwitch(tab.id)"
          @mousedown.middle.prevent="handleClose(tab.id)"
        >
          <!-- 圆角底板：独立一层，圆角只作用于背景，不裁剪内容 -->
          <span class="tab-shape" />
          <el-icon class="tab-icon"><component :is="tabIcon(tab)" /></el-icon>
          <span class="tab-name">{{ tabTitle(tab) }}</span>
          <el-button
            v-if="fileStore.tabList.length > 1"
            class="tab-close-btn"
            circle
            size="small"
            :title="'关闭标签页'"
            :aria-label="`关闭 ${tabTitle(tab)}`"
            @click.stop="handleClose(tab.id)"
          >
            <el-icon><Close /></el-icon>
          </el-button>
        </div>
      </TransitionGroup>

      <!-- + 按钮同为标签页造型，取中性配色以示与工作区无关 -->
      <button
        type="button"
        aria-label="新建标签页"
        :disabled="atMax"
        class="tab-add"
        :class="{ 'is-disabled': atMax }"
        :style="addStyle"
        :title="atMax ? `标签页数量已达上限（${MAX_TABS} 个）` : '新建标签页'"
        @click="handleAdd"
      >
        <span class="tab-shape" />
        <el-icon><Plus /></el-icon>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Close, Plus, Files, Grid, Folder, FolderOpened } from '@element-plus/icons-vue'
import { useFileStore } from '../stores/files'
import { useAppStore } from '../stores/app'
import { tabTitle, MAX_TABS, type TabState } from '../stores/browserTabs'
import { workspacePalette } from '../utils/workspaceColor'
import { getItemDrag, hasItemDrag } from '../utils/dragItems'
import { transferItems } from '../utils/itemTransfer'

const fileStore = useFileStore()
const appStore = useAppStore()

const scrollRef = ref<HTMLElement>()
const atMax = computed(() => fileStore.tabList.length >= MAX_TABS)

/** 按浏览模式取图标，便于在标签页密集时快速区分 */
function tabIcon(tab: TabState) {
  switch (tab.browseMode) {
    case 'folder':
      return Grid
    case 'tree':
      return Folder
    case 'explorer':
      return FolderOpened
    default:
      return Files
  }
}

/** 悬停提示展示完整路径，标签宽度有限时用于确认具体位置 */
function tabTooltip(tab: TabState): string {
  if (tab.isGlobalView) return '全部工作区'
  return tab.currentFolderPath || tab.workspace || '新标签页'
}

// 主题切换时配色需整体重算，故依赖 appStore.isDark 而非读 CSS 变量
const isDark = computed(() => appStore.isDark)

/** 把工作区配色注入为局部 CSS 变量，样式表内按状态取用 */
function tabStyle(tab: TabState): Record<string, string> {
  return paletteVars(tab.isGlobalView ? '' : tab.workspace)
}

/** + 按钮用空工作区对应的中性灰 */
const addStyle = computed(() => paletteVars(''))

function paletteVars(ws: string): Record<string, string> {
  const p = workspacePalette(ws, isDark.value)
  return {
    '--tab-bg': p.bg,
    '--tab-bg-active': p.bgActive,
    '--tab-text': p.text,
    '--tab-text-active': p.textActive,
  }
}

function handleSwitch(tabId: string) {
  fileStore.switchTab(tabId)
}

async function handleTabKey(tabId: string, event: KeyboardEvent) {
  if (!['ArrowLeft', 'ArrowRight', 'Home', 'End', 'Delete', 'Enter', ' '].includes(event.key)) return
  if ((event.target as HTMLElement).closest('button')) return
  event.preventDefault()
  if (event.key === 'Delete') { handleClose(tabId); return }
  const tabs = fileStore.tabList
  const index = tabs.findIndex(tab => tab.id === tabId)
  const next = event.key === 'Home' ? tabs[0] : event.key === 'End' ? tabs[tabs.length - 1] : tabs[(index + (event.key === 'ArrowLeft' ? -1 : event.key === 'ArrowRight' ? 1 : 0) + tabs.length) % tabs.length]
  await fileStore.switchTab(next.id)
  await nextTick()
  scrollRef.value?.querySelector<HTMLElement>(`[data-tab-id="${next.id}"]`)?.focus()
}

function handleClose(tabId: string) {
  fileStore.closeTab(tabId)
}

// 新标签页默认落在当前工作区根目录
function handleAdd() {
  if (atMax.value) {
    ElMessage.warning(`标签页数量已达上限（${MAX_TABS} 个），请先关闭部分标签页`)
    return
  }
  const ws = appStore.currentWorkspace || ''
  fileStore.addTab({
    workspace: ws,
    isGlobalView: appStore.isGlobalView,
    currentFolderPath: ws,
  })
}

// ─── 拖拽悬停切换标签页 ─────────────────────────────────────
//
// 拖着文件悬停在某个标签页标题上约 1 秒即切换过去，用户随后可把文件放进
// 目标标签页的文件区，实现跨标签页（跨目录/跨工作区）的移动与复制。

/** 悬停切换的等待时长（毫秒）。太短会在划过标签时误切，太长则等得难受 */
const HOVER_SWITCH_DELAY = 1000

/** 当前被拖拽悬停的标签页 id，同时用于去重与高亮 */
const dropHoverTabId = ref('')
let hoverTimer: number | null = null

function cancelHoverSwitch() {
  if (hoverTimer !== null) {
    clearTimeout(hoverTimer)
    hoverTimer = null
  }
  dropHoverTabId.value = ''
}

/**
 * 按坐标反查光标下的标签页 id，不在标签上则返回空串。
 *
 * 不用 event.target 判断：标签内有底板、图标、文字、关闭按钮等多层子元素，
 * 目标是哪一层取决于光标落点，逐层 closest 反而不如直接量矩形稳。
 */
function tabIdAtPoint(x: number, y: number): string {
  const el = scrollRef.value
  if (!el) return ''
  const nodes = el.querySelectorAll<HTMLElement>('[data-tab-id]')
  for (const node of nodes) {
    const r = node.getBoundingClientRect()
    if (x >= r.left && x <= r.right && y >= r.top && y <= r.bottom) {
      return node.dataset.tabId || ''
    }
  }
  return ''
}

/**
 * 全局 dragover：在 window 捕获阶段处理拖拽经过标签栏。
 *
 * 不绑在标签元素上，因为那样依赖事件能一路冒泡到标签：中间任何祖先的
 * stopPropagation、或覆盖在标签栏之上的透明层，都会让处理器收不到事件，
 * 表现为「光标是禁止图标且不切换」——两个症状同源，都是因为 preventDefault
 * 没被调用。捕获阶段从 window 开始，最先执行，不受这些干扰。
 *
 * dragover 在悬停期间以约 350ms 的间隔反复触发，故必须靠 dropHoverTabId
 * 去重：每次都重新计时的话计时器永远排不到头，1 秒的等待会变成「永不切换」。
 */
function handleWindowDragOver(event: DragEvent) {
  if (!hasItemDrag(event) && !getItemDrag()) return
  const tabId = tabIdAtPoint(event.clientX, event.clientY)
  if (!tabId) {
    // 移出标签栏：撤掉高亮与计时，事件继续交给下游落点（文件区、文件夹树等）
    if (dropHoverTabId.value) cancelHoverSwitch()
    return
  }

  // 标签页是有效落点，必须 preventDefault 且 dropEffect 不为 none，
  // 否则浏览器判定此处不可放置，光标显示禁止符
  event.preventDefault()
  if (event.dataTransfer) {
    event.dataTransfer.dropEffect = event.ctrlKey || event.metaKey ? 'copy' : 'move'
  }

  if (dropHoverTabId.value === tabId) return
  cancelHoverSwitch()
  if (tabId === fileStore.activeTabId) return

  dropHoverTabId.value = tabId
  hoverTimer = window.setTimeout(() => {
    hoverTimer = null
    dropHoverTabId.value = ''
    fileStore.switchTab(tabId)
  }, HOVER_SWITCH_DELAY)
}

/**
 * 全局 drop：在标签页标题上松手，直接把拖拽项移动/复制到该标签页的当前目录。
 *
 * 拖到标签上时意图已经明确（就是要放进那个标签页所在的目录），故不再要求
 * 用户切过去后重放一次。Ctrl/Cmd 为复制，与其他落点一致。
 *
 * 必须在最前面同步取出 drag：installGlobalDragCleanup 的 drop 清理虽已延后到
 * 本轮派发之后，但此处仍先取再 await，避免依赖那个延后的实现细节。
 */
async function handleWindowDrop(event: DragEvent) {
  const drag = getItemDrag()
  if (!hasItemDrag(event) && !drag) return
  const tabId = tabIdAtPoint(event.clientX, event.clientY)
  cancelHoverSwitch()
  if (!tabId) return
  event.preventDefault()
  if (!drag) return

  const tab = fileStore.tabList.find((t) => t.id === tabId)
  if (!tab) return

  // 目标目录取该标签页当前所在层级；all/tree 等无目录层级的模式下退回工作区根
  const targetPath = tab.currentFolderPath || tab.workspace
  if (!targetPath) {
    ElMessage.warning('该标签页没有可作为落点的目录')
    return
  }

  const copy = event.ctrlKey || event.metaKey
  const ok = await transferItems(drag, { targetPath, targetWs: tab.workspace, copy })
  if (!ok) return

  // 源目录与目标目录的内容都变了，且别的标签页可能正显示同一目录：
  // 全部标记为脏，只重载当前标签页（reloadCurrentView 会清掉它的脏标记），
  // 其余等切过去时惰性重载——此刻重载用户看不到，还会并发打后端
  fileStore.markTabsDirty()
  await fileStore.reloadCurrentView()
}

/*
 * 均为捕获阶段：
 * - dragover/drop 需要先于任何祖先处理器拿到事件（见 handleWindowDragOver 注释）
 * - dragend 用于兜底停表，否则在别处松手后仍会延迟切换一次
 */
onMounted(() => {
  window.addEventListener('dragover', handleWindowDragOver, true)
  window.addEventListener('drop', handleWindowDrop, true)
  window.addEventListener('dragend', cancelHoverSwitch, true)
})

onUnmounted(() => {
  window.removeEventListener('dragover', handleWindowDragOver, true)
  window.removeEventListener('drop', handleWindowDrop, true)
  window.removeEventListener('dragend', cancelHoverSwitch, true)
  if (hoverTimer !== null) clearTimeout(hoverTimer)
})

/**
 * 竖向滚轮转为横向滚动。
 *
 * 标签栏的滚动条被隐藏（否则会占掉高度、破坏标签下边缘与栏底相接的观感），
 * 而竖向滚轮默认不驱动横向滚动，于是溢出的标签在纯鼠标操作下无法触达。
 */
function handleWheel(e: WheelEvent) {
  const el = scrollRef.value
  if (!el || e.deltaY === 0) return
  if (el.scrollWidth <= el.clientWidth) return
  e.preventDefault()
  el.scrollLeft += e.deltaY
}

// 切换/新建标签页后把目标滚入可见区，否则活动标签可能停在栏外
watch(
  () => fileStore.activeTabId,
  async (id) => {
    if (!id) return
    await nextTick()
    const el = scrollRef.value?.querySelector<HTMLElement>(`[data-tab-id="${id}"]`)
    el?.scrollIntoView({ block: 'nearest', inline: 'nearest', behavior: 'smooth' })
  }
)
</script>

<style scoped>
.tabs-bar {
  display: flex;
  align-items: flex-end;
  padding: 4px 12px 0;
  border-bottom: 1px solid var(--color-border);
  background: var(--color-bg-primary);
  flex-shrink: 0;
  min-height: 34px;
}

.tabs-scroll {
  display: flex;
  align-items: flex-end;
  overflow-x: auto;
  overflow-y: hidden;
  min-width: 0;
  flex: 1;
  scrollbar-width: none;
  /* 标签下边缘与标签栏底边相接 */
  padding-bottom: 0;
}

.tabs-scroll::-webkit-scrollbar {
  display: none;
}

/*
 * 标签条按内容取宽（flex: 0 1 auto，可缩不可涨）。
 *
 * 不给 grow：否则标签条会撑满整条栏，+ 按钮被推到最右端而非紧跟最后一个标签。
 * 不给 min-width: 0：保留自动最小尺寸（各标签 min-width 之和），标签条才会在
 * 溢出时停止收缩，把溢出交给 .tabs-scroll 变成横向滚动。
 */
.tabs-strip {
  display: flex;
  align-items: flex-end;
  flex: 0 1 auto;
}

/*
 * 文档标签风格：上圆角矩形，下边缘与标签栏底边相接。
 */
.tab-item {
  position: relative;
  /* 让 .tab-shape 的 z-index: -1 局限在本标签内，
     否则它会穿到标签栏背景之下而完全不可见 */
  isolation: isolate;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 14px 6px;
  cursor: pointer;
  font-size: 13px;
  color: var(--tab-text);
  /*
   * basis 0 + grow 1：各标签等分标签条宽度（与浏览器一致），
   * 少量标签时被 max-width 截住，标签变多则等量收缩到 min-width，
   * 再溢出由 .tabs-scroll 接管为左右滚动。
   */
  flex: 1 1 0;
  min-width: 96px;
  max-width: 200px;
  min-height: 30px;
  /* 矩形不再互嵌斜边，改为留细缝分隔（负边距会盖住邻居的圆角） */
  margin-right: 2px;
  transition:
    color 0.18s ease,
    max-width 0.22s ease;
}

/* 与 + 按钮之间留稍宽的间距，区分「标签」与「新建」 */
.tab-item:last-child {
  margin-right: 4px;
}

/*
 * 底板：上两角圆角、下两角直角的圆角矩形，下边缘与标签栏底边严丝合缝。
 *
 * 改回 border-radius 而非 clip-path 切形——纯矩形不需要多边形，
 * border-radius 的圆角是真正的圆弧，不像折线逼近那样在放大时露出棱边。
 */
.tab-shape {
  position: absolute;
  inset: 0;
  z-index: -1;
  background: var(--tab-bg);
  border-radius: 8px 8px 0 0;
  transition: background 0.18s ease;
}

.tab-item:hover {
  color: var(--tab-text-active);
}

.tab-item:hover .tab-shape {
  filter: brightness(0.97);
}

/* 活动标签置于相邻标签之上，斜边不被邻居盖住 */
.tab-item.active {
  color: var(--tab-text-active);
  z-index: 2;
  font-weight: 500;
}

.tab-item.active .tab-shape {
  background: var(--tab-bg-active);
}

.tab-item.active .tab-close-btn {
  color: var(--tab-text-active) !important;
}

/* 拖拽悬停时的待切换提示，由 Phase 4 的悬停切换逻辑加上 */
.tab-item.drop-active .tab-shape {
  outline: 2px dashed var(--color-accent);
  outline-offset: -3px;
}

.tab-icon {
  flex-shrink: 0;
  font-size: 14px;
}

.tab-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tab-close-btn {
  flex-shrink: 0;
  width: 18px !important;
  height: 18px !important;
  padding: 0 !important;
  border: none !important;
  background: transparent !important;
  color: var(--tab-text) !important;
  opacity: 0;
  transition: opacity 0.15s ease;
  font-size: 10px !important;
}

.tab-item:hover .tab-close-btn,
.tab-item.active .tab-close-btn {
  opacity: 0.75;
}

.tab-close-btn:hover {
  opacity: 1 !important;
  background: rgba(0, 0, 0, 0.12) !important;
}

/* + 按钮：与标签同高同形，仅更窄，视觉上像一个空标签 */
.tab-add {
  position: relative;
  isolation: isolate;
  display: flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 auto;
  width: 40px;
  min-height: 30px;
  padding: 5px 8px 6px;
  cursor: pointer;
  color: var(--tab-text);
  transition: color 0.15s ease;
}

.tab-add .tab-shape {
  opacity: 0.6;
  transition:
    opacity 0.15s ease,
    background 0.18s ease;
}

.tab-add:hover {
  color: var(--tab-text-active);
}

.tab-add:hover .tab-shape {
  opacity: 1;
}

/* 达到上限后保留按钮位置，仅置灰——直接隐藏会让标签栏右端突然缺一块 */
.tab-add.is-disabled {
  cursor: not-allowed;
  opacity: 0.4;
}

.tab-add.is-disabled:hover {
  color: var(--tab-text);
}

/* ─── 新建/关闭/重排动画 ─── */
.tab-enter-from,
.tab-leave-to {
  opacity: 0;
  /* 从零宽展开/收拢，相邻标签随之平移，堆叠变化不跳变 */
  max-width: 0;
  min-width: 0;
  padding-left: 0;
  padding-right: 0;
  transform: translateY(6px);
}

.tab-enter-active,
.tab-leave-active {
  transition:
    opacity 0.2s ease,
    max-width 0.24s ease,
    min-width 0.24s ease,
    padding 0.24s ease,
    transform 0.2s ease;
  overflow: hidden;
}

/*
 * 注意：这里刻意不给 .tab-leave-active 加 position: absolute。
 * 那是 TransitionGroup 的常见写法，用于让离场元素立刻脱离文档流；
 * 但本组件靠「宽度收拢」驱动动画，脱流后宽度不再占位，相邻标签会
 * 瞬间跳到最终位置，反而失去平滑让位的效果。
 */

/* 其余标签平滑让位 */
.tab-move {
  transition: transform 0.24s ease;
}
</style>
