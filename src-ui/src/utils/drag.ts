export const TAG_DRAG_MIME = 'application/x-taghive-tag'

interface TagDragPayload {
  tagId: number
}

interface NativeDroppedFile extends File {
  path?: string
}

// 全局标志：当前是否正在拖拽标签（用于隔离标签拖拽与外部文件拖入）
let _tagDragInProgress = false
// 当前拖拽的 tagId，直接缓存在模块中作为备用
let _dragTagId: number | null = null

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

export function setTagDragData(event: DragEvent, tagId: number) {
  if (!event.dataTransfer) {
    return
  }

  _tagDragInProgress = true
  _dragTagId = tagId
  const payload: TagDragPayload = { tagId }
  event.dataTransfer.effectAllowed = 'copyMove'
  event.dataTransfer.setData(TAG_DRAG_MIME, JSON.stringify(payload))
  event.dataTransfer.setData('text/plain', String(tagId))
}

export function clearTagDragState() {
  _tagDragInProgress = false
  _dragTagId = null
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
