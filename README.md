# TagHive

TagHive 是一个基于标签的文件管理工具，采用 Tauri + Vue3 + Python Sidecar 架构，提供高效的文件组织和检索能力。

## 功能特性

- **标签化管理**: 为文件添加多个标签，实现灵活分类
- **全文搜索**: 支持文件名搜索和标签筛选
- **文件预览**: 支持图片、视频等多媒体文件预览
- **实时监控**: 自动订阅已添加的工作区；外部新增、修改、删除、目录移动会更新索引，移动保留文件 ID 与标签
- **浏览标签页**: 浏览器式多标签页，各标签页独立保留浏览位置（目录、浏览模式、滚动位置、选中项与搜索条件），视图偏好（网格/列表、卡片大小、排序）全局共享；标签页列表跨会话保留，拖动文件到标签标题上可直接移动/复制到该标签页所在目录
- **虚拟滚动**: 流畅浏览大量文件（10万+）
- **缩略图缓存**: 智能缩略图生成和缓存
- **标签包导入导出**: 将工作区的标签树与文件标记关联导出为 `.thpack`，跨机器或跨工作区时按 (文件名 + 大小 + mtime ±2s) 自动匹配，未命中可按相对路径重定位或手动选择本地文件

## 审查优化后的操作约定

- 名称搜索统一为字面子串匹配，`%`、`_` 按普通字符查找；SQLite 支持 trigram 时自动加速长词。
- 改变工作区、目录或筛选条件会清除选择；分页、排序及同范围刷新保留选择。排序后移出加载页的选择仍保留名称清单，操作条明确显示未显示项数量。全选仅作用于**已加载文件**，状态栏显示加载量与总数。
- 查询失败会标记当前结果来自上次成功请求，并提供重试。外部文件变化仅刷新相关工作区，保留已加载深度与滚动位置。
- 批量操作固定打开对话框时的文件清单；删除逐项处理并保留失败项供重试，成功项移入系统回收站。
- 多选时，右侧详情始终显示最后点选文件的预览、属性和标签；右侧标签编辑只作用于该文件，批量操作通过文件区上方的操作条执行。
- 侧栏和详情支持拖动边界或聚焦分隔条后按方向键调宽，宽度与显隐跨会话保留。无选择时收起空详情，窄窗详情使用抽屉；隐藏详情会停止播放器并释放媒体流。桌面窗口保存尺寸、位置和最大化状态，恢复时限制在当前显示器工作区内。
- 文件区上方常驻 40px 上下文栏，范围/筛选摘要与选择操作原位切换，出现和清除筛选、选中文件均不增加栏高。选择时保留筛选详情入口，窄窗操作收进「更多」，长路径省略显示；紧凑密度在卡片大小面板切换。标签页支持左右/Home/End，文件区支持方向键、Space 选择、Enter 打开、Delete 删除、F2 重命名及 Esc 取消选择；快捷键避开输入框和弹窗，Ctrl+A 仅在文件区生效。
- 重命名时默认选中主文件名，前端即时提示无效名称，更改扩展名需要确认；后端对重命名和新建目录统一校验，拒绝路径逃逸及系统保留名称。
- 手动扫描使用全局串行队列，底部任务入口显示简短进度，点击查看当前扫描路径、进度及取消全部扫描。取消保留索引，未变化文件不写回；扫描与监听共用完整路径段忽略规则。
- 时长排序把未知值放在末尾，覆盖率与补探测进度并入固定高度底栏，与扫描共用任务浮层。可主动补探测当前范围内尚未处理的媒体，每批最多 1000 项、单线程执行；切换排序后仍可查看、取消运行中的补探测，取消在当前文件处理完成后生效。
- SQLite 自动迁移到 schema v2，使用 WAL、外键、30 秒 busy timeout 和自然排序索引；迁移保留标签层级、修复孤儿关联，失败中止启动。关联随文件/标签删除级联清理。缩略图使用 v3 缓存键，首次访问旧缓存后会重建并校正 EXIF 方向。

复现检查（使用已安装依赖）：

```powershell
cd src-python
.venv/Scripts/python.exe -m pytest -q
cd ../src-ui
npm.cmd run test:review
npm.cmd run build
cd ..
src-python/.venv/Scripts/python.exe scripts/benchmark_review.py
src-python/.venv/Scripts/python.exe scripts/build_optimization_results.py
```

基准仅使用临时合成库，输出到 `reports/optimization-benchmark-2026-11-12.json`；结果 HTML 为 `reports/taghive-optimization-results-2026-11-12.html`。阶段清单见 [实施计划](plan/refactor-review-2026-11-12.md)。`reports/` 保持现有 Git 忽略规则。

界面布局说明位于 [docs/ui-layout.html](docs/ui-layout.html)，可直接用浏览器打开。该独立 HTML 迁移自优化结果报告中的界面说明，保留原有可点击布局图、样式、全部 67 个模块的编号、职责、显示条件及代码定位，并附有后续修改的维护方式。后续可直接指定“UI-09 文件详情栏”“UI-03-02 文件搜索框”或“DLG-04 批量标签管理弹窗”等模块名称。命名源统一维护在 `scripts/ui_module_registry.py`，运行上述报告生成命令会同步更新布局说明和报告。

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
│  ├─ Pillow (图片缩略图生成)              │
│  └─ PyAV (视频首帧抽取，内置 FFmpeg)     │
└─────────────────────────────────────────┘
```

## 快速开始

### 环境要求

- Node.js 20+
- Python 3.12+
- [uv](https://docs.astral.sh/uv/)（Python 包管理器）
- Tauri CLI 2.x

> 视频缩略图由 PyAV（内置 FFmpeg 动态库）在进程内生成，无需在运行环境单独安装 ffmpeg。

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

### 多机环境比对（排查 dev 效果差异）

在多台机器上开发时，`cargo tauri dev` 的表现可能不一致（渲染差异、sidecar 启动失败、
搜索或视频功能降级）。`scripts/env-report.py` 会输出影响 dev 行为的全部环境配置，
只读采集、不修改任何文件，仅依赖 Python 标准库：

```bash
# 在每台机器上执行，报告写入 .taghive/env-report-<主机名>.json
python scripts/env-report.py

# 只看指纹与排查提示
python scripts/env-report.py --quiet

# 把两台机器的 JSON 收集到一处后逐字段对比
python scripts/env-report.py --compare pc-a.json pc-b.json
```

采集范围：OS 版本与代码页、DPI 缩放、WebView2 Runtime 版本、rustc/cargo/node/npm/uv
版本、被 `.gitignore` 忽略的 `src-tauri/config.json` 与 `.env`、Python 解释器解析结果
（复刻 `sidecar.rs` 的四级回退）、`Cargo.lock`/`package-lock.json`/`uv.lock` 指纹与关键
包实际版本、SQLite FTS5 与 PyAV/MediaInfo 可用性、PATH 上重复的 OpenSSL/MediaInfo DLL、
端口占用、Git 状态与 `core.autocrlf`。

差异高发项依次是：`src-tauri/config.json`（未纳入版本控制，决定用哪个 Python 与数据目录）、
WebView2 Runtime 版本（决定渲染行为）、`Cargo.lock` 缺失导致 tauri/wry 小版本漂移、
系统代码页与显示缩放。

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

### 一键构建（推荐）

`scripts/build.py` 把完整生产流程串成一步：环境检查 → 打包 Python Sidecar
→ 前端依赖 → `cargo tauri build`（自动构建前端并打出安装包）→ 汇总产物。

```bash
# 项目根目录执行（--project 指定 Python 环境但不切换工作目录）
uv run --project src-python python scripts/build.py
```

常用选项：

- `--skip-sidecar`：跳过 Sidecar 打包，复用已有 `src-tauri/resources/taghive-sidecar`
- `--npm-install`：强制执行 `npm install`（默认仅在缺 `node_modules` 时执行）
- `--skip-tauri`：只打 Sidecar，不跑 `cargo tauri build`（调试用）

### 分步构建

如需手动控制各步骤：

```bash
# 1. 打包 Python Sidecar
uv run --project src-python python scripts/build-sidecar.py

# 2. 构建 Tauri 应用，根目录下运行即可
cargo tauri build
```

构建完成后，安装包位于 `src-tauri/target/release/bundle/`

### 各平台输出

- **Windows**: `TagHive_<version>_x64-setup.exe` - NSIS 安装程序
  （打包目标默认限定为 NSIS，如需 MSI 请在 `src-tauri/tauri.conf.json`
  的 `bundle.targets` 中加入 `"msi"`，首次会从 GitHub 下载 WiX3 工具集）
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
│   └── pyproject.toml
├── scripts/               # 开发与构建脚本
│   ├── build.py          # 一键生产构建
│   ├── build-sidecar.py  # PyInstaller 打包 sidecar
│   ├── dev.py            # 手动启动 sidecar + 前端
│   └── env-report.py     # 环境体检与多机对比
└── docs/                  # 文档
```

## API 文档

### REST API

- `GET /api/health` - 健康检查
- `GET /api/files` - 搜索文件
- `GET /api/files/{id}` - 获取文件详情
- `GET /api/files/{id}/media-info` - 获取视频/音频的时长、分辨率、比特率（首次访问惰性探测并落库缓存，`?refresh=true` 强制重探）
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

## 数据一致性与本机连接

- 文件和目录删除统一移至回收站。回收站失败时保留索引与标签并报告错误，不会降级成永久删除。
- 批量移动、复制、导入及目录移动在异常时补偿本次磁盘操作，并回滚数据库；断电、强制结束进程不属于可执行补偿的异常，遇到此类中断请核对磁盘后重新扫描。
- 部分目录不可访问、元数据读取失败时，扫描保留不能确认已经消失的索引。带 `_`、`%` 的目录名按字面匹配。
- 搜索会组合每个标签页的关键词、类型、标签和目录范围；旧请求不会覆盖新结果。全局视图只查询当前已添加的工作区，移除工作区不会清除历史标签数据。
- 标签禁止循环层级与跨工作区父节点。更新接口省略 `parent_id` 表示保留，传 `null` 表示提升为顶级（兼容旧客户端的 `0`）；批量删除与层级提升在后端单事务完成。
- 每次启动由 Rust 生成独立随机会话，后端通过认证的健康响应核对实例身份。启动超时会显示重试与日志入口，禁止回退连接到默认端口上的其它实例。
- REST 使用 `Authorization: Bearer <会话凭据>`，Socket.IO 使用握手 `auth.token`；媒体 URL 使用仅限读取的会话查询参数。生产环境不开放凭据引导接口。
- 浏览器开发模式仍使用 Vite 的 `/api` 与 `/socket.io` 代理。独立运行 `uv run python -m app.main` 后，前端从 `/api/session` 获取开发会话；只允许本机开发来源读取。不要把本机代理暴露到公网。

## 审查回归验证

```powershell
cd src-python
uv run pytest
cd ../src-ui
npm run test:review
npm run build
cd ../src-tauri
cargo test --offline --locked --lib readiness_tests --target-dir target/review
```

测试中的磁盘删除、故障注入及数据库均使用隔离临时目录。`target/review` 可避免运行中的桌面应用锁住默认构建资源。若本机 GNU 测试运行器因 WebView2 DLL 入口失败，可按报告中的独立实例测试命令运行相同的 `instance.rs` 测试。

审查及逐项修复前后对比见 `reports/taghive-review-2026-11-11.html`；页面可离线打开、筛选和打印。
