import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import type { FileItem, SearchQuery, SearchResult } from '../types'
import { fileApi } from '../api/files'

export const useFileStore = defineStore('files', () => {
  // State
  const files = ref<FileItem[]>([])
  const selectedIds = ref<Set<number>>(new Set())
  const searchQuery = ref<SearchQuery>({})
  const totalCount = ref(0)
  const hasMore = ref(false)
  const isLoading = ref(false)
  const viewMode = ref<'grid' | 'list'>('grid')
  const sortBy = ref<string>('name')
  const sortDesc = ref(false)

  // Getters
  const selectedFiles = computed(() => {
    return files.value.filter(f => selectedIds.value.has(f.id))
  })

  const selectedCount = computed(() => selectedIds.value.size)

  const hasSelection = computed(() => selectedIds.value.size > 0)

  const isAllSelected = computed(() => {
    return files.value.length > 0 && files.value.every(f => selectedIds.value.has(f.id))
  })

  // Actions
  async function search(query?: SearchQuery) {
    if (query) {
      searchQuery.value = query
    }

    isLoading.value = true
    try {
      const result = await fileApi.search({
        ...searchQuery.value,
        sort_by: sortBy.value,
        sort_desc: sortDesc.value,
      })
      
      files.value = result.files
      totalCount.value = result.total
      hasMore.value = result.has_more
    } catch (error) {
      console.error('Search failed:', error)
    } finally {
      isLoading.value = false
    }
  }

  async function loadMore() {
    if (!hasMore.value || isLoading.value) return

    isLoading.value = true
    try {
      const offset = files.value.length
      const result = await fileApi.search({
        ...searchQuery.value,
        offset,
        sort_by: sortBy.value,
        sort_desc: sortDesc.value,
      })
      
      files.value.push(...result.files)
      hasMore.value = result.has_more
    } catch (error) {
      console.error('Load more failed:', error)
    } finally {
      isLoading.value = false
    }
  }

  function selectFile(id: number, multi: boolean = false) {
    if (multi) {
      if (selectedIds.value.has(id)) {
        selectedIds.value.delete(id)
      } else {
        selectedIds.value.add(id)
      }
    } else {
      selectedIds.value.clear()
      selectedIds.value.add(id)
    }
  }

  function selectRange(startId: number, endId: number) {
    const startIndex = files.value.findIndex(f => f.id === startId)
    const endIndex = files.value.findIndex(f => f.id === endId)
    
    if (startIndex === -1 || endIndex === -1) return
    
    const [min, max] = startIndex < endIndex 
      ? [startIndex, endIndex] 
      : [endIndex, startIndex]
    
    for (let i = min; i <= max; i++) {
      selectedIds.value.add(files.value[i].id)
    }
  }

  function selectAll() {
    files.value.forEach(f => selectedIds.value.add(f.id))
  }

  function clearSelection() {
    selectedIds.value.clear()
  }

  function toggleViewMode() {
    viewMode.value = viewMode.value === 'grid' ? 'list' : 'grid'
  }

  function setSortBy(field: string) {
    if (sortBy.value === field) {
      sortDesc.value = !sortDesc.value
    } else {
      sortBy.value = field
      sortDesc.value = false
    }
    search()
  }

  function updateFileTags(fileId: number, tagIds: number[]) {
    const file = files.value.find(f => f.id === fileId)
    if (file) {
      file.tag_ids = tagIds
    }
  }

  function updateBatchFileTags(fileIds: number[], tagIds: number[]) {
    fileIds.forEach(fileId => {
      updateFileTags(fileId, tagIds)
    })
  }

  function removeFile(fileId: number) {
    const index = files.value.findIndex(f => f.id === fileId)
    if (index !== -1) {
      files.value.splice(index, 1)
      selectedIds.value.delete(fileId)
      totalCount.value--
    }
  }

  function removeBatchFiles(fileIds: number[]) {
    fileIds.forEach(fileId => {
      removeFile(fileId)
    })
  }

  return {
    files,
    selectedIds,
    searchQuery,
    totalCount,
    hasMore,
    isLoading,
    viewMode,
    sortBy,
    sortDesc,
    selectedFiles,
    selectedCount,
    hasSelection,
    isAllSelected,
    search,
    loadMore,
    selectFile,
    selectRange,
    selectAll,
    clearSelection,
    toggleViewMode,
    setSortBy,
    updateFileTags,
    updateBatchFileTags,
    removeFile,
    removeBatchFiles,
  }
})
