import { ref, computed, watch } from 'vue'
import { defineStore } from 'pinia'
import { invoke } from '@tauri-apps/api/core'

export interface AppState {
  theme: 'light' | 'dark'
  sidebarCollapsed: boolean
  detailPanelVisible: boolean
  isLoading: boolean
  workspaces: string[]
  activeWorkspace: string | null
  isGlobalView: boolean
}

export const useAppStore = defineStore('app', () => {
  // State
  const theme = ref<AppState['theme']>('light')
  const readNumber = (key: string, fallback: number, min: number, max: number) => {
    const raw = localStorage.getItem(key)
    const value = raw === null ? fallback : Number(raw)
    return Number.isFinite(value) ? Math.min(max, Math.max(min, value)) : fallback
  }
  const sidebarCollapsed = ref(localStorage.getItem('taghive:sidebar-collapsed') === 'true')
  const detailPanelVisible = ref(localStorage.getItem('taghive:detail-visible') === 'true')
  const sidebarWidth = ref(readNumber('taghive:sidebar-width', 240, 200, 360))
  const detailWidth = ref(readNumber('taghive:detail-width', 320, 280, 480))
  const compactDensity = ref(localStorage.getItem('taghive:compact') === 'true')
  watch([sidebarCollapsed, detailPanelVisible, sidebarWidth, detailWidth, compactDensity], values => {
    const keys = ['sidebar-collapsed', 'detail-visible', 'sidebar-width', 'detail-width', 'compact']
    values.forEach((v, index) => localStorage.setItem('taghive:' + keys[index], String(v)))
  })
  const isLoading = ref(false)

  // Multi-workspace state
  const workspaces = ref<string[]>([])
  const activeWorkspace = ref<string | null>(null)
  const isGlobalView = ref(false)
  // 当前不可达的工作区路径（如外部移动硬盘已拔出）。
  // 仅用于 UI 提示，绝不据此删除工作区或其数据。
  const unavailableWorkspaces = ref<Set<string>>(new Set())

  // Getters
  const isDark = computed(() => theme.value === 'dark')

  // currentWorkspace: backward-compat — returns activeWorkspace, or null in global view
  const currentWorkspace = computed(() =>
    isGlobalView.value ? null : activeWorkspace.value
  )

  // Actions
  function setTheme(newTheme: AppState['theme']) {
    theme.value = newTheme
    document.documentElement.setAttribute('data-theme', newTheme)
    localStorage.setItem('taghive-theme', newTheme)
  }

  function toggleTheme() {
    setTheme(theme.value === 'light' ? 'dark' : 'light')
  }

  function toggleSidebar() {
    sidebarCollapsed.value = !sidebarCollapsed.value
  }

  function toggleDetailPanel() {
    detailPanelVisible.value = !detailPanelVisible.value
  }

  function setLoading(loading: boolean) {
    isLoading.value = loading
  }

  function _saveWorkspaces() {
    localStorage.setItem('taghive-workspaces', JSON.stringify(workspaces.value))
    localStorage.setItem('taghive-active-workspace', activeWorkspace.value || '')
    localStorage.setItem('taghive-global-view', isGlobalView.value ? '1' : '0')
  }

  function setWorkspace(path: string | null) {
    if (!path) return
    if (!workspaces.value.includes(path)) {
      workspaces.value.push(path)
    }
    activeWorkspace.value = path
    isGlobalView.value = false
    _saveWorkspaces()
    // backward-compat key
    localStorage.setItem('taghive-workspace', path)
  }

  function switchWorkspace(path: string) {
    if (!workspaces.value.includes(path)) return
    activeWorkspace.value = path
    isGlobalView.value = false
    _saveWorkspaces()
    localStorage.setItem('taghive-workspace', path)
  }

  function removeWorkspace(path: string) {
    const idx = workspaces.value.indexOf(path)
    if (idx === -1) return
    workspaces.value.splice(idx, 1)
    if (activeWorkspace.value === path) {
      if (workspaces.value.length > 0) {
        activeWorkspace.value = workspaces.value[0]
        isGlobalView.value = false
      } else {
        activeWorkspace.value = null
        isGlobalView.value = false
      }
    }
    _saveWorkspaces()
  }

  function setGlobalView(enabled: boolean) {
    if (enabled && workspaces.value.length === 0) return
    isGlobalView.value = enabled
    _saveWorkspaces()
  }

  async function initialize() {
    // 加载保存的主题
    const savedTheme = localStorage.getItem('taghive-theme') as AppState['theme']
    if (savedTheme) {
      setTheme(savedTheme)
    }

    // 加载多工作区（新格式）
    const savedWorkspacesRaw = localStorage.getItem('taghive-workspaces')
    if (savedWorkspacesRaw) {
      try {
        const parsed = JSON.parse(savedWorkspacesRaw)
        if (Array.isArray(parsed)) {
          workspaces.value = parsed.filter((p): p is string => typeof p === 'string' && p.length > 0)
        }
      } catch {
        // ignore
      }
    }

    // 兼容旧的单工作区格式
    if (workspaces.value.length === 0) {
      const legacyWorkspace = localStorage.getItem('taghive-workspace')
      if (legacyWorkspace) {
        workspaces.value = [legacyWorkspace]
      }
    }

    // 检测各工作区当前是否可访问。
    // 注意：不可达（如移动硬盘拔出）时只做标记，绝不从列表删除，
    // 否则重启后工作区连同其标签/文件数据会一并丢失。
    if (workspaces.value.length > 0) {
      const checks = await Promise.all(
        workspaces.value.map(async (p) => {
          try {
            return { path: p, ok: await invoke<boolean>('path_exists', { path: p }) }
          } catch {
            // 校验失败时保守视为可用，避免误标记
            return { path: p, ok: true }
          }
        })
      )
      const offline = checks.filter(c => !c.ok).map(c => c.path)
      unavailableWorkspaces.value = new Set(offline)
      if (offline.length > 0) {
        console.warn('[app] Workspaces currently unavailable (kept):', offline)
      }
    }

    // 加载激活的工作区
    const savedActive = localStorage.getItem('taghive-active-workspace')
    if (savedActive && workspaces.value.includes(savedActive)) {
      activeWorkspace.value = savedActive
    } else if (workspaces.value.length > 0) {
      activeWorkspace.value = workspaces.value[0]
    }

    // 加载全局视图状态
    const savedGlobalView = localStorage.getItem('taghive-global-view')
    if (savedGlobalView === '1' && workspaces.value.length > 0) {
      isGlobalView.value = true
    }

    // 检测系统主题偏好
    if (!savedTheme && window.matchMedia('(prefers-color-scheme: dark)').matches) {
      setTheme('dark')
    }

    // 监听系统主题变化
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')
    const handleChange = (e: MediaQueryListEvent) => {
      if (!localStorage.getItem('taghive-theme')) {
        setTheme(e.matches ? 'dark' : 'light')
      }
    }

    if (mediaQuery.addEventListener) {
      mediaQuery.addEventListener('change', handleChange)
    } else {
      // 兼容旧浏览器
      mediaQuery.addListener(handleChange)
    }
  }

  async function selectFolder() {
    console.log('[app.ts] selectFolder called')

    try {
      const selected = await invoke<string | null>('select_folder')
      console.log('[app.ts] select_folder returned:', selected)
      if (selected) {
        setWorkspace(selected)
        return selected
      }
    } catch (error) {
      console.error('[app.ts] Failed to select folder:', error)
      throw error
    }
    return null
  }

  return {
    theme,
    sidebarCollapsed,
    sidebarWidth,
    detailWidth,
    compactDensity,
    detailPanelVisible,
    isLoading,
    workspaces,
    activeWorkspace,
    isGlobalView,
    unavailableWorkspaces,
    currentWorkspace,
    isDark,
    setTheme,
    toggleTheme,
    toggleSidebar,
    toggleDetailPanel,
    setLoading,
    setWorkspace,
    switchWorkspace,
    removeWorkspace,
    setGlobalView,
    initialize,
    selectFolder,
  }
})
