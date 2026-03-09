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

## [0.3.0] -2026-03-08

### Added

- 新增文件排序功能, 名称/修改时间/文件大小/时长(仍需测试)
- 界面底部新增状态栏, 显示文件数量
