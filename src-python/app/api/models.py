"""Pydantic 数据模型"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class FileDTO(BaseModel):
    """文件数据传输对象"""
    id: int
    path: str
    name: str
    ext: Optional[str] = None
    size: int = 0
    type: str
    hash: Optional[str] = None
    modified_at: Optional[float] = None
    created_at: datetime
    updated_at: datetime
    tags: List[TagDTO] = []

    class Config:
        from_attributes = True


class FileSummaryDTO(BaseModel):
    """文件摘要（列表用）"""
    id: int
    name: str
    path: str
    type: str
    size: int
    modified_at: Optional[float] = None
    duration: Optional[float] = None
    tag_ids: List[int] = []


class TagDTO(BaseModel):
    """标签数据传输对象"""
    id: int
    name: str
    color: Optional[str] = None
    description: Optional[str] = None
    created_at: datetime
    file_count: int = 0

    class Config:
        from_attributes = True


class TagCreateDTO(BaseModel):
    """创建标签请求"""
    name: str = Field(..., min_length=1, max_length=50)
    color: Optional[str] = Field(None, pattern=r"^#[0-9a-fA-F]{6}$")
    description: Optional[str] = Field(None, max_length=200)


class TagUpdateDTO(BaseModel):
    """更新标签请求"""
    name: Optional[str] = Field(None, min_length=1, max_length=50)
    color: Optional[str] = Field(None, pattern=r"^#[0-9a-fA-F]{6}$")
    description: Optional[str] = Field(None, max_length=200)


class SearchQueryDTO(BaseModel):
    """搜索查询请求"""
    text: Optional[str] = None
    root: Optional[str] = None
    types: List[str] = []
    tags: List[int] = []
    match_all_tags: bool = False
    sort_by: Optional[str] = None
    sort_desc: bool = False
    use_fts: bool = True
    limit: Optional[int] = Field(None, ge=1, le=10000)
    offset: int = Field(0, ge=0)


class SearchResultDTO(BaseModel):
    """搜索结果"""
    files: List[FileSummaryDTO]
    total: int
    has_more: bool


class FileTagsUpdateDTO(BaseModel):
    """文件标签更新请求"""
    tag_ids: List[int]
    mode: str = "replace"  # "replace", "add", "remove"


class ScanProgressDTO(BaseModel):
    """扫描进度"""
    status: str  # "scanning", "completed", "error"
    count: int = 0
    message: Optional[str] = None


class WorkspaceDTO(BaseModel):
    """工作区"""
    path: str
    name: str


class ThumbnailRequestDTO(BaseModel):
    """缩略图请求"""
    file_id: int
    size: int = Field(200, ge=50, le=800)


class ThumbnailResponseDTO(BaseModel):
    """缩略图响应"""
    file_id: int
    url: Optional[str] = None
    exists: bool = False
