"""应用配置"""

from __future__ import annotations

import os
from pathlib import Path
from pydantic_settings import BaseSettings


def get_data_dir() -> Path:
    """获取数据目录"""
    # 优先从环境变量读取
    if data_dir := os.getenv("TAGHIVE_DATA_DIR"):
        path = Path(data_dir).expanduser()
        # 如果是相对路径，相对于当前工作目录解析
        if not path.is_absolute():
            path = Path.cwd() / path
        return path.resolve()
    # 默认使用当前工作目录下的 .taghive
    return (Path.cwd() / ".taghive").resolve()


class Settings(BaseSettings):
    """应用配置类"""
    
    # 应用信息
    app_name: str = "TagHive"
    version: str = "0.0.1"
    debug: bool = False
    
    # 数据目录（从环境变量或默认值）
    data_dir: Path = get_data_dir()
    
    # 数据库
    db_path: str = str(get_data_dir() / "taghive.db")
    
    # 缩略图缓存
    thumbs_dir: str = str(get_data_dir() / "thumbnails")
    
    # 服务器
    host: str = "127.0.0.1"
    port: int = 8721
    
    # CORS
    cors_origins: list[str] = ["*"]
    
    class Config:
        env_prefix = "TAGHIVE_"
        env_file = ".env"
        
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # 确保数据目录存在
        self.data_dir.mkdir(parents=True, exist_ok=True)
        Path(self.thumbs_dir).mkdir(parents=True, exist_ok=True)


# 全局配置实例
settings = Settings()
