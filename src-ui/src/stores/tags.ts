import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import type { Tag } from '../types'
import { tagApi } from '../api/tags'

export const useTagStore = defineStore('tags', () => {
  // State
  const tags = ref<Tag[]>([])
  const selectedTagIds = ref<Set<number>>(new Set())
  const isLoading = ref(false)

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

  // Actions
  async function loadTags(root?: string) {
    isLoading.value = true
    try {
      tags.value = await tagApi.getAll(root)
    } catch (error) {
      console.error('Failed to load tags:', error)
    } finally {
      isLoading.value = false
    }
  }

  async function createTag(name: string, color?: string, description?: string) {
    try {
      const tag = await tagApi.create({ name, color, description })
      tags.value.push(tag)
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

  return {
    tags,
    selectedTagIds,
    isLoading,
    tagMap,
    selectedTags,
    hasSelection,
    loadTags,
    createTag,
    updateTag,
    deleteTag,
    selectTag,
    clearSelection,
    selectAll,
    getTagById,
    getTagsByIds,
  }
})
