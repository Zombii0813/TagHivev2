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


class FolderContentsDTO(BaseModel):
    """文件夹内容 DTO"""
    path: str
    files: List[FileSummaryDTO]
    total: int
    has_more: bool


class FolderCreateRequestDTO(BaseModel):
    """创建文件夹请求 DTO"""
    root_path: str
    parent_path: str
    name: str


class FolderCreateResultDTO(BaseModel):
    """创建文件夹结果 DTO"""
    name: str
    path: str


class FileRenameRequestDTO(BaseModel):
    """重命名文件请求 DTO"""
    new_name: str  # 仅文件名，不含路径


class FileMoveRequestDTO(BaseModel):
    """移动文件请求 DTO"""
    file_ids: List[int]
    target_dir: str


class FileCopyRequestDTO(BaseModel):
    """复制文件请求 DTO"""
    file_ids: List[int]
    target_dir: str


class FileBatchResultDTO(BaseModel):
    """批量文件操作结果 DTO"""
    files: List[FileSummaryDTO]
    target_dir: str


# ========== 标签相关 DTO ==========

class TagDTO(BaseModel):
    """标签 DTO"""
    id: int
    name: str
    color: Optional[str] = None
    icon: Optional[str] = None
    description: Optional[str] = None
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


class TagUpdateDTO(BaseModel):
    """更新标签 DTO"""
    name: Optional[str] = None
    color: Optional[str] = None
    icon: Optional[str] = None
    description: Optional[str] = None


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
