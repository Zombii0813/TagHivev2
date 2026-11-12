// 浏览标签页的类型定义、工厂与持久化。
//
// 只放数据形状与序列化，不放 store —— 由 stores/files.ts 引入，
// 避免 files.ts 继续膨胀。

import type { ChildDir, FileSummary, SearchQuery } from '../types'

export type BrowseMode = 'folder' | 'all' | 'tree' | 'explorer'

/**
 * 单个浏览标签页的完整状态。
 *
 * 字段分两类：
 *   - 「浏览位置」语义（目录、模式、列表、选中项、滚动位置）—— 按标签页隔离
 *   - 视图偏好（网格/列表、卡片大小、排序）不在此处，仍是 fileStore 的全局 ref
 */
export interface TabState {
  id: string
  /** 该标签页所属工作区根路径；all 模式下用于确定搜索范围 */
  workspace: string
  /** 是否处于跨工作区的全局视图 */
  isGlobalView: boolean
  browseMode: BrowseMode
  currentFolderPath: string

  // ── 列表数据与分页 ──
  files: FileSummary[]
  childDirs: ChildDir[]
  totalCount: number
  hasMore: boolean
  isLoading: boolean
  /** 分页偏移，仅 store 内部使用，不对外导出 */
  folderContentsOffset: number

  // ── 选中态 ──
  selectedIds: Set<number>
  /** 同范围刷新或排序后移出加载页的选中项，不落盘。 */
  selectedRecords: Map<number, FileSummary>
  activeId: number | null
  multiSelectMode: boolean

  // ── 搜索/过滤 ──
  queryError: string
  queryKey: string
  appliedQuery: string
  searchQuery: SearchQuery
  /** 搜索框文本，由 SearchBar 受控读写 */
  searchText: string
  /** 搜索框的类型筛选值 */
  searchType: string

  // ── 视图杂项 ──
  /** 全局视图下当前高亮的工作区 */
  activeMultiTreeWorkspace: string
  /** 虚拟滚动模式的滚动位置（像素） */
  scrollTop: number
  /** explorer 模式各层级的滚动位置（路径 → 像素） */
  explorerScrollByPath: Record<string, number>
  /**
   * 本标签页在各工作区最后浏览到的层级（工作区根 → 目录路径）。
   *
   * 必须按标签页存：切换浏览模式/工作区时要恢复的是「本标签页」上次的位置，
   * 用全局共享的记忆会取到别的标签页刚写进去的路径。
   */
  folderByWorkspace: Record<string, string>

  // ── 加载调度 ──
  /** 上次触底加载的时间戳，用于按标签页独立冷却 */
  lastLoadMoreAt: number
  /** 是否已实际加载过数据（跨会话恢复的标签页初始为 false） */
  loaded: boolean
  /** 数据是否已过期，待切换到该标签页时惰性重载 */
  dirty: boolean
}

/** 落盘的字段子集：不含列表数据与选中项，避免体积膨胀与失效 id */
export interface PersistedTab {
  id: string
  workspace: string
  isGlobalView: boolean
  browseMode: BrowseMode
  currentFolderPath: string
  searchText: string
  searchType: string
  tagIds?: number[]
}

export const TABS_KEY = 'taghive:browser-tabs'

/** 标签页数量上限：每页快照最多 500 个文件，过多会占用可观内存 */
export const MAX_TABS = 12

let _seq = 0

/** 生成标签页 id（会话内唯一即可，落盘后重启会重新计数但不影响正确性） */
function nextTabId(): string {
  _seq += 1
  return `tab-${Date.now().toString(36)}-${_seq}`
}

/**
 * 创建一个标签页状态。
 *
 * @param init 初始字段，workspace 必填；其余取默认值
 * @returns 新的标签页状态对象
 */
export function createTab(
  init: Partial<TabState> & { workspace: string }
): TabState {
  return {
    id: init.id ?? nextTabId(),
    workspace: init.workspace,
    isGlobalView: init.isGlobalView ?? false,
    browseMode: init.browseMode ?? 'all',
    currentFolderPath: init.currentFolderPath ?? '',
    files: init.files ?? [],
    childDirs: init.childDirs ?? [],
    totalCount: init.totalCount ?? 0,
    hasMore: init.hasMore ?? false,
    isLoading: init.isLoading ?? false,
    folderContentsOffset: init.folderContentsOffset ?? 0,
    selectedIds: init.selectedIds ?? new Set<number>(),
    selectedRecords: init.selectedRecords ?? new Map<number, FileSummary>(),
    activeId: init.activeId ?? null,
    multiSelectMode: init.multiSelectMode ?? false,
    queryError: '',
    queryKey: '',
    appliedQuery: '',
    searchQuery: init.searchQuery ?? {},
    searchText: init.searchText ?? '',
    searchType: init.searchType ?? '',
    activeMultiTreeWorkspace: init.activeMultiTreeWorkspace ?? '',
    scrollTop: init.scrollTop ?? 0,
    explorerScrollByPath: init.explorerScrollByPath ?? {},
    folderByWorkspace: init.folderByWorkspace ?? {},
    lastLoadMoreAt: init.lastLoadMoreAt ?? 0,
    loaded: init.loaded ?? false,
    dirty: init.dirty ?? false,
  }
}

/**
 * 计算标签页的显示标题。
 *
 * 统一为「工作区名：当前目录名」，各浏览模式一致。位于工作区根目录时
 * 两段同名，只显示一次，避免出现「视频：视频」这样的重复。
 *
 * @param tab 标签页状态
 * @returns 标签页显示文案
 */
export function tabTitle(tab: TabState): string {
  if (tab.isGlobalView) return '全部工作区'

  const wsName = tab.workspace ? baseName(tab.workspace) : ''
  if (!wsName) return '新标签页'

  // all 模式没有目录层级概念，但格式要求一致，取工作区名作为层级名
  const path = tab.currentFolderPath || tab.workspace
  const dirName = baseName(path)

  if (!dirName || dirName === wsName) return wsName
  return `${wsName}：${dirName}`
}

/** 取路径末段（同时兼容 Windows 反斜杠与 POSIX 斜杠） */
export function baseName(path: string): string {
  const trimmed = path.replace(/[\\/]+$/, '')
  const idx = Math.max(trimmed.lastIndexOf('\\'), trimmed.lastIndexOf('/'))
  const name = idx === -1 ? trimmed : trimmed.slice(idx + 1)
  // 盘符根（如 D:）取不到末段，退回原串
  return name || trimmed
}

/** 提取标签页的可落盘子集 */
export function toPersisted(tab: TabState): PersistedTab {
  return {
    id: tab.id,
    workspace: tab.workspace,
    isGlobalView: tab.isGlobalView,
    browseMode: tab.browseMode,
    currentFolderPath: tab.currentFolderPath,
    searchText: tab.searchText,
    searchType: tab.searchType,
    tagIds: tab.searchQuery.tags,
  }
}

/**
 * 从落盘数据还原标签页。
 *
 * 还原出的标签页 loaded=false，数据在首次激活时才加载，
 * 避免启动时 N 个标签页同时发起请求。
 */
export function fromPersisted(p: PersistedTab): TabState {
  return createTab({
    id: p.id,
    workspace: p.workspace,
    isGlobalView: p.isGlobalView,
    browseMode: p.browseMode,
    currentFolderPath: p.currentFolderPath,
    searchText: p.searchText,
    searchType: p.searchType,
    searchQuery: { tags: p.tagIds },
    // 把落盘的层级回填进层级记忆：树窗/资源管理器模式恢复数据时走的是
    // getTabFolder(工作区)，记忆为空会退回工作区根，currentFolderPath
    // 虽然恢复了也会立刻被覆盖掉。folderByWorkspace 本身不落盘
    // （多工作区历史层级价值有限），只种下当前这一条。
    folderByWorkspace: p.workspace && p.currentFolderPath
      ? { [p.workspace]: p.currentFolderPath }
      : {},
    loaded: false,
  })
}

const VALID_MODES: BrowseMode[] = ['folder', 'all', 'tree', 'explorer']

/** 读取落盘的标签页列表；数据损坏或不存在时返回空列表 */
export function loadPersistedTabs(): {
  tabs: PersistedTab[]
  activeId: string | null
} {
  try {
    const raw = localStorage.getItem(TABS_KEY)
    if (!raw) return { tabs: [], activeId: null }
    const parsed = JSON.parse(raw) as {
      tabs?: unknown
      activeId?: unknown
    }
    if (!Array.isArray(parsed.tabs)) return { tabs: [], activeId: null }

    const tabs: PersistedTab[] = []
    for (const item of parsed.tabs) {
      if (!item || typeof item !== 'object') continue
      const t = item as Record<string, unknown>
      if (typeof t.id !== 'string' || typeof t.workspace !== 'string') continue
      const mode = VALID_MODES.includes(t.browseMode as BrowseMode)
        ? (t.browseMode as BrowseMode)
        : 'all'
      tabs.push({
        id: t.id,
        workspace: t.workspace,
        isGlobalView: t.isGlobalView === true,
        browseMode: mode,
        currentFolderPath:
          typeof t.currentFolderPath === 'string' ? t.currentFolderPath : '',
        searchText: typeof t.searchText === 'string' ? t.searchText : '',
        searchType: typeof t.searchType === 'string' ? t.searchType : '',
        tagIds: Array.isArray(t.tagIds) ? t.tagIds.filter((id): id is number => typeof id === 'number' && Number.isInteger(id)) : [],
      })
      if (tabs.length >= MAX_TABS) break
    }

    const activeId =
      typeof parsed.activeId === 'string' &&
      tabs.some((t) => t.id === parsed.activeId)
        ? parsed.activeId
        : null

    return { tabs, activeId }
  } catch {
    return { tabs: [], activeId: null }
  }
}

/** 落盘标签页列表与当前激活项 */
export function persistTabs(tabs: TabState[], activeId: string): void {
  try {
    localStorage.setItem(
      TABS_KEY,
      JSON.stringify({
        tabs: tabs.map(toPersisted),
        activeId,
      })
    )
  } catch {
    // localStorage 满 / 隐私模式，忽略
  }
}
