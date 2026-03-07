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

## 开发模式运行

### 方式一：使用 Tauri 运行（推荐）

Tauri 会自动启动 Python Sidecar 和前端开发服务器：

```bash
cd src-tauri
cargo tauri dev
```

### Python 环境配置

项目支持多种方式配置 Python 环境，按优先级自动选择：

#### 1. 环境变量（最高优先级，临时覆盖）

适合临时切换 Python 环境：

```powershell
# Windows PowerShell
$env:TAGHIVE_PYTHON_PATH = "C:\Users\YourName\.conda\envs\taghive_env\python.exe"
cargo tauri dev

# Windows CMD
set TAGHIVE_PYTHON_PATH=C:\Users\YourName\.conda\envs\taghive_env\python.exe
cargo tauri dev

# Linux/macOS
export TAGHIVE_PYTHON_PATH="$HOME/.conda/envs/taghive_env/bin/python"
cargo tauri dev
```

#### 2. 配置文件（持久化配置）

编辑 `src-tauri/config.json`：

```json
{
  "python": {
    "type": "conda",
    "path": "~/.conda/envs/taghive_env/python.exe"
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

如果没有设置环境变量和配置文件，程序会自动检测：

1. **Conda 环境**: `~/.conda/envs/taghive_env/python.exe`
2. **venv 虚拟环境**: `src-python/venv/Scripts/python.exe` (Windows) 或 `src-python/venv/bin/python` (Linux/macOS)
3. **系统 Python**: `python` 或 `python3`

### 方式二：手动分别启动

如果需要单独调试前端或后端：

```bash
# 终端 1：启动 Python Sidecar
cd src-python
python -m app.main

# 终端 2：启动前端开发服务器
cd src-ui
npm run dev
```

Python Sidecar 默认运行在 `http://127.0.0.1:8000`

## 构建生产版本

### 独立安装包（推荐）

独立安装包包含所有依赖，无需安装 Python 环境即可运行：

```bash
# 1. 打包 Python Sidecar
conda run -n taghive_env python scripts/build-sidecar.py

# 2. 构建 Tauri 应用
cd src-tauri
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
cd src-tauri
cargo tauri build --debug
./target/debug/TagHive.exe  # Windows
./target/debug/TagHive      # Linux/macOS
```

### 日志查看

生产版本运行时，Python Sidecar 的日志会自动保存到日志文件中：

- **Windows**: `%LOCALAPPDATA%\TagHive\sidecar.log`
- **macOS**: `~/Library/Application Support/TagHive/sidecar.log`
- **Linux**: `~/.local/share/TagHive/sidecar.log`

在应用内可以通过 **设置 → 查看日志** 打开日志查看器，支持：
- 实时刷新日志
- 调整显示行数（50-5000行）
- 打开日志文件所在文件夹

### 需要上传 Git 的文件

以下文件需要上传到 Git 仓库，以便其他开发者或 CI/CD 使用：

```
# PyInstaller 配置文件
src-python/taghive-sidecar.spec

# 打包脚本
scripts/build-sidecar.py

# 入口文件
src-python/sidecar_entry.py
```

**不需要上传的文件**（已添加到 .gitignore）：
- `src-tauri/resources/taghive-sidecar.exe` - 打包生成的可执行文件
- `src-python/dist/` - PyInstaller 输出目录
- `src-python/build/` - PyInstaller 构建目录

## 不同环境开发指南

### 场景 1：使用 Conda 环境

```bash
# 创建环境
conda create -n taghive_env python=3.11
conda activate taghive_env
pip install -r src-python/requirements.txt

# 配置项目（二选一）
# 方式 A：编辑配置文件
# 修改 src-tauri/config.json 中的 path 为实际路径

# 方式 B：使用环境变量
$env:TAGHIVE_PYTHON_PATH = "$(conda run -n taghive_env which python)"
```

### 场景 2：使用 venv 虚拟环境

```bash
# 创建虚拟环境
cd src-python
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/macOS
pip install -r requirements.txt

# 无需配置，程序会自动检测 src-python/venv
```

### 场景 3：使用系统 Python

```bash
# 安装依赖到系统 Python
pip install -r src-python/requirements.txt

# 无需配置，程序会自动使用系统 Python
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
