# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

TagHive is a desktop file management app built on **Tauri 2.0** (Rust shell) + **Vue 3 + TypeScript** (frontend) + **Python FastAPI** (backend sidecar). The three layers communicate as follows:

- Vue frontend (port 5173 in dev) proxies `/api` and `/socket.io` to the Python sidecar (port 8721)
- Tauri Rust layer manages the Python sidecar process lifecycle and exposes native OS commands via `invoke()`
- Python sidecar runs as a subprocess started by Tauri on app launch; it owns the SQLite database and file scanning

## Development Commands

### Full dev environment (recommended)

```bash
# From project root
# 一键构建项目并启动
cd src-tauri
cargo tauri dev
```

### Individual layer startup
```bash
# Python sidecar only
cd src-python
python -m app.main

# Frontend only
cd src-ui
npm run dev

# Tauri (requires sidecar + frontend already running)
cargo tauri dev
```

### Frontend
```bash
cd src-ui
npm run dev        # dev server on :5173
npm run build      # production build to src-ui/dist/
npm run type-check # TypeScript check
```

### Python sidecar
```bash
cd src-python
python -m pytest                         # run all tests
python -m pytest tests/test_foo.py       # single test file
python -m pytest -k "test_name"          # single test by name
```

### Production build
```bash
python scripts/build-sidecar.py   # package Python sidecar binary
cargo tauri build                  # full app bundle
```

## Architecture

### Data Flow
```
[Vue 3 UI] → axios/socket.io → [Python FastAPI :8721] → SQLite (.taghive/data/)
[Vue 3 UI] → invoke() → [Tauri Rust commands]
```

### Data Storage
By default **portable mode**: all data lives in `{project_root}/.taghive/` (dev) or `{exe_dir}/.taghive/` (production). Creating a `use-system-data-dir` file next to the exe switches to `%LOCALAPPDATA%/com.taghive.app/`. The `TAGHIVE_DATA_DIR` env var is set by Tauri at startup and read by the Python sidecar.

### Python Sidecar (`src-python/`)
- `app/main.py` — FastAPI app, lifespan (DB init + WatchService start), uvicorn entry
- `app/api/routes.py` — all REST endpoints under `/api` prefix
- `app/api/models.py` — Pydantic DTOs (request/response)
- `app/db/` — SQLAlchemy models (`File`, `Tag`), `Repo` class (data access), session management, schema migrations via `_ensure_schema()` in `session.py`
- `app/core/` — search engine, file indexer (`build_file_meta`), tag manager, thumbnail generation, incremental/parallel scanner
- `app/services/` — `ScanService` (full workspace scan), `WatchService` (file system monitoring via watchdog), `ThumbnailService`

### Tauri Layer (`src-tauri/`)
- `src/lib.rs` — all Tauri commands: `select_folder`, `open_file`, `open_folder`, `create_folder`, `cmd_start_sidecar`, `cmd_stop_sidecar`, `get_sidecar_logs`, `open_logs_folder`
- `src/sidecar.rs` — `PythonSidecar` struct that spawns and manages the Python process

### Vue Frontend (`src-ui/src/`)
- `views/MainLayout.vue` — root layout: collapsible sidebar (TagPanel) + toolbar + BrowserView + DetailPanel
- `views/BrowserView.vue` — file browser with two modes: `'all'` (search-based) and `'folder'` (tree + contents). Handles drag-and-drop (tag→file and external file import), context menus, virtual scrolling via `vue-virtual-scroller`
- `views/TagPanel.vue` — left sidebar tag list; drag-reorder tags, click to filter files
- `views/DetailPanel.vue` — right panel showing selected file details and tags
- `stores/files.ts` — file list state, search, folder browsing, selection, `gridItemSize`
- `stores/tags.ts` — tag list, tag order (persisted to localStorage per workspace), selection
- `stores/app.ts` — theme, sidebar/panel visibility, current workspace path
- `api/` — thin axios wrappers: `files.ts`, `tags.ts`, `folders.ts`, `thumbnails.ts`, `websocket.ts`
- `utils/drag.ts` — drag-and-drop utilities; `_tagDragInProgress` global flag isolates tag drags from external file-import drags

### Key Design Patterns

**Tag order**: Stored in `localStorage` under key `taghive:tag-order:{root_path}` (or `__global__`). The store merges saved order with current tag IDs on each load.

**Workspace isolation**: Tags are scoped to a workspace path via the `workspace` column in the DB. The `TagPanel` reloads tags on workspace change.

**Browse modes**: `fileStore.browseMode` switches between `'all'` (calls `fileStore.search()`) and `'folder'` (calls `fileStore.loadFolderContents(path)`). Both modes share the same grid/list rendering in BrowserView.

**Drag-and-drop isolation**: Tag drags and external file-import drags must be kept separate. `setTagDragData()` sets `_tagDragInProgress = true`; `clearTagDragState()` (called in tag `dragend`) resets it. File cell drop handlers use `@drop.prevent.stop` to prevent bubbling to the root `.browser-view` drop handler.

**DB schema migrations**: `session.py:_ensure_schema()` runs `ALTER TABLE` statements at startup to add new columns without dropping existing data.

**Thumbnail URL**: `src-ui/src/api/thumbnails.ts` constructs `/api/thumbnails/{file_id}` URLs; the Python endpoint serves them from the thumbnail cache.
