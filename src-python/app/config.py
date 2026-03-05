"""应用配置"""

from __future__ import annotations

import os
from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """应用配置类"""
    
    # 应用信息
    app_name: str = "TagHive"
    version: str = "0.0.1"
    debug: bool = False
    
    # 数据库
    db_path: str = str(Path.home() / ".taghive" / "taghive.db")
    
    # 缩略图缓存
    thumbs_dir: str = str(Path.home() / ".taghive" / "thumbnails")
    
    # 服务器
    host: str = "127.0.0.1"
    port: int = 8721
    
    # CORS
    cors_origins: list[str] = ["*"]
    
    class Config:
        env_prefix = "TAGHIVE_"
        env_file = ".env"


# 全局配置实例
settings = Settings()
