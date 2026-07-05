"""API 数据模型"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


# ========== 文件相关 DTO ==========

class FileSummaryDTO(BaseModel):
    """文件摘要 DTO"""
    id: int
    name: str
    path: str
    type: str
    size: int
    modified_at: Optional[float] = None
    duration: Optional[float] = None
    tag_ids: List[int] = Field(default_factory=list)

    class Config:
        from_attributes = True


class FileDTO(BaseModel):
    """文件详情 DTO"""
    id: int
    path: str
    name: str
    ext: Optional[str] = None
    size: int
    type: str
    hash: Optional[str] = None
    modified_at: Optional[float] = None
    created_at: datetime
    updated_at: datetime
    tags: List[TagDTO] = Field(default_factory=list)

    class Config:
        from_attributes = True


class SearchResultDTO(BaseModel):
    """搜索结果 DTO"""
    files: List[FileSummaryDTO]
    total: int
    has_more: bool


class FileResolveRequestDTO(BaseModel):
    """按路径解析文件 DTO"""
    paths: List[str]


class FileResolveResultDTO(BaseModel):
    """按路径解析文件结果 DTO"""
    files: List[FileSummaryDTO]
    missing_paths: List[str] = Field(default_factory=list)


class FileImportRequestDTO(BaseModel):
    """导入外部文件到指定目录 DTO"""
    paths: List[str]
    target_dir: str


class FileImportResultDTO(BaseModel):
    """导入外部文件结果 DTO"""
    files: List[FileSummaryDTO]
    target_dir: str


class SearchQueryDTO(BaseModel):
    """搜索查询 DTO"""
    text: Optional[str] = None
    root: Optional[str] = None
    types: Optional[List[str]] = None
    tags: Optional[List[int]] = None
    match_all_tags: bool = False
    sort_by: Optional[str] = None
    sort_desc: bool = False
    use_fts: bool = True
    limit: Optional[int] = None
    offset: int = 0


class FileTagsUpdateDTO(BaseModel):
    """文件标签更新 DTO"""
    tag_ids: List[int]
    mode: str = "replace"  # replace, add, remove


# ========== 文件夹相关 DTO ==========

class FolderNodeDTO(BaseModel):
    """文件夹节点 DTO - 用于树形结构"""
    name: str
    path: str
    file_count: int = 0
    children: List['FolderNodeDTO'] = Field(default_factory=list)
    is_expanded: bool = False

    class Config:
        from_attributes = True


class FolderTreeDTO(BaseModel):
    """文件夹树 DTO"""
    root_path: str
    folders: List[FolderNodeDTO]
    total_folders: int
    root_file_count: int = 0  # 根目录下的直接文件数


class ChildDirDTO(BaseModel):
    """子目录 DTO - 用于 explorer 浏览模式的目录卡片

    cover_file_ids 为该目录内（含深层）前若干个可生成缩略图的文件 id，
    供前端拼九宫格封面使用；无媒体文件时为空列表。
    cover_path 为用户自定义封面路径（优先于九宫格）；未自定义时为 None。
    """
    name: str
    path: str
    file_count: int = 0  # 直接子文件数
    cover_file_ids: List[int] = Field(default_factory=list)
    cover_path: Optional[str] = None  # 自定义封面路径（POSIX），优先于九宫格


class FolderContentsDTO(BaseModel):
    """文件夹内容 DTO"""
    path: str
    files: List[FileSummaryDTO]
    total: int
    has_more: bool
    dirs: List[ChildDirDTO] = Field(default_factory=list)  # explorer 模式的子目录（include_dirs=true 时返回）


class FolderCoverRequestDTO(BaseModel):
    """设置目录封面请求 DTO"""
    folder_path: str  # 目标目录路径（POSIX 形式）
    cover_path: str   # 作为封面的图片/视频路径（POSIX 形式）
    workspace: Optional[str] = None  # 所属工作区根，便于按工作区清理


class FolderCoverClearRequestDTO(BaseModel):
    """清除目录封面请求 DTO"""
    folder_path: str  # 目标目录路径（POSIX 形式）


class FolderCreateRequestDTO(BaseModel):
    """创建文件夹请求 DTO"""
    root_path: str
    parent_path: str
    name: str


class FolderCreateResultDTO(BaseModel):
    """创建文件夹结果 DTO"""
    name: str
    path: str


class FolderDeleteRequestDTO(BaseModel):
    """删除文件夹请求 DTO"""
    root_path: str   # 工作区根目录（用于路径安全校验）
    folder_path: str # 要删除的目录路径


class FileRenameRequestDTO(BaseModel):
    """重命名文件请求 DTO"""
    new_name: str  # 仅文件名，不含路径


class FileMoveRequestDTO(BaseModel):
    """移动文件请求 DTO

    Attributes:
        file_ids: 待移动文件 ID 列表
        target_dir: 目标目录绝对路径（可跨工作区）
        target_workspace: 目标目录所在的工作区根路径；当跨工作区移动时用于清理不再适用的标签关联，
            为空表示不做工作区清理（仅做物理移动）
    """
    file_ids: List[int]
    target_dir: str
    target_workspace: Optional[str] = None


class FileCopyRequestDTO(BaseModel):
    """复制文件请求 DTO

    Attributes:
        file_ids: 待复制文件 ID 列表
        target_dir: 目标目录绝对路径（可跨工作区）
        target_workspace: 目标目录所在的工作区根路径；当前实现下副本默认不携带原标签，
            该字段保留用于将来按工作区匹配复制标签
    """
    file_ids: List[int]
    target_dir: str
    target_workspace: Optional[str] = None


class FileBatchResultDTO(BaseModel):
    """批量文件操作结果 DTO"""
    files: List[FileSummaryDTO]
    target_dir: str


class FolderMoveRequestDTO(BaseModel):
    """移动文件夹请求 DTO

    Attributes:
        source_path: 待移动的源文件夹绝对路径
        target_dir: 目标父目录绝对路径（可跨工作区）；文件夹将作为其子目录移入
        target_workspace: 目标所在的工作区根路径；跨工作区移动时用于清理不再适用的标签关联，
            为空表示不做工作区标签清理
    """
    source_path: str
    target_dir: str
    target_workspace: Optional[str] = None


class FolderCopyRequestDTO(BaseModel):
    """复制文件夹请求 DTO

    Attributes:
        source_path: 待复制的源文件夹绝对路径
        target_dir: 目标父目录绝对路径（可跨工作区）；副本将作为其子目录写入
    """
    source_path: str
    target_dir: str


# ========== 标签相关 DTO ==========

class TagDTO(BaseModel):
    """标签 DTO"""
    id: int
    name: str
    color: Optional[str] = None
    icon: Optional[str] = None
    description: Optional[str] = None
    parent_id: Optional[int] = None
    created_at: datetime
    file_count: int = 0

    class Config:
        from_attributes = True


class TagCreateDTO(BaseModel):
    """创建标签 DTO"""
    name: str
    color: Optional[str] = None
    icon: Optional[str] = None
    description: Optional[str] = None
    workspace: Optional[str] = None  # 工作目录路径，用于标签隔离
    parent_id: Optional[int] = None  # 父标签ID，null 表示顶级标签


class TagUpdateDTO(BaseModel):
    """更新标签 DTO"""
    name: Optional[str] = None
    color: Optional[str] = None
    icon: Optional[str] = None
    description: Optional[str] = None
    parent_id: Optional[int] = None  # 传 None 不更新，传 0 清除父标签（设为顶级）


# ========== 工作区相关 DTO ==========

class WorkspaceDTO(BaseModel):
    """工作区 DTO"""
    path: str


class ScanProgressDTO(BaseModel):
    """扫描进度 DTO"""
    status: str
    count: int
    message: Optional[str] = None


# 解决前向引用
FolderNodeDTO.model_rebuild()


# ========== 标签导入导出相关 DTO ==========


class TagExportRequestDTO(BaseModel):
    """标签导出请求 DTO"""
    workspace: str
    tag_ids: Optional[List[int]] = None  # 为空表示导出 workspace 下所有标签
    include_thumbnails: bool = False     # 是否将本地 small 缩略图（仅图片/视频）以 base64 内联


class ExportedTagDTO(BaseModel):
    """导入预览中的标签条目 DTO"""
    export_id: str
    name: str
    color: Optional[str] = None
    icon: Optional[str] = None
    description: Optional[str] = None
    parent_export_id: Optional[str] = None
    conflict: bool = False               # 当前 workspace 下是否同名冲突
    existing_tag_id: Optional[int] = None


class FileMatchEntryDTO(BaseModel):
    """文件匹配预览条目 DTO"""
    rel_path: str
    name: str
    size: int
    mtime: Optional[float] = None
    tag_export_ids: List[str] = Field(default_factory=list)
    candidate_file_ids: List[int] = Field(default_factory=list)
    thumbnail: Optional[str] = None  # base64 编码的 small 缩略图，导出包未携带时为 None


class ImportPreviewDTO(BaseModel):
    """导入预览结果 DTO"""
    token: str
    schema_version: int
    exported_at: str
    source_workspace: str
    target_workspace: str
    tags: List[ExportedTagDTO]
    unique: List[FileMatchEntryDTO]
    multiple: List[FileMatchEntryDTO]
    unmatched: List[FileMatchEntryDTO]


class ImportRelocateRequestDTO(BaseModel):
    """重定位请求 DTO

    mode='manual' 时 rel_path 与 file_id 必填，将该未匹配条目锁定到指定本地文件。
    mode='skip_all' 时清空未匹配列表。
    """
    token: str
    mode: str  # 'manual' | 'skip_all'
    rel_path: Optional[str] = None
    file_id: Optional[int] = None


class ImportTagDecisionDTO(BaseModel):
    """单个标签的最终冲突裁决"""
    export_id: str
    strategy: str        # 'skip' | 'merge' | 'rename'
    new_name: Optional[str] = None  # strategy='rename' 时使用


class ImportFileDecisionDTO(BaseModel):
    """单个文件条目的最终裁决：勾选要关联的本地 file_id 列表（空 = 跳过）"""
    rel_path: str
    file_ids: List[int] = Field(default_factory=list)


class ImportCommitRequestDTO(BaseModel):
    """导入提交请求 DTO"""
    token: str
    tag_decisions: List[ImportTagDecisionDTO] = Field(default_factory=list)
    file_decisions: List[ImportFileDecisionDTO] = Field(default_factory=list)


class ImportSummaryDTO(BaseModel):
    """导入提交结果 DTO"""
    tags_created: int
    tags_reused: int
    files_linked: int
    files_skipped: int
