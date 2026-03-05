# TagHive v0.0.1

TagHive 是一个基于标签的文件管理工具，采用 Tauri + Vue3 + Python Sidecar 架构，提供高效的文件组织和检索能力。

## 功能特性

- **标签化管理**: 为文件添加多个标签，实现灵活分类
- **全文搜索**: 支持文件名搜索和标签筛选
- **文件预览**: 支持图片、视频等多媒体文件预览
- **实时监控**: 自动检测文件变更并更新索引
- **虚拟滚动**: 流畅浏览大量文件（10万+）
- **缩略图缓存**: 智能缩略图生成和缓存

## 技术架构

```
┌─────────────────────────────────────────┐
│           Frontend (Vue3 + TS)          │
│  ├─ Element Plus UI                    │
│  ├─ Pinia 状态管理                      │
│  └─ Vue Virtual Scroller               │
├─────────────────────────────────────────┤
│           Tauri (Rust)                  │
│  ├─ 窗口管理                            │
│  ├─ 系统对话框                          │
│  └─ Python Sidecar 进程管理              │
├─────────────────────────────────────────┤
│           Backend (Python)              │
│  ├─ FastAPI                             │
│  ├─ Socket.IO (实时通信)                 │
│  ├─ SQLAlchemy + SQLite                │
│  ├─ Watchdog (文件监控)                  │
│  └─ Pillow (缩略图生成)                  │
└─────────────────────────────────────────┘
```

## 快速开始

### 环境要求

- Node.js 20+
- Python 3.11+
- Rust 1.75+

### 安装依赖

```bash
# 安装前端依赖
cd src-ui
npm install

# 安装 Python 依赖
cd ../src-python
pip install -r requirements.txt
```

### 开发模式运行

```bash
# 启动 Python Sidecar
cd src-python
python -m app.main

# 启动前端（新终端）
cd src-ui
npm run dev

# 或使用 Tauri 运行
cd src-tauri
cargo tauri dev
```

### 构建生产版本

```bash
# 构建前端
cd src-ui
npm run build

# 构建 Tauri 应用
cd ../src-tauri
cargo tauri build
```

## 项目结构

```
TagHive/
├── src-ui/                 # Vue3 前端
│   ├── src/
│   │   ├── api/           # API 客户端
│   │   ├── components/    # 组件
│   │   ├── stores/        # Pinia stores
│   │   ├── views/         # 页面
│   │   └── types/         # TypeScript 类型
│   └── package.json
├── src-tauri/             # Tauri 应用
│   ├── src/               # Rust 源码
│   └── Cargo.toml
├── src-python/            # Python Sidecar
│   ├── app/
│   │   ├── api/          # FastAPI 路由
│   │   ├── core/         # 核心业务逻辑
│   │   ├── db/           # 数据库模型
│   │   └── services/     # 服务
│   └── requirements.txt
└── docs/                  # 文档
```

## API 文档

### REST API

- `GET /api/health` - 健康检查
- `GET /api/files` - 搜索文件
- `GET /api/files/{id}` - 获取文件详情
- `PUT /api/files/{id}/tags` - 更新文件标签
- `GET /api/tags` - 获取所有标签
- `POST /api/tags` - 创建标签
- `POST /api/workspace/scan` - 扫描工作区

### WebSocket 事件

- `file_changed` - 文件变更
- `file_deleted` - 文件删除
- `scan_progress` - 扫描进度
- `scan_completed` - 扫描完成

## 开发指南

### 添加新的 API 端点

1. 在 `src-python/app/api/routes.py` 中添加路由
2. 在 `src-ui/src/api/` 中添加对应的客户端方法
3. 在 `src-ui/src/types/index.ts` 中添加类型定义

### 添加新组件

1. 在 `src-ui/src/components/` 创建组件
2. 遵循 Vue3 Composition API 风格
3. 使用 Element Plus 组件库

## 许可证

MIT License
