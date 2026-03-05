import { apiClient } from './client'
import type { FileDetail, SearchQuery, SearchResult, FileTagsUpdate } from '../types'

export const fileApi = {
  // 搜索文件
  async search(query: SearchQuery): Promise<SearchResult> {
    return apiClient.post<SearchResult>('/api/files', query)
  },

  // 获取文件详情
  async getById(id: number): Promise<FileDetail> {
    return apiClient.get<FileDetail>(`/api/files/${id}`)
  },

  // 更新文件标签
  async updateTags(id: number, update: FileTagsUpdate): Promise<{ success: boolean }> {
    return apiClient.put<{ success: boolean }>(`/api/files/${id}/tags`, update)
  },

  // 删除文件
  async delete(id: number): Promise<{ success: boolean }> {
    return apiClient.delete<{ success: boolean }>(`/api/files/${id}`)
  },
}
