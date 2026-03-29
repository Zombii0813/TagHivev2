export const TAG_DRAG_MIME = 'application/x-taghive-tag'

interface TagDragPayload {
  tagId: number
}

interface NativeDroppedFile extends File {
  path?: string
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

  const payload: TagDragPayload = { tagId }
  event.dataTransfer.effectAllowed = 'copyMove'
  event.dataTransfer.setData(TAG_DRAG_MIME, JSON.stringify(payload))
  event.dataTransfer.setData('text/plain', String(tagId))
}

export function getDraggedTagId(event: DragEvent): number | null {
  const rawPayload = event.dataTransfer?.getData(TAG_DRAG_MIME)
  if (!rawPayload) {
    return null
  }

  try {
    const payload = JSON.parse(rawPayload) as TagDragPayload
    return typeof payload.tagId === 'number' ? payload.tagId : null
  } catch {
    return null
  }
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