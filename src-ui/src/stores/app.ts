import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import { invoke } from '@tauri-apps/api/core'

export interface AppState {
  theme: 'light' | 'dark'
  sidebarCollapsed: boolean
  detailPanelVisible: boolean
  isLoading: boolean
  currentWorkspace: string | null
}

export const useAppStore = defineStore('app', () => {
  // State
  const theme = ref<AppState['theme']>('light')
  const sidebarCollapsed = ref(false)
  const detailPanelVisible = ref(true)
  const isLoading = ref(false)
  const currentWorkspace = ref<string | null>(null)

  // Getters
  const isDark = computed(() => theme.value === 'dark')

  // Actions
  function setTheme(newTheme: AppState['theme']) {
    theme.value = newTheme
    document.documentElement.setAttribute('data-theme', newTheme)
    // 保存到本地存储
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

  function setWorkspace(path: string | null) {
    currentWorkspace.value = path
    if (path) {
      localStorage.setItem('taghive-workspace', path)
    }
  }

  async function initialize() {
    // 加载保存的主题
    const savedTheme = localStorage.getItem('taghive-theme') as AppState['theme']
    if (savedTheme) {
      setTheme(savedTheme)
    }

    // 加载保存的工作区
    const savedWorkspace = localStorage.getItem('taghive-workspace')
    if (savedWorkspace) {
      currentWorkspace.value = savedWorkspace
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
    currentWorkspace,
    isDark,
    setTheme,
    toggleTheme,
    toggleSidebar,
    toggleDetailPanel,
    setLoading,
    setWorkspace,
    initialize,
    selectFolder,
  }
})
