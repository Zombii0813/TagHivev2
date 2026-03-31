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
  icon?: string
  description?: string
  parent_id?: number | null
  created_at: string
  file_count: number
}

export interface CreateTagRequest {
  name: string
  color?: string
  icon?: string
  description?: string
  workspace?: string  // 工作目录路径，用于标签隔离
  parent_id?: number | null  // 父标签ID
}

export interface UpdateTagRequest {
  name?: string
  color?: string
  icon?: string
  description?: string
  parent_id?: number | null  // null 不更新；0 清除父标签；正整数设置父标签
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

export interface ResolveFilesResult {
  files: FileSummary[]
  missing_paths: string[]
}

export interface ImportFilesResult {
  files: FileSummary[]
  target_dir: string
}

export interface FileSummary {
  id: number
  name: string
  path: string
  type: string
  size: number
  modified_at?: number
  duration?: number
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
  total: number
  percentage: number
  path: string
  current_file?: string
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

// 文件夹树类型
export interface FolderNode {
  name: string
  path: string
  file_count: number
  children: FolderNode[]
  is_expanded: boolean
}

export interface FolderTree {
  root_path: string
  folders: FolderNode[]
  total_folders: number
  root_file_count: number
}

export interface FolderContents {
  path: string
  files: FileSummary[]
  total: number
  has_more: boolean
}

export interface CreateFolderResult {
  name: string
  path: string
}

export interface FileBatchResult {
  files: FileSummary[]
  target_dir: string
}
