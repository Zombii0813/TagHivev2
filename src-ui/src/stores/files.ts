import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import type { FileSummary, SearchQuery } from '../types'
import { fileApi } from '../api/files'
import { folderApi } from '../api/folders'

export const useFileStore = defineStore('files', () => {
  // State
  const files = ref<FileSummary[]>([])
  const selectedIds = ref<Set<number>>(new Set())
  const searchQuery = ref<SearchQuery>({})
  const totalCount = ref(0)
  const hasMore = ref(false)
  const isLoading = ref(false)
  // 视图模式：grid（网格）或 list（列表）
  const viewMode = ref<'grid' | 'list'>('grid')
  // 浏览范围：folder（文件夹层级浏览）或 all（浏览所有文件）
  const browseMode = ref<'folder' | 'all'>('all')
  const sortBy = ref<string>('name')
  const sortDesc = ref(false)
  
  // 文件夹浏览模式状态
  const currentFolderPath = ref<string>('')
  const folderContentsOffset = ref(0)
  
  // 加载文件夹内容
  async function loadFolderContents(folderPath: string, append: boolean = false) {
    if (!append) {
      folderContentsOffset.value = 0
      files.value = []
    }
    
    currentFolderPath.value = folderPath
    isLoading.value = true
    
    try {
      const result = await folderApi.getContents(
        folderPath,
        folderContentsOffset.value,
        500,
        sortBy.value,
        sortDesc.value
      )
      
      if (append) {
        files.value.push(...result.files)
      } else {
        files.value = result.files
      }
      
      totalCount.value = result.total
      hasMore.value = result.has_more
    } catch (error) {
      console.error('Failed to load folder contents:', error)
    } finally {
      isLoading.value = false
    }
  }
  
  // 加载更多文件夹内容
  async function loadMoreFolderContents() {
    if (!hasMore.value || isLoading.value || !currentFolderPath.value) return
    
    folderContentsOffset.value = files.value.length
    await loadFolderContents(currentFolderPath.value, true)
  }
  
  // 扫描状态
  const isScanning = ref(false)
  const scanProgress = ref(0)
  const scanCount = ref(0)
  const scanTotal = ref(0)
  const scanCurrentFile = ref('')

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
  
  function setViewMode(mode: 'grid' | 'list') {
    viewMode.value = mode
  }

  function toggleBrowseMode() {
    browseMode.value = browseMode.value === 'folder' ? 'all' : 'folder'
  }
  
  function setBrowseMode(mode: 'folder' | 'all') {
    browseMode.value = mode
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

  function addTagsToFile(fileId: number, tagIds: number[]) {
    const file = files.value.find(f => f.id === fileId)
    if (file) {
      file.tag_ids = Array.from(new Set([...file.tag_ids, ...tagIds]))
    }
  }

  function addTagsToFiles(fileIds: number[], tagIds: number[]) {
    fileIds.forEach(fileId => {
      addTagsToFile(fileId, tagIds)
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
  
  // 扫描状态操作
  function startScanning() {
    isScanning.value = true
    scanProgress.value = 0
    scanCount.value = 0
    scanTotal.value = 0
    scanCurrentFile.value = ''
  }
  
  function updateScanProgress(count: number, total: number, percentage: number, currentFile?: string) {
    scanCount.value = count
    scanTotal.value = total
    scanProgress.value = percentage
    if (currentFile) {
      scanCurrentFile.value = currentFile
    }
  }
  
  function completeScanning() {
    isScanning.value = false
    scanProgress.value = 100
    scanCurrentFile.value = ''
  }
  
  function resetScanning() {
    isScanning.value = false
    scanProgress.value = 0
    scanCount.value = 0
    scanTotal.value = 0
    scanCurrentFile.value = ''
  }

  return {
    files,
    selectedIds,
    searchQuery,
    totalCount,
    hasMore,
    isLoading,
    viewMode,
    browseMode,
    sortBy,
    sortDesc,
    currentFolderPath,
    selectedFiles,
    selectedCount,
    hasSelection,
    isAllSelected,
    isScanning,
    scanProgress,
    scanCount,
    scanTotal,
    scanCurrentFile,
    search,
    loadMore,
    loadFolderContents,
    loadMoreFolderContents,
    selectFile,
    selectRange,
    selectAll,
    clearSelection,
    toggleViewMode,
    setViewMode,
    toggleBrowseMode,
    setBrowseMode,
    setSortBy,
    updateFileTags,
    updateBatchFileTags,
    addTagsToFile,
    addTagsToFiles,
    removeFile,
    removeBatchFiles,
    startScanning,
    updateScanProgress,
    completeScanning,
    resetScanning,
  }
})
