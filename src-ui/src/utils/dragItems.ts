// 文件/文件夹拖拽工具：用于把文件或文件夹拖到文件夹树节点完成移动/复制。
// 与「标签拖到文件」(utils/drag.ts) 使用不同的 MIME 与全局状态，互不干扰。

export const ITEM_DRAG_MIME = 'application/x-taghive-items'

// 当前拖拽项的类型：文件（可多选）或单个文件夹
export type ItemDragKind = 'file' | 'folder'

export interface ItemDragState {
  kind: ItemDragKind
  fileIds?: number[]     // kind === 'file' 时有效
  folderPath?: string    // kind === 'folder' 时有效
  sourceWs?: string      // 来源工作区根路径（文件夹拖拽时用于跨工作区判定）
  label?: string         // 拖影显示文案
}

// 模块级全局状态：drop 事件中 dataTransfer 可能取不到自定义数据，用此兜底
let _itemDrag: ItemDragState | null = null

export function isItemDragInProgress(): boolean {
  return _itemDrag !== null
}

export function getItemDrag(): ItemDragState | null {
  return _itemDrag
}

export function hasItemDrag(event: DragEvent): boolean {
  const types = event.dataTransfer?.types
  return !!types && Array.from(types).includes(ITEM_DRAG_MIME)
}

export function setItemDragData(event: DragEvent, state: ItemDragState) {
  if (!event.dataTransfer) return
  _itemDrag = state
  event.dataTransfer.effectAllowed = 'copyMove'
  event.dataTransfer.setData(ITEM_DRAG_MIME, JSON.stringify(state))
  // 兜底，便于调试与跨浏览器
  event.dataTransfer.setData('text/plain', state.label || state.folderPath || '')

  const ghost = _createGhost(state)
  document.body.appendChild(ghost)
  event.dataTransfer.setDragImage(ghost, 20, 20)
  setTimeout(() => ghost.remove(), 0)
}

export function clearItemDragState() {
  _itemDrag = null
}

/**
 * 安装全局拖拽状态兜底清理，应在应用启动时调用一次。
 *
 * dragend 原本绑在被拖拽的源卡片上，若拖拽过程中源卡片被卸载（例如列表刷新、
 * 切换浏览标签页导致 files 换掉），dragend 永不触发，_itemDrag 会一直残留，
 * 使后续所有 dragover 都误以为仍在拖拽中，故需在 window 上兜底。
 *
 * 两个事件的清理时机必须区别对待：
 *
 * - dragend 在 drop 处理完之后才派发，此时同步清理是安全的。
 * - drop 则不能同步清理。各落点处理器（文件夹树、文件夹卡片、explorer 空白区、
 *   工作区切换器）都在冒泡阶段读 getItemDrag() 取拖拽内容，而 window 捕获阶段
 *   永远先于后代元素的冒泡阶段执行；在此同步清理会让它们全部读到 null 而直接
 *   return，表现为「拖得动但不发生移动/复制」。因此延到本轮事件派发结束后再清。
 */
export function installGlobalDragCleanup() {
  window.addEventListener('dragend', clearItemDragState, true)
  window.addEventListener('drop', () => {
    // setTimeout 而非 microtask：落点处理器多为 async，其首个 await 之前的同步段
    // （读取 getItemDrag 的部分）需要先跑完
    setTimeout(clearItemDragState, 0)
  }, true)
}

function _createGhost(state: ItemDragState): HTMLElement {
  const el = document.createElement('div')
  const text = state.label
    || (state.kind === 'folder' ? '文件夹' : `${state.fileIds?.length || 1} 个文件`)
  el.style.cssText = `
    position: fixed;
    top: -9999px;
    left: -9999px;
    padding: 6px 12px;
    border-radius: 8px;
    background: #409EFF;
    color: #fff;
    font-size: 13px;
    font-weight: 600;
    white-space: nowrap;
    box-shadow: 0 4px 16px rgba(0,0,0,0.25);
    pointer-events: none;
    z-index: 99999;
    font-family: system-ui, sans-serif;
  `
  el.textContent = text
  return el
}
