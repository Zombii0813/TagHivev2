import { apiClient } from './client'
import type { Workspace, WorkspaceStats, ScanProgress } from '../types'

export const workspaceApi = {
  // 扫描工作区
  async scan(workspace: Workspace): Promise<ScanProgress> {
    return apiClient.post<ScanProgress>('/api/workspace/scan', workspace)
  },

  // 获取工作区统计
  async getStats(): Promise<WorkspaceStats> {
    return apiClient.get<WorkspaceStats>('/api/workspace/stats')
  },

  // 健康检查
  async health(): Promise<{ status: string; version: string }> {
    return apiClient.get<{ status: string; version: string }>('/api/health')
  },
}
