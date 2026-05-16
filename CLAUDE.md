# CLAUDE.md

本文件为 Claude Code (claude.ai/code) 在本仓库中工作时提供指导。

## 项目概述

TagHive 是一款基于标签的桌面文件管理工具，采用三层架构：

- **Tauri 2.0（Rust）** — 外壳层，负责窗口、原生 OS 调用，并以 sidecar 方式管理 Python 子进程的生命周期
- **Vue 3 + TypeScript** — 前端，开发期监听 `:5173`，通过 Vite 代理把 `/api` 与 `/socket.io` 转发到 Python sidecar
- **Python FastAPI** — 后端 sidecar，监听 `127.0.0.1:8721`（由 `TAGHIVE_PORT` 控制；Rust 端会自动避让占用端口），独占 SQLite 数据库与文件扫描

三者通过两条通道交互：前端 → axios/socket.io → Python；前端 → `invoke()` → Tauri 原生命令。

## 开发命令

### 一键启动（推荐）

```bash
# 项目根目录执行；Tauri 会自动拉起 Python sidecar 与前端 dev server
cargo tauri dev
```

### Python 环境配置（按优先级）

依赖由 **uv** 管理（见 `src-python/pyproject.toml`，要求 Python ≥ 3.12）。首次执行 `cd src-python && uv sync` 会创建 `src-python/.venv/`。

1. **环境变量**（最高）：`TAGHIVE_PYTHON_PATH=/path/to/python`
2. **配置文件**：`src-tauri/config.json` 中的 `python.path`（默认 `src-python/.venv/Scripts/python.exe`）
3. **自动检测**：依次检查 `~/.conda/envs/taghive_env` → `src-python/venv` → 系统 `python`

### 单独启动各层

```bash
# 仅启动 Python sidecar
cd src-python
uv run python -m app.main

# 仅启动前端
cd src-ui
npm run dev

# 启动 Tauri（需要 sidecar 与前端已就绪）
cargo tauri dev
```

### 前端

```bash
cd src-ui
npm run dev          # dev server，端口 5173
npm run build        # 生产构建（包含 vue-tsc 类型检查），输出至 src-ui/dist/
```

### Python sidecar

```bash
cd src-python
uv sync                                # 同步依赖（含 dev 组）
uv run pytest                          # 运行测试（注：tests/ 目录目前尚未建立；
                                       #   pyproject.toml 已配置 testpaths=["tests"]、asyncio_mode="auto"）
uv run pytest tests/test_foo.py        # 单个测试文件
uv run pytest -k "test_name"           # 按名称过滤
uv add <package>                       # 新增运行时依赖
uv add --dev <package>                 # 新增开发依赖
```

### 生产构建

```bash
python scripts/build-sidecar.py        # 通过 pyinstaller 将 Python sidecar 打包为单文件
cargo tauri build                      # 完整应用打包（msi/nsis/dmg/AppImage）
```

## 架构

### 数据流

```
[Vue 3 UI] ── axios/HTTP    ──► [FastAPI :8721]  ──► SQLite (.taghive/data/)
[Vue 3 UI] ── socket.io     ──► [FastAPI :8721]    （文件变更、扫描进度等实时事件）
[Vue 3 UI] ── invoke()      ──► [Tauri Rust 命令]   （选择文件夹、打开文件等原生能力）
```

### 数据存储（便携模式优先）

默认便携模式：所有数据写入 `{运行目录}/.taghive/`（开发期为项目根，生产为 exe 同级目录）。在 exe 旁创建 `use-system-data-dir` 文件可切换为 `%LOCALAPPDATA%/com.taghive.app/`。Tauri 启动时会向 sidecar 注入 `TAGHIVE_DATA_DIR` 环境变量；Python 端的 `app/config.py:get_data_dir()` 读取该变量决定 `taghive.db` 与 `thumbnails/` 的位置。

### Python Sidecar（`src-python/`）

- `app/main.py` — FastAPI 应用入口，定义 `lifespan`（启动时初始化数据库、拉起 `WatchService`；退出时停止监控），并将 Socket.IO 包裹为 ASGI 应用
- `app/api/routes.py` — 所有 REST 端点（`/api` 前缀）
- `app/api/websocket.py` — Socket.IO 服务器；`app/api/thumbnails.py` 单独提供缩略图静态资源
- `app/api/models.py` — Pydantic 请求/响应 DTO
- `app/db/` — SQLAlchemy 模型（`File`、`Tag`）、`Repo` 数据访问类、会话管理；`session.py:_ensure_schema()` 在启动时执行 `ALTER TABLE` 完成增量迁移
- `app/core/` — 搜索引擎、文件索引（`indexer.build_file_meta`）、增量/并行扫描器、查询缓存、游标分页、标签管理、异步缩略图
- `app/services/` — `ScanService`（全量扫描）、`WatchService`（基于 watchdog 的实时监控）、`ThumbnailService`
- `app/utils/` — 文件类型识别、哈希、媒体信息（pymediainfo）

### Tauri 层（`src-tauri/`）

- `src/lib.rs` — 全部 Tauri 命令：`select_folder`、`open_file`、`open_folder`、`create_folder`、`cmd_start_sidecar`、`cmd_stop_sidecar`、`get_sidecar_logs`、`open_logs_folder`
- `src/sidecar.rs` — `PythonSidecar` 结构体；`find_available_port(8721)` 自动避让端口冲突；Windows 上为打包版本设置 `CREATE_NO_WINDOW` 隐藏控制台
- `config.json` — Python 解释器路径与数据目录配置（**非** Tauri 官方的 `tauri.conf.json`）

### Vue 前端（`src-ui/src/`）

技术栈：Vue 3 Composition API + Pinia + Element Plus + vue-virtual-scroller + Tailwind CSS + socket.io-client。

- `views/MainLayout.vue` — 根布局：可折叠侧栏（TagPanel） + 工具栏 + BrowserView + DetailPanel
- `views/BrowserView.vue` — 文件浏览器，含两种模式：`'all'`（搜索）与 `'folder'`（文件夹树 + 内容）。处理拖放（标签→文件、外部文件导入）、右键菜单与虚拟滚动
- `views/TagPanel.vue` — 左侧标签列表，支持拖动排序，点击触发筛选
- `views/DetailPanel.vue` — 右侧详情面板
- `stores/files.ts` — 文件列表、搜索、文件夹浏览、选中态、`gridItemSize`
- `stores/tags.ts` — 标签列表与排序（按工作区持久化到 localStorage）
- `stores/app.ts` — 主题、侧栏可见性、当前工作区路径
- `api/` — axios 薄封装：`files.ts`、`tags.ts`、`folders.ts`、`thumbnails.ts`、`websocket.ts`
- `utils/drag.ts` — 拖放工具；`_tagDragInProgress` 全局标志用于隔离标签拖动与外部文件导入拖动

### 关键设计模式

**标签顺序**：以 localStorage 键 `taghive:tag-order:{root_path}`（无工作区时为 `__global__`）持久化；store 在每次加载时把已保存顺序与当前标签 ID 合并。

**工作区隔离**：标签通过数据库 `workspace` 列与工作区路径绑定；切换工作区时 `TagPanel` 会重新拉取标签。

**浏览模式切换**：`fileStore.browseMode` 在 `'all'`（调用 `fileStore.search()`）与 `'folder'`（调用 `fileStore.loadFolderContents(path)`）之间切换；两种模式共用同一套网格/列表渲染。

**拖放隔离**：标签拖动与外部文件导入拖动必须严格分离。`setTagDragData()` 设置 `_tagDragInProgress = true`；`clearTagDragState()`（在标签 `dragend` 中调用）将其复位。文件单元格的 `drop` 处理使用 `@drop.prevent.stop`，避免冒泡到根 `.browser-view` 的 drop handler。

**WatchService 生命周期**：`WatchService` 在 FastAPI `lifespan` 启动阶段实例化（`main.py:55`）并保存在 `app.state.watch_service`，关闭阶段调用 `stop()`。修改启动顺序时务必注意对其他 startup hook 的影响。

**Schema 迁移**：`session.py:_ensure_schema()` 通过 `ALTER TABLE` 增量加列，避免破坏既有数据；新增字段时在此处补上即可。

**缩略图 URL**：`src-ui/src/api/thumbnails.ts` 拼装 `/api/thumbnails/{file_id}`；Python 端从缩略图缓存目录提供。

## 端口与环境变量速查

| 名称 | 默认值 | 作用 |
| --- | --- | --- |
| `TAGHIVE_PORT` | 8721 | Python sidecar 监听端口（被 Rust 端按需替换为可用端口） |
| `TAGHIVE_HOST` | 127.0.0.1 | sidecar 监听地址 |
| `TAGHIVE_DATA_DIR` | `.taghive` | 数据目录；支持 `~`、相对路径、绝对路径 |
| `TAGHIVE_PYTHON_PATH` | — | 覆盖 `config.json` 与自动检测，用于临时切换 Python |
