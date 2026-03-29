import { apiClient } from './client'
import type { FileDetail, SearchQuery, SearchResult, FileTagsUpdate, ResolveFilesResult, ImportFilesResult, FileSummary, FileBatchResult } from '../types'

export const fileApi = {
  // 搜索文件
  async search(query: SearchQuery): Promise<SearchResult> {
    return apiClient.post<SearchResult>('/api/files', query)
  },

  // 获取文件详情
  async getById(id: number): Promise<FileDetail> {
    return apiClient.get<FileDetail>(`/api/files/${id}`)
  },

  // 按路径解析已扫描文件
  async resolvePaths(paths: string[]): Promise<ResolveFilesResult> {
    return apiClient.post<ResolveFilesResult>('/api/files/resolve', { paths })
  },

  // 导入外部文件到指定目录
  async importToDirectory(paths: string[], targetDir: string): Promise<ImportFilesResult> {
    return apiClient.post<ImportFilesResult>('/api/files/import', {
      paths,
      target_dir: targetDir,
    })
  },

  // 更新文件标签
  async updateTags(id: number, update: FileTagsUpdate): Promise<{ success: boolean }> {
    return apiClient.put<{ success: boolean }>(`/api/files/${id}/tags`, update)
  },

  // 删除文件
  async delete(id: number): Promise<{ success: boolean }> {
    return apiClient.delete<{ success: boolean }>(`/api/files/${id}`)
  },

  // 重命名文件
  async rename(id: number, newName: string): Promise<FileSummary> {
    return apiClient.put<FileSummary>(`/api/files/${id}/rename`, { new_name: newName })
  },

  // 移动文件（工作区内移动）
  async move(fileIds: number[], targetDir: string): Promise<FileBatchResult> {
    return apiClient.post<FileBatchResult>('/api/files/move', {
      file_ids: fileIds,
      target_dir: targetDir,
    })
  },

  // 复制文件
  async copy(fileIds: number[], targetDir: string): Promise<FileBatchResult> {
    return apiClient.post<FileBatchResult>('/api/files/copy', {
      file_ids: fileIds,
      target_dir: targetDir,
    })
  },
}
