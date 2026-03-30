export const TAG_DRAG_MIME = 'application/x-taghive-tag'

interface TagDragPayload {
  tagId: number
}

interface NativeDroppedFile extends File {
  path?: string
}

export interface TagDragMeta {
  tagId: number
  name: string
  color?: string
  icon?: string
}

// 全局标志：当前是否正在拖拽标签（用于隔离标签拖拽与外部文件拖入）
let _tagDragInProgress = false
// 当前拖拽的 tagId，直接缓存在模块中作为备用
let _dragTagId: number | null = null
// 当前拖拽标签的元数据（用于渲染拖动图标）
let _dragMeta: TagDragMeta | null = null

export function isTagDragInProgress(): boolean {
  return _tagDragInProgress
}

export function getDragTagId(): number | null {
  return _dragTagId
}

function parseFileUri(rawValue: string): string | null {
  if (!rawValue.startsWith('file://')) {
    return null
  }

  try {
    let decoded = decodeURIComponent(rawValue.replace('file://', ''))
    if (/^\/[A-Za-z]:/.test(decoded)) {
      decoded = decoded.slice(1)
    }
    return decoded
  } catch {
    return null
  }
}

export function getDragMeta(): TagDragMeta | null {
  return _dragMeta
}

export function setTagDragData(event: DragEvent, tagId: number, meta?: Omit<TagDragMeta, 'tagId'>) {
  if (!event.dataTransfer) {
    return
  }

  _tagDragInProgress = true
  _dragTagId = tagId
  _dragMeta = meta ? { tagId, ...meta } : { tagId, name: String(tagId) }

  const payload: TagDragPayload = { tagId }
  event.dataTransfer.effectAllowed = 'copyMove'
  event.dataTransfer.setData(TAG_DRAG_MIME, JSON.stringify(payload))
  event.dataTransfer.setData('text/plain', String(tagId))

  // Custom drag ghost: circular badge
  const ghost = _createDragGhost(_dragMeta)
  document.body.appendChild(ghost)
  event.dataTransfer.setDragImage(ghost, 28, 28)
  // Remove ghost after a tick (browser has captured it)
  setTimeout(() => ghost.remove(), 0)
}

function _createDragGhost(meta: TagDragMeta): HTMLElement {
  const el = document.createElement('div')
  const color = meta.color || '#409EFF'
  el.style.cssText = `
    position: fixed;
    top: -9999px;
    left: -9999px;
    width: 56px;
    height: 56px;
    border-radius: 50%;
    background: ${color};
    display: flex;
    align-items: center;
    justify-content: center;
    box-shadow: 0 4px 16px rgba(0,0,0,0.25);
    border: 3px solid rgba(255,255,255,0.8);
    pointer-events: none;
    z-index: 99999;
    font-size: 26px;
    line-height: 1;
    overflow: hidden;
    font-family: "Apple Color Emoji","Segoe UI Emoji","Noto Color Emoji",sans-serif;
  `
  if (meta.icon) {
    el.textContent = meta.icon
  } else {
    // Show first letter of name
    const letter = document.createElement('span')
    letter.style.cssText = 'font-size:18px;font-weight:700;color:rgba(255,255,255,0.95);font-family:system-ui,sans-serif;'
    letter.textContent = meta.name.charAt(0).toUpperCase()
    el.appendChild(letter)
  }
  return el
}

export function clearTagDragState() {
  _tagDragInProgress = false
  _dragTagId = null
  _dragMeta = null
}

export function getDraggedTagId(event: DragEvent): number | null {
  // 优先从 dataTransfer 读取（drop 事件中可用）
  const rawPayload = event.dataTransfer?.getData(TAG_DRAG_MIME)
  if (rawPayload) {
    try {
      const payload = JSON.parse(rawPayload) as TagDragPayload
      if (typeof payload.tagId === 'number') return payload.tagId
    } catch {
      // ignore
    }
  }

  // 从 text/plain 读取备用
  const plainText = event.dataTransfer?.getData('text/plain')
  if (plainText) {
    const id = Number(plainText)
    if (!isNaN(id) && id > 0) return id
  }

  // 从模块缓存读取（当 dataTransfer 数据不可用时）
  return _dragTagId
}

export function hasTagDrag(event: DragEvent): boolean {
  const types = event.dataTransfer?.types
  return !!types && Array.from(types).includes(TAG_DRAG_MIME)
}

export function hasExternalFiles(event: DragEvent): boolean {
  const types = event.dataTransfer?.types
  return !!types && Array.from(types).includes('Files')
}

export function getDroppedFilePaths(event: DragEvent): string[] {
  const paths = new Set<string>()
  const dataTransfer = event.dataTransfer

  if (!dataTransfer) {
    return []
  }

  Array.from(dataTransfer.files).forEach(file => {
    const nativePath = (file as NativeDroppedFile).path
    if (nativePath) {
      paths.add(nativePath)
    }
  })

  const uriList = dataTransfer.getData('text/uri-list')
  if (uriList) {
    uriList
      .split(/\r?\n/)
      .map((line: string) => line.trim())
      .filter((line: string) => line && !line.startsWith('#'))
      .forEach((line: string) => {
        const parsed = parseFileUri(line)
        if (parsed) {
          paths.add(parsed)
        }
      })
  }

  return Array.from(paths)
}
