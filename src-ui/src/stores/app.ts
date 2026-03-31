import { ref, computed } from 'vue'
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
  const sidebarCollapsed = ref(false)
  const detailPanelVisible = ref(true)
  const isLoading = ref(false)

  // Multi-workspace state
  const workspaces = ref<string[]>([])
  const activeWorkspace = ref<string | null>(null)
  const isGlobalView = ref(false)

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
    detailPanelVisible,
    isLoading,
    workspaces,
    activeWorkspace,
    isGlobalView,
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
