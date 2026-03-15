# Changelog

所有项目的显著变更都将记录在此文件中。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，
并且本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### Added

- **后端缓存系统**
  - 新增 `src-python/app/core/cache.py` 模块，实现智能缓存机制
  - 支持缓存过期、LRU淘汰策略和内存管理
  - 为缩略图生成和文件扫描提供缓存支持

- **批量操作功能**
  - 新增 `src-ui/src/components/BatchOperations.vue` 组件
  - 支持批量选择文件、批量打标签、批量删除等操作
  - 提供直观的批量操作界面

- **缩略图API**
  - 新增 `src-ui/src/api/thumbnails.ts` 模块
  - 提供统一的缩略图加载和管理接口

- **Tauri构建配置**
  - 新增 `src-tauri/build.rs` 构建脚本
  - 新增 `src-tauri/icons/icon.ico` 应用程序图标

### Changed

- **缩略图服务优化**
  - 统一使用正方形尺寸，保持所有缩略图大小一致
  - 提升默认质量从 80 到 85
  - 优化缩略图生成性能

- **API路由增强**
  - 新增文件预览和下载接口
  - 支持 MIME 类型自动检测
  - 改进错误处理和响应格式

- **数据库仓库层**
  - 优化查询性能
  - 新增批量操作方法
  - 改进文件路径处理

- **扫描服务改进**
  - 提升文件扫描效率
  - 优化增量扫描逻辑
  - 改进文件变更检测

- **Tauri应用架构**
  - 重构 `src-tauri/src/lib.rs`，简化代码结构
  - 更新 `Cargo.toml` 依赖配置
  - 优化 `tauri.conf.json` 配置

- **UI组件优化**
  - 改进 `FileCard.vue` 组件样式和交互
  - 优化 `FileListItem.vue` 列表项展示
  - 更新 `BrowserView.vue` 浏览器视图
  - 改进 `DetailPanel.vue` 详情面板
  - 优化 `TagPanel.vue` 标签面板
  - 更新 `SettingsView.vue` 设置页面
  - 改进 `MainLayout.vue` 主布局

- **状态管理优化**
  - 更新 `app.ts` 应用状态管理
  - 优化 `files.ts` 文件状态管理

- **样式优化**
  - 更新 `index.css` 全局样式
  - 改进 `env.d.ts` 类型定义

### Fixed

- 修复文件扫描过程中的内存泄漏问题
- 修复缩略图生成时的并发问题
- 修复批量操作时的状态同步问题

## [0.1.0] - 2026-03-06

### Added

- 初始版本发布
- 基本的文件管理功能
- 标签管理系统
- 文件搜索功能
- 缩略图预览
- Tauri桌面应用框架

## [0.2.0] - 2026-03-08

### Added

- 新增应用内日志查看功能

### Changed

- **发布应用优化**
  - 应用仅显示用户界面, 隐藏终端日志
  - 流程问题排查, 打包流程见`README.md`

## [0.3.0] -2026-03-12

### Added

- 新增文件排序功能, 名称/修改时间/文件大小/时长(仍需测试)
- 界面底部新增状态栏, 显示文件数量
- 新增文件夹层级浏览模式功能

### Fixed

- 修复文件列表无法显示全部文件的问题
- 修复根目录文件数量统计不准确的问题
- 修复浏览模式切换时网格布局不自动调整的问题
- 修复 FTS 全文搜索功能中的变量名冲突错误
  - 将 `_fts_search` 方法的参数名从 `text` 改为 `query`
  - 避免与 SQLAlchemy 的 `text()` 函数冲突
- 修复搜索功能中工作目录隔离问题
  - `SearchBar.vue` 组件现在会自动附加当前工作区路径作为 `root` 参数
  - 确保搜索只返回当前工作区内的文件，避免显示其他工作目录的文件
- **修复切换工作目录时标签数据不更新的问题**
  - 修改后端 API `/api/tags` 支持按工作目录过滤（新增 `root` 参数）
  - 修改 `Repo.list_tags()` 方法，根据工作目录路径过滤标签
  - 标签文件数量现在只统计当前工作目录下的文件
  - 修改前端 `TagPanel.vue`，监听工作目录变化并重新加载标签
  - 切换工作目录时自动清除标签选择状态

### Changed

- **扫描文件功能优化**
  - 设置界面刷新功能移动至主界面工具栏
  - 设置界面选择工作目录自动跳转至主界面扫描文件
  - 底部状态栏新增实时扫描进度
  - 实现高效文件扫描算法
- **浏览模式重构**
  - 将浏览模式分离为两个独立维度：
    - **视图模式**：网格视图 / 列表视图（二选一）
    - **浏览范围**：全部文件 / 文件夹层级浏览（二选一）
  - 工具栏新增独立的浏览范围切换按钮组（全部/文件夹）
  - 工具栏保留视图模式切换按钮组（网格/列表）
  - 文件夹浏览模式支持网格和列表两种视图
- 优化浏览模式切换时的数据加载逻辑
- **工具栏响应式布局优化**
  - 添加多个响应式断点（1100px/900px/768px/640px/560px）
  - 窗口变小时自动隐藏排序按钮文字
  - 搜索栏宽度随窗口大小动态调整
  - 小屏幕时隐藏类型筛选按钮文字，只保留图标
- 极窄屏幕时进一步压缩间距，避免元素溢出
- **搜索功能优化**
  - 实现输入时自动搜索，无需按回车键
  - 添加 300ms 防抖机制，避免频繁请求
  - 清空搜索框时立即显示所有文件
- **更改WebView数据存储目录**
  - 开发版本更改至项目根目录下
  - 发行版本默认在应用目录下
  - 详细内容可查阅PORTABLE_MODE.md

## [0.4.0] - 2026-03-15

### Added

- **数据库性能优化**
  - 为 `files.path`、`files.type`、`files.modified_at` 添加数据库索引
  - 为 `file_tags.file_id` 和 `file_tags.tag_id` 添加复合索引
  - 预期提升搜索速度 30-50%

- **数据库连接池**
  - 使用 SQLAlchemy 连接池管理
  - 配置合理的连接池大小（5-10）
  - 提升并发请求处理能力

- **查询结果缓存层** (`src-python/app/core/query_cache.py`)
  - 实现内存缓存机制，支持 TTL 自动过期
  - 最大容量限制和 LRU 淘汰策略
  - 缓存统计信息（命中率、大小等）
  - 支持装饰器模式缓存函数结果
  - 缓存标签列表、文件夹树等相对静态数据
  - 默认过期时间 5 分钟

- **游标分页优化** (`src-python/app/core/cursor_pagination.py`)
  - 实现游标分页器 `CursorPaginator`，避免 OFFSET 深度分页性能问题
  - 支持多字段排序和前后翻页
  - 自动编码/解码游标字符串
  - 保留传统 OFFSET 分页用于小数据量场景
  - 自动根据数据量选择最优分页策略（>10000条使用游标分页）

- **并行扫描优化** (`src-python/app/core/parallel_scanner.py`)
  - 实现 `ParallelScanner` 并行扫描器，使用多线程/多进程并行扫描不同子目录
  - 实现 `AdaptiveScanner` 自适应扫描器，根据目录特征自动选择最优策略
  - 支持动态线程数调整（根据 CPU 核心数）
  - 支持任务优先级队列，优先扫描大目录
  - 预期提升扫描速度 2-4 倍

- **增量扫描改进** (`src-python/app/core/incremental_scanner.py`)
  - 实现 `IncrementalScanner` 增量扫描器，基于文件签名检测变更
  - 实现 `FileSystemWatcher` 文件系统监控器（支持 watchdog 库）
  - 实现 `SmartScanner` 智能扫描器，结合多种扫描策略
  - 支持文件签名比对（大小 + 修改时间 + inode）
  - 支持文件系统实时监控（创建/修改/删除/移动事件）
  - 支持断点续扫和扫描进度持久化

### Changed

- **数据访问层增强** (`src-python/app/db/repo.py`)
  - 新增 `list_tags_cached()` 方法 - 缓存标签列表查询
  - 新增 `get_folder_tree_cached()` 方法 - 缓存文件夹树查询
  - 新增 `invalidate_tags_cache()` 方法 - 使标签缓存失效
  - 新增 `invalidate_folder_cache()` 方法 - 使文件夹缓存失效
  - 新增 `clear_all_caches()` 方法 - 清除所有缓存
  - 新增 `search_with_cursor()` 方法 - 游标分页搜索
  - 新增 `search_with_offset()` 方法 - OFFSET 分页搜索
  - 新增 `search_optimized()` 方法 - 自动选择最优分页策略
  - 新增 `_estimate_search_count()` 方法 - 预估搜索结果数量

- **扫描服务增强** (`src-python/app/services/scan_service.py`)
  - 新增 `OptimizedScanService` 优化扫描服务类
  - 集成并行扫描和增量扫描功能
  - 支持智能扫描策略选择（增量/全量/断点续扫）
  - 支持实时监控文件变更
