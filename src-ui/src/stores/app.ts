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
  }

  async function selectFolder() {
    console.log('[app.ts] selectFolder called')
    console.log('[app.ts] invoke function:', invoke)
    console.log('[app.ts] typeof invoke:', typeof invoke)
    
    // 尝试使用全局 Tauri 对象作为回退
    let invokeFn = invoke
    if (typeof invoke !== 'function' && typeof window !== 'undefined' && (window as any).__TAURI__) {
      console.log('[app.ts] Using global __TAURI__ object')
      invokeFn = (window as any).__TAURI__.core.invoke
    }
    
    if (typeof invokeFn !== 'function') {
      console.error('[app.ts] invoke is not a function!')
      throw new Error('invoke is not available')
    }
    
    try {
      console.log('[app.ts] invoking select_folder command')
      const selected = await invokeFn('select_folder')
      console.log('[app.ts] select_folder returned:', selected)
      if (selected) {
        setWorkspace(selected as string)
        return selected as string
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
