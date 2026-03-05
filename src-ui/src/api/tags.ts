import { apiClient } from './client'
import type { Tag, CreateTagRequest, UpdateTagRequest } from '../types'

export const tagApi = {
  // 获取所有标签
  async getAll(): Promise<Tag[]> {
    return apiClient.get<Tag[]>('/api/tags')
  },

  // 获取标签详情
  async getById(id: number): Promise<Tag> {
    return apiClient.get<Tag>(`/api/tags/${id}`)
  },

  // 创建标签
  async create(data: CreateTagRequest): Promise<Tag> {
    return apiClient.post<Tag>('/api/tags', data)
  },

  // 更新标签
  async update(id: number, data: UpdateTagRequest): Promise<Tag> {
    return apiClient.put<Tag>(`/api/tags/${id}`, data)
  },

  // 删除标签
  async delete(id: number): Promise<{ success: boolean }> {
    return apiClient.delete<{ success: boolean }>(`/api/tags/${id}`)
  },

  // 批量分配标签
  async batchAssign(fileIds: number[], tagIds: number[]): Promise<{ success: boolean; files: number; tags: number }> {
    return apiClient.post<{ success: boolean; files: number; tags: number }>('/api/tags/batch-assign', {
      file_ids: fileIds,
      tag_ids: tagIds,
    })
  },
}
