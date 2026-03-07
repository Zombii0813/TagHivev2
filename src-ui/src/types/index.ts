// 文件类型
export interface FileItem {
  id: number
  path: string
  name: string
  ext?: string
  size: number
  type: string
  hash?: string
  modified_at?: number
  created_at: string
  updated_at: string
  tag_ids: number[]
}

export interface FileDetail extends FileItem {
  tags: Tag[]
}

// 标签类型
export interface Tag {
  id: number
  name: string
  color?: string
  description?: string
  created_at: string
  file_count: number
}

export interface CreateTagRequest {
  name: string
  color?: string
  description?: string
}

export interface UpdateTagRequest {
  name?: string
  color?: string
  description?: string
}

// 搜索类型
export interface SearchQuery {
  text?: string
  root?: string
  types?: string[]
  tags?: number[]
  match_all_tags?: boolean
  sort_by?: string
  sort_desc?: boolean
  use_fts?: boolean
  limit?: number
  offset?: number
}

export interface SearchResult {
  files: FileSummary[]
  total: number
  has_more: boolean
}

export interface FileSummary {
  id: number
  name: string
  path: string
  type: string
  size: number
  modified_at?: number
  tag_ids: number[]
}

// 工作区类型
export interface Workspace {
  path: string
  name: string
}

export interface WorkspaceStats {
  total_files: number
  total_tags: number
  type_distribution: Record<string, number>
}

// 扫描进度
export interface ScanProgress {
  status: 'scanning' | 'completed' | 'error'
  count: number
  message?: string
}

// 文件标签更新
export interface FileTagsUpdate {
  tag_ids: number[]
  mode: 'replace' | 'add' | 'remove'
}

// WebSocket 事件
export interface FileChangedEvent {
  path: string
  file_id: number
  name: string
  type: string
  size: number
  tags: Array<{ id: number; name: string }>
  event: 'created' | 'modified'
}

export interface FileDeletedEvent {
  path: string
  file_id: number
}

export interface ScanProgressEvent {
  count: number
  path: string
}

export interface ScanCompletedEvent {
  path: string
  total: number
}

// 缩略图
export interface ThumbnailRequest {
  file_id: number
  size?: number
}

export interface ThumbnailResponse {
  file_id: number
  url?: string
  exists: boolean
}
