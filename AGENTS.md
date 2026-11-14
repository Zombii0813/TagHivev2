# TagHIve - AGENTS.md

本文件为 Codex (Codex.ai/code) 在本仓库中工作时提供指导。

## 项目概述

TagHive 是一款基于标签的桌面文件管理工具。

## 技术栈

- **Tauri 2.0（Rust）** — 外壳层，负责窗口、原生 OS 调用，并以 sidecar 方式管理 Python 子进程的生命周期
- **Vue 3 + TypeScript** — 前端，开发期监听 `:5173`，通过 Vite 代理把 `/api` 与 `/socket.io` 转发到 Python sidecar
- **Python FastAPI** — 后端 sidecar，监听 `127.0.0.1:8721`（由 `TAGHIVE_PORT` 控制；Rust 端会自动避让占用端口），独占 SQLite 数据库与文件扫描

## 关键约束

- 前端通过 `/api` 与 `/socket.io` 调用后端；在 Tauri 容器中走真实端口，在浏览器 dev 模式下走 Vite 代理 —— 新增接口路径前缀必须保持 `/api`，否则代理与生产路由都会失配
- SQLite 中文件名搜索使用 FTS5 虚拟表 `files_fts`，由数据库触发器维护（见 `src-python/app/db/models.py:FileSearch` 注释）；写入文件元数据时不要绕过 ORM 直写 FTS 表
- 标签按 `workspace` 字段隔离；不同工作目录可以同名标签。`parent_id` 支持父子层级，删除父标签时需考虑子标签处理（当前默认弹窗询问「全部删除/层级提升」）
- 关闭主窗口时 Rust 端以非阻塞方式终止 sidecar（`taskkill /T /F` fire-and-forget，见 `src-tauri/src/sidecar.rs:stop`），窗口即时关闭；`src-python/app/utils/parent_watch.py` 的父进程监控作为兜底防止孤儿进程。新增的后台任务务必能被 taskkill/SIGTERM 强杀，或自行响应父进程退出

## 界面布局文档

- 修改界面前，先用浏览器打开 [界面布局说明](docs/ui-layout.html)，通过可点击布局图及模块表，按固定编号定位涉及区域。该 HTML 沿用原优化结果报告中的布局图、样式和完整模块说明。
- 界面布局、显示条件或职责发生变化时，更新命名源 `scripts/ui_module_registry.py`，再从项目根目录运行 `src-python/.venv/Scripts/python.exe scripts/build_optimization_results.py`，同步生成 `docs/ui-layout.html` 和优化结果报告并校验源码锚点。
- `docs/ui-layout.html` 为生成文档，不直接手改；现有模块编号不随位置调整而改变。

## 常用命令

### 一键启动

```bash
# 项目根目录执行；Tauri 会自动拉起 Python sidecar 与前端 dev server
cargo tauri dev
```

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
npm run dev          # dev server，端口 5173（strictPort）
npm run build        # 生产构建（vue-tsc 类型检查 + Vite 构建），输出至 src-ui/dist/
```

### Python

```bash
cd src-python
uv sync                                # 同步依赖（含 dev 组），首次执行会创建 src-python/.venv
uv run pytest                          # 运行 tests/ 下的所有测试
uv run pytest tests/test_repo_tags.py  # 单个测试文件
uv run pytest -k "test_name"           # 按名称过滤
uv add <package>                       # 新增运行时依赖
uv add --dev <package>                 # 新增开发依赖
```

## 代码风格

- Python
  - 函数/类定义须有中文注释，统一为 Google 规范

## 开发规范

- 每一次更新代码后，提供 Git 提交信息，由用户进行审核
  - 提交信息格式：`[<type>] <subject>`
  - `type`：feat、fix、docs、style、refactor 等
  - 示例：`[feat] 添加日志输出功能`
- 更新代码同时，检查 `README.md` 内容是否需要同步更新
- 变更应用版本号时，必须同步修改以下三处保持一致（发布版本号）：
  - `src-tauri/tauri.conf.json` 的 `version`（决定安装包版本）
  - `src-tauri/Cargo.toml` 的 `version`（改后需 `cargo check`/`cargo build` 更新 `Cargo.lock`）
  - `src-python/pyproject.toml` 的 `version`
  - 版本号 bump 与对应代码改动合并进同一个 commit；一批变更时放在最后一个 commit 或单列 `[chore] bump version to x.y.z` 收尾
  - 注：`src-ui/package.json` 与 `src-python/app/main.py` 的 `version` 仅影响开发期/API 文档标题，非发布版本号，可不强制同步
