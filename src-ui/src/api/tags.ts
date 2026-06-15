import { apiClient } from './client'
import { getApiBaseUrl } from './baseUrl'
import type { Tag, CreateTagRequest, UpdateTagRequest } from '../types'

export const tagApi = {
  // 获取所有标签
  // root: 可选的工作目录路径，如果提供则只返回该目录下有关联文件的标签
  async getAll(root?: string): Promise<Tag[]> {
    const config = root ? { params: { root } } : undefined
    return apiClient.get<Tag[]>('/api/tags', config)
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

  // 导出指定 workspace 的标签树与文件标记关联（返回 .thpack 二进制）
  async exportPack(workspace: string, tagIds?: number[], includeThumbnails: boolean = false): Promise<Uint8Array> {
    const resp = await fetch(`${getApiBaseUrl()}/api/tags/export`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        workspace,
        tag_ids: tagIds ?? null,
        include_thumbnails: includeThumbnails,
      }),
    })
    if (!resp.ok) {
      const text = await resp.text()
      throw new Error(`导出失败: ${resp.status} ${text}`)
    }
    const buf = await resp.arrayBuffer()
    return new Uint8Array(buf)
  },

  // 上传 .thpack 内容获取导入预览
  async importPreview(workspace: string, content: Uint8Array): Promise<ImportPreview> {
    const blob = new Blob([content as BlobPart], { type: 'application/octet-stream' })
    const resp = await fetch(
      `${getApiBaseUrl()}/api/tags/import/preview?workspace=${encodeURIComponent(workspace)}`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/octet-stream' },
        body: blob,
      },
    )
    if (!resp.ok) {
      const text = await resp.text()
      throw new Error(`预览失败: ${resp.status} ${text}`)
    }
    return resp.json()
  },

  async importRelocate(req: ImportRelocateRequest): Promise<ImportPreview> {
    return apiClient.post<ImportPreview>('/api/tags/import/relocate', req)
  },

  async importCommit(req: ImportCommitRequest): Promise<ImportSummary> {
    return apiClient.post<ImportSummary>('/api/tags/import/commit', req)
  },
}

// ===== 导入导出相关类型 =====

export interface ExportedTagPreview {
  export_id: string
  name: string
  color?: string | null
  icon?: string | null
  description?: string | null
  parent_export_id?: string | null
  conflict: boolean
  existing_tag_id?: number | null
}

export interface FileMatchEntryPreview {
  rel_path: string
  name: string
  size: number
  mtime?: number | null
  tag_export_ids: string[]
  candidate_file_ids: number[]
  thumbnail?: string | null  // base64(small 缩略图)，导出包未携带时为 null
}

export interface ImportPreview {
  token: string
  schema_version: number
  exported_at: string
  source_workspace: string
  target_workspace: string
  tags: ExportedTagPreview[]
  unique: FileMatchEntryPreview[]
  multiple: FileMatchEntryPreview[]
  unmatched: FileMatchEntryPreview[]
}

export interface ImportRelocateRequest {
  token: string
  mode: 'manual' | 'skip_all'
  rel_path?: string | null
  file_id?: number | null
}

export interface ImportTagDecision {
  export_id: string
  strategy: 'skip' | 'merge' | 'rename'
  new_name?: string | null
}

export interface ImportFileDecision {
  rel_path: string
  file_ids: number[]
}

export interface ImportCommitRequest {
  token: string
  tag_decisions: ImportTagDecision[]
  file_decisions: ImportFileDecision[]
}

export interface ImportSummary {
  tags_created: number
  tags_reused: number
  files_linked: number
  files_skipped: number
}
