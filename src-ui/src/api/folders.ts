import { apiClient } from './client'
import type { FolderTree, FolderContents, FolderNode } from '../types'

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
    sortDesc: boolean = false
  ): Promise<FolderContents> {
    // URLSearchParams 会自动编码参数，不需要手动 encodeURIComponent
    const params = new URLSearchParams({
      path,
      offset: offset.toString(),
      limit: limit.toString(),
      sort_by: sortBy,
      sort_desc: sortDesc.toString(),
    })
    return apiClient.get<FolderContents>(`/api/folders/contents?${params.toString()}`)
  },
}
