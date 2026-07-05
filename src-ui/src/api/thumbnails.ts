import { apiClient } from './client'
import { getApiBaseUrl } from './baseUrl'

export const thumbnailApi = {
  // 获取缩略图 URL
  getThumbnailUrl(fileId: number, size: 'small' | 'medium' | 'large' = 'medium'): string {
    return `${getApiBaseUrl()}/api/thumbnails/${fileId}?size=${size}`
  },

  // 按任意本地文件路径获取缩略图 URL（用于 explorer 目录自定义封面）
  getThumbnailUrlByPath(path: string, size: 'small' | 'medium' | 'large' = 'medium'): string {
    const params = new URLSearchParams({ path, size })
    return `${getApiBaseUrl()}/api/thumbnails/by-path?${params.toString()}`
  },

  // 获取原始文件 URL（用于视频播放）
  getFileUrl(fileId: number): string {
    return `${getApiBaseUrl()}/api/files/${fileId}/preview`
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
