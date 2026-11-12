import { nextTick } from 'vue'
import { useFileStore } from '../stores/files'
import type { FileSummary } from '../types'

/** 文件区共用的单一 Tab 入口与方向键导航。 */
export function useFileNavigation(open: (file: FileSummary) => void, scroll?: (index: number) => void, columns = () => 1) {
  const store = useFileStore()
  function fileTabIndex(id: number) {
    const active = store.files.some(f => f.id === store.activeId) ? store.activeId : store.files[0]?.id
    return id === active ? 0 : -1
  }
  async function handleFileKey(file: FileSummary, event: KeyboardEvent) {
    if ((event.target as HTMLElement).closest('button,input,textarea,select,[contenteditable="true"]')) return
    if (!['Enter', ' ', 'ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', 'Home', 'End'].includes(event.key)) return
    event.preventDefault()
    if (event.key === 'Enter') { open(file); return }
    if (event.key === ' ') { store.selectFile(file.id, true); return }
    const index = store.files.findIndex(f => f.id === file.id)
    const delta = event.key === 'ArrowLeft' ? -1 : event.key === 'ArrowRight' ? 1 : event.key === 'ArrowUp' ? -columns() : columns()
    const targetIndex = event.key === 'Home' ? 0 : event.key === 'End' ? store.files.length - 1 : Math.max(0, Math.min(store.files.length - 1, index + delta))
    const target = store.files[targetIndex]
    if (!target) return
    if (event.shiftKey) store.selectRange(file.id, target.id)
    else store.selectFile(target.id)
    scroll?.(targetIndex)
    await nextTick()
    const element = document.querySelector<HTMLElement>(`[role="option"][data-file-id="${target.id}"]`)
    element?.focus({ preventScroll: true })
    element?.scrollIntoView({ block: 'nearest', inline: 'nearest' })
  }
  return { fileTabIndex, handleFileKey }
}
