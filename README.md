# TagHive v0.0.1

TagHive 是一个基于标签的文件管理工具，采用 Tauri + Vue3 + Python Sidecar 架构，提供高效的文件组织和检索能力。

## 功能特性

- **标签化管理**: 为文件添加多个标签，实现灵活分类
- **全文搜索**: 支持文件名搜索和标签筛选
- **文件预览**: 支持图片、视频等多媒体文件预览
- **实时监控**: 自动检测文件变更并更新索引
- **虚拟滚动**: 流畅浏览大量文件（10万+）
- **缩略图缓存**: 智能缩略图生成和缓存
- **标签包导入导出**: 将工作区的标签树与文件标记关联导出为 `.thpack`，跨机器或跨工作区时按 (文件名 + 大小 + mtime ±2s) 自动匹配，未命中可按相对路径重定位或手动选择本地文件

## 技术架构

```text
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
- Python 3.12+
- [uv](https://docs.astral.sh/uv/)（Python 包管理器）
- Tauri CLI 2.x

### 安装依赖

```powershell
# 安装前端依赖
cd src-ui
npm ci

# 安装 Python 依赖（使用 uv 管理，自动创建 src-python/.venv）
cd ../src-python
uv sync --python 3.12

# 安装 Tauri CLI 2
cd ..
cargo install tauri-cli --version "^2.0.0" --locked
cargo tauri --version

# 验证 Tauri 开发模式
cargo tauri dev
```

## 开发模式运行

### 方式一：使用 Tauri 运行（推荐）

项目根目录终端运行，Tauri 会自动启动 Python Sidecar 和前端开发服务器：

```bash
cargo tauri dev
```

### Python 环境配置

项目使用 [uv](https://docs.astral.sh/uv/) 管理 Python 依赖；首次 `cd src-python && uv sync` 会自动创建 `src-python/.venv/`。Tauri 启动时按以下优先级选择 Python 解释器：

#### 1. 环境变量（最高优先级，临时覆盖）

适合临时切换 Python 环境（例如调试别处的解释器）：

```powershell
# Windows PowerShell
$env:TAGHIVE_PYTHON_PATH = "D:\path\to\python.exe"
cargo tauri dev

# Windows CMD
set TAGHIVE_PYTHON_PATH=D:\path\to\python.exe
cargo tauri dev

# Linux/macOS
export TAGHIVE_PYTHON_PATH="/path/to/python"
cargo tauri dev
```

#### 2. 配置文件（持久化配置）

编辑 `src-tauri/config.json`（默认指向 `src-python/.venv`）：

```json
{
  "python": {
    "type": "uv",
    "path": "src-python/.venv/Scripts/python.exe"
  },
  "data_dir": ".taghive"
}
```

- `python.type`: 环境类型标识（仅用于日志）
- `python.path`: Python 可执行文件路径，支持 `~` 展开为用户主目录
- `data_dir`: 数据目录路径（数据库和缩略图存储位置）
  - 相对路径：相对于软件运行目录（如 `.taghive`）
  - 绝对路径：直接使用（如 `D:/TagHiveData`）
  - `~` 开头：展开为用户主目录（如 `~/.taghive`）
  - 默认：`.taghive`（当前运行目录下）

#### 3. 自动检测（零配置）

如果没有设置环境变量和配置文件，开发模式会自动检测：

1. **uv 虚拟环境**: `src-python/.venv/Scripts/python.exe` (Windows) 或 `src-python/.venv/bin/python` (Linux/macOS)
2. **系统 Python**: `python` 或 `python3`

### 方式二：手动分别启动

如果需要单独调试前端或后端：

```bash
# 终端 1：启动 Python Sidecar
cd src-python
uv run python -m app.main

# 终端 2：启动前端开发服务器
cd src-ui
npm run dev
```

Python Sidecar 默认运行在 `http://127.0.0.1:8721`

## 构建生产版本

### 独立安装包（推荐）

独立安装包包含所有依赖，无需安装 Python 环境即可运行：

```bash
# 1. 打包 Python Sidecar
uv run scripts/build-sidecar.py

# 2. 构建 Tauri 应用，根目录下运行即可
cargo tauri build
```

构建完成后，安装包位于 `src-tauri/target/release/bundle/`

### 各平台输出

- **Windows**:
  - `TagHive_0.0.1_x64_en-US.msi` - MSI 安装程序
  - `TagHive_0.0.1_x64-setup.exe` - NSIS 安装程序
- **macOS**: `dmg` 磁盘映像
- **Linux**: `AppImage` 或 `deb` 包

### 生产模式运行

生产版本使用打包的 Python Sidecar，无需额外配置 Python 环境：

```bash
# 运行生产版本（开发测试）
cargo tauri build --debug
./target/debug/TagHive.exe  # Windows
./target/debug/TagHive      # Linux/macOS
```

### 日志查看

生产版本运行时，Python Sidecar 的日志会自动保存到日志文件中，在应用内可以通过 **设置 → 查看日志** 打开日志查看器，支持：

- 实时刷新日志
- 调整显示行数（50-5000行）
- 打开日志文件所在文件夹

## 项目结构

```text
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
- `POST /api/tags/export` - 导出当前工作区的标签树与文件标记关联（返回 `.thpack` 二进制流）
- `POST /api/tags/import/preview` - 上传 `.thpack`（请求体为 octet-stream，`workspace` 走 query 参数），返回标签冲突 + 文件匹配预览，并签发 token
- `POST /api/tags/import/relocate` - 对未匹配项执行重定位（按相对路径自动尝试 / 手动指定 file_id / 全部跳过）
- `POST /api/tags/import/commit` - 按用户裁决执行导入；单事务写入标签与文件标签关联

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
