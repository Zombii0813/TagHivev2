import { apiClient } from './client'
import type { FolderTree, FolderContents, CreateFolderResult, FileBatchResult } from '../types'

export const folderApi = {
  // 获取文件夹树结构
  async getTree(root: string): Promise<FolderTree> {
    // URLSearchParams 会自动编码参数，不需要手动 encodeURIComponent
    const params = new URLSearchParams({ root })
    return apiClient.get<FolderTree>(`/api/folders/tree?${params.toString()}`)
  },

  // 获取指定文件夹的内容
  async getContents(
    path: string,
    offset: number = 0,
    limit: number = 500,
    sortBy: string = 'name',
    sortDesc: boolean = false,
    includeDirs: boolean = false
  ): Promise<FolderContents> {
    // URLSearchParams 会自动编码参数，不需要手动 encodeURIComponent
    const params = new URLSearchParams({
      path,
      offset: offset.toString(),
      limit: limit.toString(),
      sort_by: sortBy,
      sort_desc: sortDesc.toString(),
      include_dirs: includeDirs.toString(),
    })
    return apiClient.get<FolderContents>(`/api/folders/contents?${params.toString()}`)
  },

  // 设置目录自定义封面（explorer 模式）
  async setCover(folderPath: string, coverPath: string, workspace?: string): Promise<void> {
    return apiClient.post('/api/folders/cover', {
      folder_path: folderPath,
      cover_path: coverPath,
      workspace: workspace ?? null,
    })
  },

  // 清除目录自定义封面，恢复自动九宫格
  async clearCover(folderPath: string): Promise<void> {
    return apiClient.post('/api/folders/cover/clear', {
      folder_path: folderPath,
    })
  },

  async createFolder(rootPath: string, parentPath: string, name: string): Promise<CreateFolderResult> {
    return apiClient.post<CreateFolderResult>('/api/folders/create', {
      root_path: rootPath,
      parent_path: parentPath,
      name,
    })
  },

  async deleteFolder(rootPath: string, folderPath: string): Promise<void> {
    return apiClient.post('/api/folders/delete', {
      root_path: rootPath,
      folder_path: folderPath,
    })
  },

  // 移动整个文件夹到目标父目录（支持跨工作区）
  async moveFolder(sourcePath: string, targetDir: string, targetWorkspace?: string): Promise<FileBatchResult> {
    return apiClient.post<FileBatchResult>('/api/folders/move', {
      source_path: sourcePath,
      target_dir: targetDir,
      target_workspace: targetWorkspace,
    })
  },

  // 复制整个文件夹到目标父目录（副本不含标签）
  async copyFolder(sourcePath: string, targetDir: string): Promise<FileBatchResult> {
    return apiClient.post<FileBatchResult>('/api/folders/copy', {
      source_path: sourcePath,
      target_dir: targetDir,
    })
  },
}
