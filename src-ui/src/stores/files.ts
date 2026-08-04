import { ref, computed, watch } from 'vue'
import { defineStore } from 'pinia'
import type { FileSummary, SearchQuery, ChildDir, MediaInfo } from '../types'
import { fileApi } from '../api/files'
import { folderApi } from '../api/folders'
import { useTagStore } from './tags'
import { useAppStore } from './app'

// 视图偏好持久化（全局，不按工作区隔离）
const VIEW_PREF_KEY = 'taghive:view-prefs'
type ViewMode = 'grid' | 'list'
type BrowseMode = 'folder' | 'all' | 'tree' | 'explorer'

// 是否为「按目录层级浏览」的模式（folder/tree/explorer）——这些模式共享
// currentFolderPath 层级记忆与 loadFolderContents 加载逻辑，区别于 all（全部文件）。
function isFolderScoped(mode: BrowseMode): boolean {
  return mode === 'folder' || mode === 'tree' || mode === 'explorer'
}
interface ViewPrefs {
  viewMode: ViewMode
  browseMode: BrowseMode
  gridItemSize: number
  sortBy: string
  sortDesc: boolean
}
const VIEW_PREF_DEFAULTS: ViewPrefs = {
  viewMode: 'grid',
  browseMode: 'all',
  gridItemSize: 184,
  sortBy: 'name',
  sortDesc: false,
}
function loadViewPrefs(): ViewPrefs {
  try {
    const raw = localStorage.getItem(VIEW_PREF_KEY)
    if (!raw) return { ...VIEW_PREF_DEFAULTS }
    const parsed = JSON.parse(raw) as Partial<ViewPrefs>
    return {
      viewMode: parsed.viewMode === 'list' ? 'list' : 'grid',
      browseMode: parsed.browseMode === 'folder' || parsed.browseMode === 'tree' || parsed.browseMode === 'explorer'
        ? parsed.browseMode
        : 'all',
      gridItemSize: typeof parsed.gridItemSize === 'number'
        ? Math.max(80, Math.min(320, parsed.gridItemSize))
        : VIEW_PREF_DEFAULTS.gridItemSize,
      sortBy: typeof parsed.sortBy === 'string' ? parsed.sortBy : VIEW_PREF_DEFAULTS.sortBy,
      sortDesc: typeof parsed.sortDesc === 'boolean' ? parsed.sortDesc : VIEW_PREF_DEFAULTS.sortDesc,
    }
  } catch {
    return { ...VIEW_PREF_DEFAULTS }
  }
}

export const useFileStore = defineStore('files', () => {
  // 从 localStorage 恢复视图偏好
  const prefs = loadViewPrefs()

  // State
  const files = ref<FileSummary[]>([])
  const selectedIds = ref<Set<number>>(new Set())
  // 当前活动文件 id（最后点击的文件），用于右侧详情栏展示
  const activeId = ref<number | null>(null)
  const searchQuery = ref<SearchQuery>({})
  const totalCount = ref(0)
  const hasMore = ref(false)
  const isLoading = ref(false)
  // 视图模式：grid（网格）或 list（列表）
  const viewMode = ref<ViewMode>(prefs.viewMode)
  // 网格卡片固定尺寸（像素）
  const gridItemSize = ref(prefs.gridItemSize)
  // 浏览范围：folder（文件夹层级浏览）或 all（浏览所有文件）
  const browseMode = ref<BrowseMode>(prefs.browseMode)
  const sortBy = ref<string>(prefs.sortBy)
  const sortDesc = ref(prefs.sortDesc)

  // 任意视图偏好变化时持久化
  watch(
    [viewMode, browseMode, gridItemSize, sortBy, sortDesc],
    ([v, b, g, sb, sd]) => {
      try {
        localStorage.setItem(
          VIEW_PREF_KEY,
          JSON.stringify({ viewMode: v, browseMode: b, gridItemSize: g, sortBy: sb, sortDesc: sd })
        )
      } catch {
        // localStorage 满 / 隐私模式，忽略
      }
    }
  )
  
  // 文件夹浏览模式状态
  const currentFolderPath = ref<string>('')
  const folderContentsOffset = ref(0)
  // explorer 浏览模式：当前层的子目录（仅 explorer 模式加载，其他模式恒为空）
  const childDirs = ref<ChildDir[]>([])

  // 每个工作区最后浏览到的文件夹路径（会话内记忆）。
  // 用于切换工作区时恢复到上次浏览的层级，而非每次都回到根目录。
  const folderMemory = ref<Map<string, string>>(new Map())

  // 记住某工作区当前浏览的文件夹路径
  function rememberFolder(workspace: string, folderPath: string) {
    if (workspace && folderPath) {
      folderMemory.value.set(workspace, folderPath)
    }
  }

  // 读取某工作区记忆的浏览路径
  function getRememberedFolder(workspace: string): string | undefined {
    return folderMemory.value.get(workspace)
  }

  // 清除某工作区的浏览记忆（工作区被移除时调用）
  function forgetWorkspaceFolder(workspace: string) {
    folderMemory.value.delete(workspace)
  }
  
  // 加载文件夹内容
  async function loadFolderContents(folderPath: string, append: boolean = false) {
    if (!append) {
      folderContentsOffset.value = 0
      files.value = []
      childDirs.value = []
    }

    currentFolderPath.value = folderPath
    isLoading.value = true

    // 仅 explorer 模式请求子目录，且只在首页请求（分页加载更多文件时无需重复）
    const wantDirs = browseMode.value === 'explorer' && !append

    try {
      const result = await folderApi.getContents(
        folderPath,
        folderContentsOffset.value,
        500,
        sortBy.value,
        sortDesc.value,
        wantDirs
      )

      if (append) {
        files.value.push(...result.files)
      } else {
        files.value = result.files
      }

      if (wantDirs) {
        childDirs.value = result.dirs ?? []
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

  // 当前活动文件（最后点击的文件）；不存在时回退到首个选中项
  const activeFile = computed(() => {
    if (activeId.value !== null) {
      const f = files.value.find(file => file.id === activeId.value)
      if (f) return f
    }
    return selectedFiles.value[0]
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

    // search 语义为跨层级文件检索（含标签过滤），不属于目录层级浏览，
    // 故清空 explorer 的子目录卡片——与树窗/蜂巢过滤态只显示文件保持一致。
    // 取消过滤后经 reloadCurrentView → loadFolderContents 重新加载目录卡片。
    childDirs.value = []

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
        // 取消选中活动文件时，活动文件回退到其余选中项的首个
        if (activeId.value === id) {
          activeId.value = selectedFiles.value[0]?.id ?? null
        }
      } else {
        selectedIds.value.add(id)
        activeId.value = id
      }
    } else {
      selectedIds.value.clear()
      selectedIds.value.add(id)
      activeId.value = id
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
    // 活动文件更新为范围终点
    activeId.value = endId
  }

  function selectAll() {
    files.value.forEach(f => selectedIds.value.add(f.id))
  }

  function clearSelection() {
    selectedIds.value.clear()
    activeId.value = null
  }

  function toggleViewMode() {
    viewMode.value = viewMode.value === 'grid' ? 'list' : 'grid'
  }
  
  function setViewMode(mode: ViewMode) {
    viewMode.value = mode
  }

  function setGridItemSize(size: number) {
    gridItemSize.value = Math.max(80, Math.min(320, size))
  }

  function toggleBrowseMode() {
    // 四态循环：全部文件 → 蜂巢导航 → 文件夹树窗 → 资源管理器 → 全部文件
    const order: BrowseMode[] = ['all', 'folder', 'tree', 'explorer']
    const i = order.indexOf(browseMode.value)
    browseMode.value = order[(i + 1) % order.length]
  }

  function setBrowseMode(mode: BrowseMode) {
    browseMode.value = mode
  }

  // 按当前浏览上下文重新加载文件列表（排序变更后调用）。
  //
  // 排序必须在「当前视图」内生效，不能一律走全部文件搜索，否则蜂巢/树窗
  // 模式下处于子目录层级时改排序会跳回全部文件。三种上下文各自的重载方式：
  //   1. 标签过滤态：保留过滤条件重跑 search（loadFolderContents 不带 tag 过滤）
  //   2. 蜂巢/树窗且已进入某层级：在当前文件夹层级内按新排序重载
  //   3. 其余（全部文件模式）：按工作区根搜索全部文件
  // 计算标签过滤应使用的路径范围（后端按此前缀递归匹配）：
  //   - 全部文件模式：工作区根，显示该标签在整个工作区下的文件
  //   - 蜂巢/树窗模式：当前浏览层级（未进入子目录时退回工作区根），
  //     仅显示当前目录层级下（含子目录）该标签的文件
  // 使得标签过滤范围始终与当前浏览模式/层级保持同步。
  function resolveTagFilterRoot(): string | undefined {
    const appStore = useAppStore()
    if (isFolderScoped(browseMode.value) && currentFolderPath.value) {
      return currentFolderPath.value
    }
    return appStore.currentWorkspace || undefined
  }

  // 按当前浏览上下文对选中标签执行过滤搜索。
  // folderContext 显式指定层级上下文（切换浏览模式时传入）：
  //   传入非空路径 → 同步 currentFolderPath 为该层级（供取消标签后恢复）；
  //   传入空串     → 全部文件模式，清空层级上下文；
  //   不传（undefined）→ 沿用当前 currentFolderPath。
  async function filterByTags(tagIds: number[], folderContext?: string) {
    if (folderContext !== undefined) {
      currentFolderPath.value = folderContext
    }
    await search({
      root: resolveTagFilterRoot(),
      tags: tagIds,
      match_all_tags: false,
    })
  }

  async function reloadCurrentView() {
    // useTagStore/useAppStore 仅在函数内调用（非模块顶层），
    // 故与 tags/app store 的循环静态引用不会在模块求值期触发问题
    const tagStore = useTagStore()
    const appStore = useAppStore()

    if (tagStore.hasSelection) {
      // 标签过滤态：root 按当前浏览层级重算（排序变更不改层级，行为等价，但更稳健），
      // 保留 searchQuery 中的文本/类型等其它过滤条件。
      await search({
        ...searchQuery.value,
        root: resolveTagFilterRoot(),
        tags: Array.from(tagStore.effectiveTagIds),
        match_all_tags: false,
      })
      return
    }

    if (isFolderScoped(browseMode.value) && currentFolderPath.value) {
      await loadFolderContents(currentFolderPath.value)
      return
    }

    await search({ root: appStore.currentWorkspace || undefined })
  }

  // 切换排序字段：同字段切换升/降序，异字段切换到升序，随后按当前视图重载
  function setSortBy(field: string) {
    if (sortBy.value === field) {
      sortDesc.value = !sortDesc.value
    } else {
      sortBy.value = field
      sortDesc.value = false
    }
    reloadCurrentView()
  }

  // 明确指定排序字段与方向，随后按当前视图重载
  function setSort(field: string, desc: boolean) {
    sortBy.value = field
    sortDesc.value = desc
    reloadCurrentView()
  }

  // 回填惰性探测得到的媒体元数据，避免同一会话内重复请求
  function updateFileMediaInfo(fileId: number, info: MediaInfo) {
    const file = files.value.find(f => f.id === fileId)
    if (!file) return
    file.duration = info.duration
    file.width = info.width
    file.height = info.height
    file.bitrate = info.bitrate
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

  function removeTagFromAllFiles(tagId: number) {
    files.value.forEach(file => {
      const idx = file.tag_ids.indexOf(tagId)
      if (idx !== -1) {
        file.tag_ids.splice(idx, 1)
      }
    })
  }

  function removeTagFromFiles(fileIds: number[], tagId: number) {
    const idSet = new Set(fileIds)
    files.value.forEach(file => {
      if (!idSet.has(file.id)) return
      const idx = file.tag_ids.indexOf(tagId)
      if (idx !== -1) {
        file.tag_ids.splice(idx, 1)
      }
    })
  }

  function removeFile(fileId: number) {
    const index = files.value.findIndex(f => f.id === fileId)
    if (index !== -1) {
      files.value.splice(index, 1)
      selectedIds.value.delete(fileId)
      if (activeId.value === fileId) {
        activeId.value = selectedFiles.value[0]?.id ?? null
      }
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
    activeId,
    searchQuery,
    totalCount,
    hasMore,
    isLoading,
    viewMode,
    browseMode,
    gridItemSize,
    sortBy,
    sortDesc,
    currentFolderPath,
    childDirs,
    selectedFiles,
    activeFile,
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
    rememberFolder,
    getRememberedFolder,
    forgetWorkspaceFolder,
    selectFile,
    selectRange,
    selectAll,
    clearSelection,
    toggleViewMode,
    setViewMode,
    setGridItemSize,
    toggleBrowseMode,
    setBrowseMode,
    setSortBy,
    setSort,
    reloadCurrentView,
    filterByTags,
    updateFileMediaInfo,
    updateFileTags,
    updateBatchFileTags,
    addTagsToFile,
    addTagsToFiles,
    removeTagFromAllFiles,
    removeTagFromFiles,
    removeFile,
    removeBatchFiles,
    startScanning,
    updateScanProgress,
    completeScanning,
    resetScanning,
  }
})
