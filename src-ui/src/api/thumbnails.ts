import { apiClient } from './client'

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8721'

export const thumbnailApi = {
  // 获取缩略图 URL
  getThumbnailUrl(fileId: number, size: 'small' | 'medium' | 'large' = 'medium'): string {
    return `${API_BASE_URL}/api/thumbnails/${fileId}?size=${size}`
  },

  // 获取原始文件 URL（用于视频播放）
  getFileUrl(fileId: number): string {
    return `${API_BASE_URL}/api/files/${fileId}/preview`
  },

  // 清理过期缩略图
  async cleanup(maxAgeDays: number = 30): Promise<{ cleaned: number }> {
    return apiClient.post<{ cleaned: number }>(`/api/thumbnails/cleanup?max_age_days=${maxAgeDays}`)
  },

  // 获取缓存统计
  async getStats(): Promise<{ file_count: number; total_size_bytes: number; total_size_mb: number }> {
    return apiClient.get('/api/thumbnails/stats')
  },
}
