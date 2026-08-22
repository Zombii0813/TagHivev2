import { ref, computed, watch, nextTick } from 'vue'
import { defineStore } from 'pinia'
import type { FileSummary, SearchQuery, ChildDir, MediaInfo } from '../types'
import { fileApi } from '../api/files'
import { folderApi } from '../api/folders'
import { useTagStore } from './tags'
import { useAppStore } from './app'
import type { BrowseMode, TabState } from './browserTabs'
import {
  createTab,
  fromPersisted,
  loadPersistedTabs,
  persistTabs,
  toPersisted,
  MAX_TABS,
} from './browserTabs'
import { isItemDragInProgress } from '../utils/dragItems'

// 视图偏好持久化（全局，不按工作区隔离）
const VIEW_PREF_KEY = 'taghive:view-prefs'
type ViewMode = 'grid' | 'list'

// 是否为「按目录层级浏览」的模式（folder/tree/explorer）——这些模式共享
// currentFolderPath 层级记忆与 loadFolderContents 加载逻辑，区别于 all（全部文件）。
function isFolderScoped(mode: BrowseMode): boolean {
  return mode === 'folder' || mode === 'tree' || mode === 'explorer'
}

// 两次触底加载之间的最小间隔（毫秒），见 tryLoadMore 注释
const LOAD_MORE_COOLDOWN = 400

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

  // ══════════════════════════════════════════════════════════════
  // 标签页状态
  //
  // 「浏览位置」相关状态（目录、模式、列表、选中项、滚动位置）全部收进
  // TabState，由下方可写 computed 代理暴露为原来的扁平字段名，
  // 使既有的 155 处 fileStore.xxx 引用无需改动。
  //
  // 不变量（下方所有代理都依赖它，破坏即静默丢数据）：
  //   tabOrder.length >= 1，且其中每个 id 都能在 tabs 中取到，
  //   故 activeTab 永远返回真实对象，绝不返回临时兜底对象。
  // ══════════════════════════════════════════════════════════════
  const tabs = ref<Map<string, TabState>>(new Map())
  const tabOrder = ref<string[]>([])
  const activeTabId = ref<string>('')

  // 全局层级记忆的初始内容，由下方标签页恢复块填充。
  // 单独一个 Map 而非直接写 folderMemory：后者声明在文件更下方（紧邻其读写
  // 函数便于阅读），此处尚不可用。
  const _folderMemoryInit = new Map<string, string>()

  // 恢复上次会话的标签页；没有落盘数据时建一个空白标签页。
  //
  // 恢复出的标签页 loaded=false，数据不在此刻加载：store 初始化时 appStore
  // 尚未恢复工作区，且 N 个标签页同时请求会拖慢启动。活动标签页的数据由
  // BrowserView 的 currentWorkspace watcher 在工作区恢复后加载，其余标签页
  // 等切过去时由 ensureTabLoaded 惰性加载。
  //
  // 落盘的工作区是否还存在此刻也无从判断（appStore 尚未 initialize），
  // 由 App.vue 在 initialize 完成后调 pruneInvalidTabs 剔除。
  //
  // 无落盘数据时新建的标签页 workspace 留空，由 BrowserView 挂载时补齐，
  // 与改造前 currentFolderPath 初始为 '' 一致。
  {
    const persisted = loadPersistedTabs()
    for (const p of persisted.tabs) {
      const tab = fromPersisted(p)
      tabs.value.set(tab.id, tab)
      tabOrder.value.push(tab.id)
      // 顺带把层级种进全局记忆，供移动/复制对话框与侧栏工作区落点推断默认
      // 目标目录——否则重启后第一次拖到侧栏只会落到工作区根。按顺序写入，
      // 同工作区多标签页时靠右的覆盖靠左的。
      if (p.workspace && p.currentFolderPath) {
        _folderMemoryInit.set(p.workspace, p.currentFolderPath)
      }
    }
    if (tabOrder.value.length === 0) {
      const first = createTab({ workspace: '', browseMode: prefs.browseMode })
      tabs.value.set(first.id, first)
      tabOrder.value.push(first.id)
    }
    activeTabId.value = persisted.activeId ?? tabOrder.value[0]
  }

  /**
   * 当前激活的标签页。
   *
   * 取不到时回退到第一个标签页而非新建对象：代理 computed 若在兜底分支
   * 返回 new Set()/[]，每次求值都是新引用，框选的 .add() 会写进临时对象后
   * 立刻被丢弃，且没有任何报错。
   */
  const activeTab = computed<TabState>(() => {
    const t = tabs.value.get(activeTabId.value)
    if (t) return t
    return tabs.value.get(tabOrder.value[0])!
  })

  /**
   * 按 id 取标签页，缺省取当前激活的。
   *
   * 所有 async action 都在入口处调用一次并持有返回值：若在 await 之后
   * 才通过 activeTab 取，标签页 A 发起的请求在切到 B 后 resolve，
   * 就会把 A 的数据写进 B。
   *
   * @param tabId 目标标签页 id；不传或已关闭时取当前激活标签页
   * @returns 标签页状态对象
   */
  function getTab(tabId?: string): TabState {
    if (tabId) {
      const t = tabs.value.get(tabId)
      if (t) return t
    }
    return activeTab.value
  }

  /** 有序的标签页列表，供标签栏渲染 */
  const tabList = computed<TabState[]>(() =>
    tabOrder.value.map(id => tabs.value.get(id)!).filter(Boolean)
  )

  /**
   * 是否正在切换标签页。
   *
   * 组件里若干 watcher 监听 browseMode / currentFolderPath 等代理字段并据此
   * 重新加载数据——那是为「用户主动改变浏览模式」设计的。切换标签页同样会
   * 让这些代理值变化，但此时数据由 switchTab 自行按目标标签页恢复，
   * watcher 再插一脚就会用「上次记忆的层级」覆盖掉目标标签页自己的位置。
   * 这些 watcher 需在入口检查本标志并直接返回。
   */
  const isSwitchingTab = ref(false)

  // ── 按标签页隔离的字段：可写 computed 代理 ──
  const files = computed<FileSummary[]>({
    get: () => activeTab.value.files,
    set: (v) => { activeTab.value.files = v },
  })
  const childDirs = computed<ChildDir[]>({
    get: () => activeTab.value.childDirs,
    set: (v) => { activeTab.value.childDirs = v },
  })
  const totalCount = computed<number>({
    get: () => activeTab.value.totalCount,
    set: (v) => { activeTab.value.totalCount = v },
  })
  const hasMore = computed<boolean>({
    get: () => activeTab.value.hasMore,
    set: (v) => { activeTab.value.hasMore = v },
  })
  const isLoading = computed<boolean>({
    get: () => activeTab.value.isLoading,
    set: (v) => { activeTab.value.isLoading = v },
  })
  const selectedIds = computed<Set<number>>({
    get: () => activeTab.value.selectedIds,
    set: (v) => { activeTab.value.selectedIds = v },
  })
  const activeId = computed<number | null>({
    get: () => activeTab.value.activeId,
    set: (v) => { activeTab.value.activeId = v },
  })
  const searchQuery = computed<SearchQuery>({
    get: () => activeTab.value.searchQuery,
    set: (v) => { activeTab.value.searchQuery = v },
  })
  const currentFolderPath = computed<string>({
    get: () => activeTab.value.currentFolderPath,
    set: (v) => { activeTab.value.currentFolderPath = v },
  })
  const browseMode = computed<BrowseMode>({
    get: () => activeTab.value.browseMode,
    set: (v) => { activeTab.value.browseMode = v },
  })

  // ── 全局视图偏好（所有标签页共享）──
  const viewMode = ref<ViewMode>(prefs.viewMode)
  const gridItemSize = ref(prefs.gridItemSize)
  const sortBy = ref<string>(prefs.sortBy)
  const sortDesc = ref(prefs.sortDesc)

  // 任意视图偏好变化时持久化。browseMode 现在是代理 computed，
  // 切换标签页也会触发一次写入——落盘值即「最近使用的浏览模式」，
  // 正好作为新建标签页的默认模式。
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

  /*
   * 标签页落盘。
   *
   * 只跟随「浏览位置」类字段变化写入（见 toPersisted 的字段子集）：列表数据与
   * 选中项不落盘，故不必监听 files/selectedIds —— 那些每次加载都变，
   * 监听它们等于每次滚动分页都写一次 localStorage。
   *
   * flush: 'post' 避免在同一次切换标签页的多字段变更中写多遍。
   */
  watch(
    // 侦听源取 toPersisted 的序列化结果：落盘字段单点定义在那里，
    // 此处无需再维护一份字段清单，日后增减字段不会两边走偏
    () => JSON.stringify({
      tabs: tabList.value.map(toPersisted),
      activeId: activeTabId.value,
    }),
    () => {
      persistTabs(tabList.value, activeTabId.value)
    },
    { flush: 'post' }
  )

  // 每个工作区最后浏览到的文件夹路径。
  // 用于切换工作区时恢复到上次浏览的层级，而非每次都回到根目录。
  // 初值取自恢复出的标签页层级，故跨会话也有效（见上方标签页恢复块）。
  const folderMemory = ref<Map<string, string>>(_folderMemoryInit)

  /**
   * 记住某工作区当前浏览的文件夹路径。
   *
   * 同时写两处：标签页自己的 folderByWorkspace（用于本标签页恢复层级）
   * 与全局 folderMemory（仅供移动/复制对话框推断默认目标目录）。
   *
   * @param workspace 工作区根路径
   * @param folderPath 当前浏览的目录路径
   * @param tabId 目标标签页；不传则为当前激活标签页
   */
  function rememberFolder(workspace: string, folderPath: string, tabId?: string) {
    if (!workspace || !folderPath) return
    folderMemory.value.set(workspace, folderPath)
    getTab(tabId).folderByWorkspace[workspace] = folderPath
  }

  /**
   * 取本标签页在某工作区上次浏览到的层级。
   *
   * 与 getRememberedFolder 的区别：后者是全局共享的，会取到其它标签页
   * 刚写入的路径——切换浏览模式时用它会让本标签页跳到别的标签页的位置。
   *
   * @param workspace 工作区根路径
   * @param tabId 目标标签页；不传则为当前激活标签页
   * @returns 记忆的目录路径，没有则 undefined
   */
  function getTabFolder(workspace: string, tabId?: string): string | undefined {
    return getTab(tabId).folderByWorkspace[workspace]
  }

  // 读取某工作区记忆的浏览路径
  function getRememberedFolder(workspace: string): string | undefined {
    return folderMemory.value.get(workspace)
  }

  // 清除某工作区的浏览记忆（工作区被移除时调用）
  function forgetWorkspaceFolder(workspace: string) {
    folderMemory.value.delete(workspace)
  }

  /**
   * 加载文件夹内容。
   *
   * @param folderPath 目标文件夹绝对路径
   * @param append 是否追加（分页加载更多）
   * @param tabId 目标标签页；不传则为当前激活标签页
   */
  async function loadFolderContents(folderPath: string, append: boolean = false, tabId?: string) {
    const tab = getTab(tabId)

    if (!append) {
      tab.folderContentsOffset = 0
      tab.files = []
      tab.childDirs = []
      // 换了目录，旧的滚动位置对新列表无意义；不清零会在切走再切回时
      // 把上一个目录的偏移恢复到这个目录上
      tab.scrollTop = 0
    }

    tab.currentFolderPath = folderPath
    tab.isLoading = true

    // 仅 explorer 模式请求子目录，且只在首页请求（分页加载更多文件时无需重复）
    const wantDirs = tab.browseMode === 'explorer' && !append

    try {
      const result = await folderApi.getContents(
        folderPath,
        tab.folderContentsOffset,
        500,
        sortBy.value,
        sortDesc.value,
        wantDirs
      )

      if (append) {
        tab.files.push(...result.files)
      } else {
        tab.files = result.files
      }

      if (wantDirs) {
        tab.childDirs = result.dirs ?? []
      }

      tab.totalCount = result.total
      tab.hasMore = result.has_more
      tab.loaded = true
      tab.dirty = false
    } catch (error) {
      console.error('Failed to load folder contents:', error)
    } finally {
      tab.isLoading = false
    }
  }

  // 加载更多文件夹内容
  async function loadMoreFolderContents(tabId?: string) {
    const tab = getTab(tabId)
    if (!tab.hasMore || tab.isLoading || !tab.currentFolderPath) return

    tab.folderContentsOffset = tab.files.length
    await loadFolderContents(tab.currentFolderPath, true, tab.id)
  }

  /**
   * 触底加载下一页，按标签页独立冷却。
   *
   * 冷却窗口必须存在：RecycleScroller 的 scroll-end 在最后一个 item 进入渲染
   * 范围时就 emit，框选自动滚动贴底时几乎每帧触发，不节流会连续串行翻页几十次，
   * 把后端 COUNT + 全表重排与缩略图请求打满。
   *
   * 时间戳存在标签页上而非模块级变量：模块级变量被所有标签页共用，
   * 在 A 标签页刚翻过页后切到 B 立刻触底，B 会被 A 的冷却挡掉一次加载。
   *
   * @param tabId 目标标签页；不传则为当前激活标签页
   */
  async function tryLoadMore(tabId?: string) {
    const tab = getTab(tabId)
    if (!tab.hasMore || tab.isLoading) return

    const now = performance.now()
    if (now - tab.lastLoadMoreAt < LOAD_MORE_COOLDOWN) return
    tab.lastLoadMoreAt = now

    const tagStore = useTagStore()
    const inFolderContext =
      isFolderScoped(tab.browseMode) && !tagStore.hasSelection && !!tab.currentFolderPath

    if (inFolderContext) {
      await loadMoreFolderContents(tab.id)
    } else {
      await loadMore(tab.id)
    }
  }

  /**
   * 把除指定标签页外的所有标签页标记为脏，待切换过去时惰性重载。
   *
   * 扫描完成、批量删除等会影响全局数据的事件后调用：非活动标签页此刻重载
   * 纯属浪费（用户看不到，且 N 个标签页并发请求会把后端打满），只在真正
   * 切过去时由 ensureTabLoaded 重载一次。
   *
   * @param exceptTabId 不标记的标签页 id；通常传当前激活标签页（它会立即重载）
   */
  function markTabsDirty(exceptTabId?: string) {
    for (const tab of tabs.value.values()) {
      if (tab.id === exceptTabId) continue
      tab.dirty = true
    }
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

  /** 取某标签页中首个仍被选中的文件 id（删除文件后回退活动项用） */
  function _firstSelectedId(tab: TabState): number | null {
    for (const f of tab.files) {
      if (tab.selectedIds.has(f.id)) return f.id
    }
    return null
  }

  // Actions
  async function search(query?: SearchQuery, tabId?: string) {
    const tab = getTab(tabId)

    if (query) {
      tab.searchQuery = query
    }

    // search 语义为跨层级文件检索（含标签过滤），不属于目录层级浏览，
    // 故清空 explorer 的子目录卡片——与树窗/蜂巢过滤态只显示文件保持一致。
    // 取消过滤后经 reloadCurrentView → loadFolderContents 重新加载目录卡片。
    tab.childDirs = []
    // 结果集整体更换，旧滚动位置无意义
    tab.scrollTop = 0

    tab.isLoading = true
    try {
      const result = await fileApi.search({
        ...tab.searchQuery,
        sort_by: sortBy.value,
        sort_desc: sortDesc.value,
      })

      tab.files = result.files
      tab.totalCount = result.total
      tab.hasMore = result.has_more
      tab.loaded = true
      tab.dirty = false
    } catch (error) {
      console.error('Search failed:', error)
    } finally {
      tab.isLoading = false
    }
  }

  async function loadMore(tabId?: string) {
    const tab = getTab(tabId)
    if (!tab.hasMore || tab.isLoading) return

    tab.isLoading = true
    try {
      const offset = tab.files.length
      const result = await fileApi.search({
        ...tab.searchQuery,
        offset,
        sort_by: sortBy.value,
        sort_desc: sortDesc.value,
      })

      tab.files.push(...result.files)
      tab.hasMore = result.has_more
    } catch (error) {
      console.error('Load more failed:', error)
    } finally {
      tab.isLoading = false
    }
  }

  function selectFile(id: number, multi: boolean = false, tabId?: string) {
    const tab = getTab(tabId)
    if (multi) {
      if (tab.selectedIds.has(id)) {
        tab.selectedIds.delete(id)
        // 取消选中活动文件时，活动文件回退到其余选中项的首个
        if (tab.activeId === id) {
          tab.activeId = _firstSelectedId(tab)
        }
      } else {
        tab.selectedIds.add(id)
        tab.activeId = id
      }
    } else {
      tab.selectedIds.clear()
      tab.selectedIds.add(id)
      tab.activeId = id
    }
  }

  function selectRange(startId: number, endId: number, tabId?: string) {
    const tab = getTab(tabId)
    const startIndex = tab.files.findIndex(f => f.id === startId)
    const endIndex = tab.files.findIndex(f => f.id === endId)

    if (startIndex === -1 || endIndex === -1) return

    const [min, max] = startIndex < endIndex
      ? [startIndex, endIndex]
      : [endIndex, startIndex]

    for (let i = min; i <= max; i++) {
      tab.selectedIds.add(tab.files[i].id)
    }
    // 活动文件更新为范围终点
    tab.activeId = endId
  }

  function selectAll(tabId?: string) {
    const tab = getTab(tabId)
    tab.files.forEach(f => tab.selectedIds.add(f.id))
  }

  function clearSelection(tabId?: string) {
    const tab = getTab(tabId)
    tab.selectedIds.clear()
    tab.activeId = null
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

  function toggleBrowseMode(tabId?: string) {
    // 四态循环：全部文件 → 蜂巢导航 → 文件夹树窗 → 资源管理器 → 全部文件
    const tab = getTab(tabId)
    const order: BrowseMode[] = ['all', 'folder', 'tree', 'explorer']
    const i = order.indexOf(tab.browseMode)
    tab.browseMode = order[(i + 1) % order.length]
  }

  function setBrowseMode(mode: BrowseMode, tabId?: string) {
    getTab(tabId).browseMode = mode
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
  function resolveTagFilterRoot(tab: TabState): string | undefined {
    const appStore = useAppStore()
    if (isFolderScoped(tab.browseMode) && tab.currentFolderPath) {
      return tab.currentFolderPath
    }
    return appStore.currentWorkspace || undefined
  }

  // 按当前浏览上下文对选中标签执行过滤搜索。
  // folderContext 显式指定层级上下文（切换浏览模式时传入）：
  //   传入非空路径 → 同步 currentFolderPath 为该层级（供取消标签后恢复）；
  //   传入空串     → 全部文件模式，清空层级上下文；
  //   不传（undefined）→ 沿用当前 currentFolderPath。
  async function filterByTags(tagIds: number[], folderContext?: string, tabId?: string) {
    const tab = getTab(tabId)
    if (folderContext !== undefined) {
      tab.currentFolderPath = folderContext
    }
    await search({
      root: resolveTagFilterRoot(tab),
      tags: tagIds,
      match_all_tags: false,
    }, tab.id)
  }

  async function reloadCurrentView(tabId?: string) {
    // useTagStore/useAppStore 仅在函数内调用（非模块顶层），
    // 故与 tags/app store 的循环静态引用不会在模块求值期触发问题
    const tagStore = useTagStore()
    const appStore = useAppStore()
    const tab = getTab(tabId)

    if (tagStore.hasSelection) {
      // 标签过滤态：root 按当前浏览层级重算（排序变更不改层级，行为等价，但更稳健），
      // 保留 searchQuery 中的文本/类型等其它过滤条件。
      await search({
        ...tab.searchQuery,
        root: resolveTagFilterRoot(tab),
        tags: Array.from(tagStore.effectiveTagIds),
        match_all_tags: false,
      }, tab.id)
      return
    }

    if (isFolderScoped(tab.browseMode) && tab.currentFolderPath) {
      await loadFolderContents(tab.currentFolderPath, false, tab.id)
      return
    }

    // 带上该标签页自己的搜索条件：跨会话恢复出的标签页 searchQuery 为空
    // （不落盘），只落了 searchText/searchType，若此处不重建条件，搜索框
    // 有词而列表是全量，看起来像搜索失效。
    // root 取标签页自身工作区而非 appStore：重载非活动标签页时 appStore
    // 未必已同步到它的工作区。
    await search({
      // workspace 尚未补齐时（启动早期）退回 appStore，与改造前一致
      root: tab.isGlobalView
        ? undefined
        : (tab.workspace || appStore.currentWorkspace || undefined),
      text: tab.searchText || undefined,
      types: tab.searchType ? [tab.searchType] : undefined,
    }, tab.id)
  }

  // ══════════════════════════════════════════════════════════════
  // 标签页操作
  // ══════════════════════════════════════════════════════════════

  /**
   * 视图层注册的滚动读写钩子。
   *
   * store 不碰 DOM，但切换标签页时「存旧位置」必须发生在 activeTabId 改变
   * 之前（改后 DOM 立刻按新标签页数据 patch，旧位置已被夹掉），
   * 「恢复新位置」又必须在数据落地之后——这个时序只有 switchTab 内部知道，
   * 用 watcher 在组件侧做不到，故由视图注册钩子交给 store 调度。
   */
  let scrollHooks: { capture: () => number; restore: (top: number) => void } | null = null

  /**
   * 注册滚动位置读写钩子（由 BrowserView 在挂载时调用）。
   *
   * @param hooks capture 读当前视图滚动位置；restore 恢复到指定位置
   * @returns 注销函数
   */
  function registerScrollHooks(hooks: {
    capture: () => number
    restore: (top: number) => void
  }): () => void {
    scrollHooks = hooks
    return () => {
      if (scrollHooks === hooks) scrollHooks = null
    }
  }

  /**
   * 把当前视图的滚动位置存入指定标签页。
   *
   * 只认确实存在的标签页，不走 getTab 的兜底：closeTab 会先把 activeTabId
   * 置空再切走，兜底会把即将关闭标签页的滚动位置写到 tabOrder[0] 上去。
   *
   * @param tabId 目标标签页 id
   */
  function captureTabScroll(tabId?: string) {
    if (!scrollHooks || !tabId) return
    const tab = tabs.value.get(tabId)
    if (!tab) return
    tab.scrollTop = scrollHooks.capture()
  }

  /**
   * 确保标签页已有数据，尚未加载或已过期时按其自身浏览上下文加载。
   *
   * @param tabId 目标标签页 id
   */
  async function ensureTabLoaded(tabId?: string) {
    const tab = getTab(tabId)
    if (tab.loaded && !tab.dirty) return
    // 拖拽期间不做「过期重载」：重载会换掉 files 数组，被拖拽的源卡片随之卸载，
    // 绑在它上面的 dragend 永不触发，拖拽状态残留。dirty 保持置位，
    // 拖拽结束后由 refreshDirtyActiveTab 补上。
    // 但从未加载过的标签页仍要加载——否则悬停切过去是一片空白。
    if (tab.loaded && isItemDragInProgress()) return
    await reloadCurrentView(tab.id)
  }

  /**
   * 拖拽结束后补上被跳过的过期重载。
   *
   * 由视图在 window dragend/drop 时调用；此刻拖拽状态已被兜底清理清空，
   * ensureTabLoaded 不会再跳过。
   */
  async function refreshDirtyActiveTab() {
    const tab = activeTab.value
    if (!tab.dirty) return
    await reloadCurrentView(tab.id)
  }

  /**
   * 切换到指定标签页。
   *
   * 先置 isSwitchingTab 抑制组件 watcher，等一轮 flush 让它们空转掉，
   * 再按目标标签页自身的工作区与位置恢复数据。
   *
   * 工作区归标签页所有：appStore 的 activeWorkspace/isGlobalView 是
   * 「当前标签页的工作区」的投影，切换标签页时反向同步过去，
   * 侧栏高亮、标签面板、蜂巢导航等消费方无需各自感知标签页。
   *
   * @param tabId 目标标签页 id
   */
  async function switchTab(tabId: string) {
    if (!tabs.value.has(tabId) || tabId === activeTabId.value) return

    const appStore = useAppStore()
    const tagStore = useTagStore()

    // 必须在 activeTabId 改变前读：改后 DOM 立即按新标签页数据重绘，
    // 此时读到的是新列表的滚动位置（多为 0），旧位置就丢了
    captureTabScroll(activeTabId.value)

    isSwitchingTab.value = true
    activeTabId.value = tabId
    const tab = tabs.value.get(tabId)!

    try {
      const wsChanged =
        tab.workspace !== (appStore.activeWorkspace || '') ||
        tab.isGlobalView !== appStore.isGlobalView

      if (wsChanged) {
        // 同步 appStore 到该标签页所属工作区
        if (tab.isGlobalView) {
          appStore.setGlobalView(true)
        } else if (tab.workspace) {
          appStore.switchWorkspace(tab.workspace)
        }
        // 标签按工作区隔离，跨工作区切换需重载标签树并清除过滤
        tagStore.clearSelection()
        await tagStore.loadTags(tab.workspace || undefined)
      }

      // 先取出目标位置：脏标签页会走重载，而重载（loadFolderContents/search）
      // 会把 scrollTop 归零，等它跑完再读就只剩 0 了
      const targetScroll = tab.scrollTop

      // watcher 默认在 pre flush 时机触发，这里让它们先跑完并因标志位返回
      await nextTick()
      await ensureTabLoaded(tabId)
      // 数据落地后再恢复滚动位置：虚拟滚动容器的高度由列表长度撑起，
      // 数据未就位时赋值会被夹到 0
      scrollHooks?.restore(targetScroll)
    } finally {
      isSwitchingTab.value = false
    }
  }

  /**
   * 新建标签页并切换过去。
   *
   * @param init 初始字段；不传 workspace 时沿用当前标签页的工作区
   * @returns 新标签页 id；已达数量上限时返回空串
   */
  async function addTab(init?: Partial<TabState>): Promise<string> {
    if (tabOrder.value.length >= MAX_TABS) return ''

    const current = activeTab.value
    const workspace = init?.workspace ?? current.workspace
    // 逐字段取值而非 { ...defaults, ...init }：后者在 init 显式带
    // undefined 字段时会把算好的默认值冲掉
    const tab = createTab({
      workspace,
      isGlobalView: init?.isGlobalView ?? current.isGlobalView,
      // 沿用当前标签页的浏览模式，位置则回到工作区根目录
      browseMode: init?.browseMode ?? current.browseMode,
      currentFolderPath: init?.currentFolderPath ?? workspace,
      searchText: init?.searchText ?? '',
      searchType: init?.searchType ?? '',
    })
    tabs.value.set(tab.id, tab)
    tabOrder.value.push(tab.id)
    await switchTab(tab.id)
    return tab.id
  }

  /**
   * 关闭标签页。
   *
   * 恒保留至少一个标签页（activeTab 的兜底依赖该不变量）。
   *
   * @param tabId 待关闭的标签页 id
   */
  async function closeTab(tabId: string) {
    if (tabOrder.value.length <= 1) return
    const idx = tabOrder.value.indexOf(tabId)
    if (idx === -1) return

    tabOrder.value.splice(idx, 1)
    tabs.value.delete(tabId)

    // 关闭当前标签页时激活右邻，没有右邻则取左邻（与浏览器一致）
    if (activeTabId.value === tabId) {
      const nextId = tabOrder.value[idx] ?? tabOrder.value[idx - 1]
      activeTabId.value = ''
      await switchTab(nextId)
    }
  }

  /**
   * 关闭属于指定工作区的所有标签页（工作区被移除时调用）。
   *
   * 恒保留至少一个标签页；若全部标签页都属于该工作区，最后一个会被重置
   * 到新的活动工作区，而非留着指向已移除工作区的失效内容。
   *
   * @param ws 被移除的工作区根路径
   */
  async function closeWorkspaceTabs(ws: string) {
    const victims = tabOrder.value.filter(id => {
      const t = tabs.value.get(id)
      return t && !t.isGlobalView && t.workspace === ws
    })

    for (const id of victims) {
      if (tabOrder.value.length <= 1) break
      await closeTab(id)
    }

    // 只剩一个且仍指向被移除的工作区：原地重置，交由调用方重新加载
    const last = activeTab.value
    if (last && !last.isGlobalView && last.workspace === ws) {
      const appStore = useAppStore()
      const fallback = appStore.activeWorkspace || ''
      last.workspace = fallback
      last.currentFolderPath = fallback
      last.folderByWorkspace = {}
      last.files = []
      last.childDirs = []
      last.selectedIds = new Set()
      last.activeId = null
      last.totalCount = 0
      last.hasMore = false
      last.searchQuery = {}
      last.searchText = ''
      last.searchType = ''
      last.loaded = false
      last.dirty = true
    }
  }

  /**
   * 剔除指向已不存在工作区的恢复标签页（appStore 工作区列表就绪后调用一次）。
   *
   * 跨会话恢复时 store 无从判断落盘的 workspace 是否还在列表里——工作区可能
   * 在上次会话之后被移除。不剔除会留下一个点开就报错的死标签页。
   *
   * 恒保留至少一个标签页；全部失效时最后一个被重置到活动工作区。
   *
   * @param validWorkspaces 当前有效的工作区根路径列表
   */
  async function pruneInvalidTabs(validWorkspaces: string[]) {
    const valid = new Set(validWorkspaces)
    const victims = tabOrder.value.filter(id => {
      const t = tabs.value.get(id)
      // workspace 为空的是「新标签页」（工作区尚未补齐），不算失效
      return t && !t.isGlobalView && t.workspace && !valid.has(t.workspace)
    })
    for (const id of victims) {
      if (tabOrder.value.length <= 1) break
      await closeTab(id)
    }
    const last = activeTab.value
    if (last && !last.isGlobalView && last.workspace && !valid.has(last.workspace)) {
      const fallback = validWorkspaces[0] || ''
      last.workspace = fallback
      last.currentFolderPath = fallback
      last.folderByWorkspace = {}
      last.searchQuery = {}
      last.searchText = ''
      last.searchType = ''
      last.loaded = false
      last.dirty = true
    }
  }

  /**
   * 设置标签页所属工作区（切换工作区时由外部调用）。
   *
   * @param workspace 工作区根路径
   * @param isGlobalView 是否为跨工作区全局视图
   * @param tabId 目标标签页；不传则为当前激活标签页
   */
  function setTabWorkspace(workspace: string, isGlobalView: boolean, tabId?: string) {
    const tab = getTab(tabId)
    tab.workspace = workspace
    tab.isGlobalView = isGlobalView
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

  // 以下就地更新类操作遍历所有标签页：同一文件可能同时出现在多个标签页的
  // 列表快照中，只改当前标签页会让其它标签页显示过期的标签/元数据。

  // 回填惰性探测得到的媒体元数据，避免同一会话内重复请求
  function updateFileMediaInfo(fileId: number, info: MediaInfo) {
    for (const tab of tabs.value.values()) {
      const file = tab.files.find(f => f.id === fileId)
      if (!file) continue
      file.duration = info.duration
      file.width = info.width
      file.height = info.height
      file.bitrate = info.bitrate
    }
  }

  function updateFileTags(fileId: number, tagIds: number[]) {
    for (const tab of tabs.value.values()) {
      const file = tab.files.find(f => f.id === fileId)
      if (file) {
        file.tag_ids = tagIds
      }
    }
  }

  function updateBatchFileTags(fileIds: number[], tagIds: number[]) {
    fileIds.forEach(fileId => {
      updateFileTags(fileId, tagIds)
    })
  }

  function addTagsToFile(fileId: number, tagIds: number[]) {
    for (const tab of tabs.value.values()) {
      const file = tab.files.find(f => f.id === fileId)
      if (file) {
        file.tag_ids = Array.from(new Set([...file.tag_ids, ...tagIds]))
      }
    }
  }

  function addTagsToFiles(fileIds: number[], tagIds: number[]) {
    fileIds.forEach(fileId => {
      addTagsToFile(fileId, tagIds)
    })
  }

  function removeTagFromAllFiles(tagId: number) {
    for (const tab of tabs.value.values()) {
      tab.files.forEach(file => {
        const idx = file.tag_ids.indexOf(tagId)
        if (idx !== -1) {
          file.tag_ids.splice(idx, 1)
        }
      })
    }
  }

  function removeTagFromFiles(fileIds: number[], tagId: number) {
    const idSet = new Set(fileIds)
    for (const tab of tabs.value.values()) {
      tab.files.forEach(file => {
        if (!idSet.has(file.id)) return
        const idx = file.tag_ids.indexOf(tagId)
        if (idx !== -1) {
          file.tag_ids.splice(idx, 1)
        }
      })
    }
  }

  function removeFile(fileId: number) {
    for (const tab of tabs.value.values()) {
      const index = tab.files.findIndex(f => f.id === fileId)
      if (index === -1) continue
      tab.files.splice(index, 1)
      tab.selectedIds.delete(fileId)
      if (tab.activeId === fileId) {
        tab.activeId = _firstSelectedId(tab)
      }
      tab.totalCount--
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
    // 标签页
    tabs,
    tabOrder,
    activeTabId,
    activeTab,
    tabList,
    getTab,
    isSwitchingTab,
    switchTab,
    addTab,
    closeTab,
    ensureTabLoaded,
    closeWorkspaceTabs,
    pruneInvalidTabs,
    setTabWorkspace,
    markTabsDirty,
    refreshDirtyActiveTab,
    registerScrollHooks,
    captureTabScroll,
    // 按标签页隔离的字段（代理）
    files,
    selectedIds,
    activeId,
    searchQuery,
    totalCount,
    hasMore,
    isLoading,
    browseMode,
    currentFolderPath,
    childDirs,
    // 全局视图偏好
    viewMode,
    gridItemSize,
    sortBy,
    sortDesc,
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
    tryLoadMore,
    rememberFolder,
    getRememberedFolder,
    getTabFolder,
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
