import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import type { Tag } from '../types'
import { tagApi } from '../api/tags'
import { useFileStore } from './files'

function buildTagOrderKey(root?: string | null) {
  return `taghive:tag-order:${root || '__global__'}`
}

export const useTagStore = defineStore('tags', () => {
  // State
  const tags = ref<Tag[]>([])
  const selectedTagIds = ref<Set<number>>(new Set())
  const isLoading = ref(false)
  const orderIds = ref<number[]>([])
  const lastLoadedRoot = ref<string>()

  // Getters
  const tagMap = computed(() => {
    const map = new Map<number, Tag>()
    tags.value.forEach(tag => map.set(tag.id, tag))
    return map
  })

  const selectedTags = computed(() => {
    return tags.value.filter(t => selectedTagIds.value.has(t.id))
  })

  const hasSelection = computed(() => selectedTagIds.value.size > 0)

  const orderedTags = computed(() => {
    if (!orderIds.value.length) {
      return tags.value
    }

    const orderMap = new Map(orderIds.value.map((id, index) => [id, index]))
    return [...tags.value].sort((left, right) => {
      const leftOrder = orderMap.get(left.id) ?? Number.MAX_SAFE_INTEGER
      const rightOrder = orderMap.get(right.id) ?? Number.MAX_SAFE_INTEGER
      if (leftOrder !== rightOrder) {
        return leftOrder - rightOrder
      }
      return left.name.localeCompare(right.name, 'zh-CN')
    })
  })

  function syncTagOrder(root?: string) {
    const storageKey = buildTagOrderKey(root)
    let storedOrder: number[] = []

    try {
      const raw = localStorage.getItem(storageKey)
      if (raw) {
        const parsed = JSON.parse(raw)
        if (Array.isArray(parsed)) {
          storedOrder = parsed.filter((id): id is number => typeof id === 'number')
        }
      }
    } catch (error) {
      console.warn('Failed to parse tag order:', error)
    }

    const tagIds = tags.value.map(tag => tag.id)
    const validStored = storedOrder.filter(id => tagIds.includes(id))
    const missingIds = tagIds.filter(id => !validStored.includes(id))
    orderIds.value = [...validStored, ...missingIds]
    localStorage.setItem(storageKey, JSON.stringify(orderIds.value))
  }

  function persistTagOrder(root?: string) {
    localStorage.setItem(buildTagOrderKey(root), JSON.stringify(orderIds.value))
  }

  // Actions
  async function loadTags(root?: string) {
    isLoading.value = true
    lastLoadedRoot.value = root
    try {
      tags.value = await tagApi.getAll(root)
      syncTagOrder(root)
    } catch (error) {
      console.error('Failed to load tags:', error)
    } finally {
      isLoading.value = false
    }
  }

  async function reloadTags() {
    await loadTags(lastLoadedRoot.value)
  }

  async function createTag(name: string, color?: string, description?: string, workspace?: string, icon?: string) {
    try {
      const tag = await tagApi.create({ name, color, description, workspace, icon })
      tags.value.push(tag)
      syncTagOrder(workspace)
      return tag
    } catch (error) {
      console.error('Failed to create tag:', error)
      throw error
    }
  }

  async function updateTag(id: number, updates: Partial<Tag>) {
    try {
      const tag = await tagApi.update(id, updates)
      const index = tags.value.findIndex(t => t.id === id)
      if (index !== -1) {
        tags.value[index] = tag
      }
      return tag
    } catch (error) {
      console.error('Failed to update tag:', error)
      throw error
    }
  }

  async function deleteTag(id: number) {
    try {
      await tagApi.delete(id)
      tags.value = tags.value.filter(t => t.id !== id)
      selectedTagIds.value.delete(id)
      orderIds.value = orderIds.value.filter(tagId => tagId !== id)
      persistTagOrder(lastLoadedRoot.value)
    } catch (error) {
      console.error('Failed to delete tag:', error)
      throw error
    }
  }

  function selectTag(id: number, multi: boolean = false) {
    if (multi) {
      if (selectedTagIds.value.has(id)) {
        selectedTagIds.value.delete(id)
      } else {
        selectedTagIds.value.add(id)
      }
    } else {
      selectedTagIds.value.clear()
      selectedTagIds.value.add(id)
    }
  }

  function clearSelection() {
    selectedTagIds.value.clear()
  }

  function selectAll() {
    tags.value.forEach(t => selectedTagIds.value.add(t.id))
  }

  function getTagById(id: number): Tag | undefined {
    return tagMap.value.get(id)
  }

  function getTagsByIds(ids: number[]): Tag[] {
    return ids.map(id => tagMap.value.get(id)).filter((t): t is Tag => t !== undefined)
  }

  function reorderTags(draggedTagId: number, targetTagId?: number | null) {
    const currentOrder = [...orderedTags.value.map(tag => tag.id)]
    const draggedIndex = currentOrder.indexOf(draggedTagId)

    if (draggedIndex === -1) {
      return
    }

    currentOrder.splice(draggedIndex, 1)

    if (targetTagId == null) {
      currentOrder.push(draggedTagId)
    } else {
      const targetIndex = currentOrder.indexOf(targetTagId)
      if (targetIndex === -1) {
        currentOrder.push(draggedTagId)
      } else {
        currentOrder.splice(targetIndex, 0, draggedTagId)
      }
    }

    orderIds.value = currentOrder
    persistTagOrder(lastLoadedRoot.value)
  }

  async function assignTagsToFiles(fileIds: number[], tagIds: number[]) {
    const uniqueFileIds = Array.from(new Set(fileIds))
    const uniqueTagIds = Array.from(new Set(tagIds))

    if (!uniqueFileIds.length || !uniqueTagIds.length) {
      return { files: 0, tags: 0 }
    }

    try {
      const result = await tagApi.batchAssign(uniqueFileIds, uniqueTagIds)
      const fileStore = useFileStore()
      fileStore.addTagsToFiles(uniqueFileIds, uniqueTagIds)
      await reloadTags()
      return result
    } catch (error) {
      console.error('Failed to assign tags to files:', error)
      throw error
    }
  }

  return {
    tags,
    selectedTagIds,
    isLoading,
    tagMap,
    selectedTags,
    hasSelection,
    orderedTags,
    lastLoadedRoot,
    loadTags,
    reloadTags,
    createTag,
    updateTag,
    deleteTag,
    selectTag,
    clearSelection,
    selectAll,
    getTagById,
    getTagsByIds,
    reorderTags,
    assignTagsToFiles,
  }
})
