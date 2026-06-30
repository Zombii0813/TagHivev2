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
