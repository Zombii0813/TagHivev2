---
goal: 按第二轮审查报告完成 TagHive 的正确性、交互布局与容量优化
version: 2
date_created: 2026-11-12
last_updated: 2026-11-12
owner: Codex
status: 'Completed'
tags: [fix, refactor, design, performance]
---

# Introduction

![Status: Completed](https://img.shields.io/badge/status-Completed-green)

依据 `reports/taghive-optimization-review-2026-11-12.html` 最新 25 项清单实施。三个阶段顺序执行；每阶段完成相关回归后进入下一阶段。保留既有工作树改动，不自动提交或发布。

## 1. Requirements & Constraints

- **REQ-001**: 完成 R01–R19、L01–L06，记录实测结果及未实测边界。
- **SEC-001**: 文件名校验必须由后端执行；数据库迁移失败中止启动，不静默忽略。
- **CON-001**: 保持 `/api`、工作区标签隔离、ORM/触发器维护 FTS 和 sidecar 可终止约束。
- **CON-002**: 不改变发布版本，不覆盖用户已修改的 `src-python/uv.lock`、`src-tauri/Cargo.toml`。
- **GUD-001**: Python 新函数和类使用中文 Google 文档注释；README 与行为同步。
- **PAT-001**: 状态按标签页隔离；异步写操作在入口固定目标和数据，禁止 await 后重新读取活动选择。

## 2. Implementation Steps

### Implementation Phase 1

- **GOAL-001**: 阶段 A 修正可复现的操作边界；相关测试与前端构建通过。

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-001 | R01/R07：`stores/files.ts` 在查询范围改变时清选择，保存 appliedQuery/queryError；目录与搜索失败显示重试及旧结果标记 | ✅ | 2026-11-12 |
| TASK-002 | R02：`DetailPanel.vue`、`BatchOperations.vue` 捕获提交快照与 submitting，区分取消和失败 | ✅ | 2026-11-12 |
| TASK-003 | R03/R04/R12：修正 thumbnails 静态路由、根相对忽略规则及扫描一致性、统一文件名校验与大小写重命名 | ✅ | 2026-11-12 |
| TASK-004 | R11/R15：`db/session.py` 实施版本化迁移、WAL/外键及孤儿修复；`repo.py` 统一字面子串搜索，使用触发器维护的 trigram FTS 子查询（短词或不支持时 LIKE） | ✅ | 2026-11-12 |
| TASK-005 | R05/R13：共用缩略图缩放与 EXIF 方向处理；前端统一 pending/失败/重试、就绪通知与版本更新 | ✅ | 2026-11-12 |
| TASK-006 | L01：`MainLayout.vue` 工具栏按容器空间收纳低频操作，搜索保留 180px；窄窗详情抽屉 | ✅ | 2026-11-12 |

### Implementation Phase 2

- **GOAL-002**: 阶段 B 依赖阶段 A，完成资源生命周期、浏览位置保留和布局交互；回归与 UI 验证通过。

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-007 | R10/R14：`async_thumbnail.py` 限制派发 worker、版本键去重/提升优先级、负缓存、可见性淘汰和有界结果队列；依赖 TASK-005 | ✅ | 2026-11-12 |
| TASK-008 | R16：`repo.py` 跳过未变化记录，扫描取消与串行队列、任务标识、全局汇总；依赖 TASK-004 | ✅ | 2026-11-12 |
| TASK-009 | R18：`files.ts` 在刷新时保留已加载条数、选择与滚动锚点；`App.vue` 按事件路径筛选相关标签页，限制刷新频率 | ✅ | 2026-11-12 |
| TASK-010 | R06/R08/L02–L04：详情隐藏暂停媒体；固定批量清单、逐项结果与重试；筛选摘要、侧栏宽度/可见性持久化及活动文件详情/批量上下文操作条；Rust 保存窗口位置/尺寸/最大化并限制恢复边界；依赖 TASK-001、TASK-002、TASK-006 | ✅ | 2026-11-12 |
| TASK-011 | L05：标签页 tablist/方向键、原生新增按钮、文件 roving focus/Enter/Space、F2/Delete/Esc、图标名称及快捷键焦点范围 | ✅ | 2026-11-12 |

### Implementation Phase 3

- **GOAL-003**: 阶段 C 依赖阶段 B，用独立数据测容量，再完成稳定排序、封面上限与视觉整理。

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-012 | R09/R17：搜索与目录共用排序白名单、ID 兜底、未知时长末尾；封面每目录最多取 4 行；测 10k/100k 首屏与深页 P50/P95，按结果决定游标迁移 | ✅ | 2026-11-12 |
| TASK-013 | R19：按时长排序显示覆盖率；提供显式受限媒体补探测与进度/取消，避免未知时长排序误导 | ✅ | 2026-11-12 |
| TASK-014 | L06：统一密度与语义色、稳定选中边框、减少动画设置；虚拟滚动尺寸跟随偏好 | ✅ | 2026-11-12 |
| TASK-015 | 完成 Python 全量、前端回归/构建与 1000/1280/1680 窗口验证，更新 README、阶段结果 HTML 和提交建议 | ✅ | 2026-11-12 |

## 3. Alternatives

- **ALT-001**: 不把搜索范围改变后的选择保留为隐藏跨查询选择；默认清空更明确，跨页选择仍保留。
- **ALT-002**: 不立即切换全部分页为游标；先验证稳定次序与 OFFSET 容量，保留现有接口兼容。
- **ALT-003**: R19 优先显示覆盖率并提供用户控制的补探测，避免扫描后自动竞争媒体资源。

## 4. Dependencies

- **DEP-001**: 使用仓库现有 Vue、Pinia、Element Plus、SQLAlchemy、Pillow、FastAPI 和 SQLite，不新增运行依赖。
- **DEP-002**: trigram 支持通过实际 SQLite 探测；不支持时保留字面 LIKE 语义。

## 5. Files

- **FILE-001**: `src-python/app/db/{session,repo,models}.py`、`api/{routes,websocket,thumbnails}.py`。
- **FILE-002**: `src-python/app/{services,core,utils}/` 中扫描、忽略、缩略图和文件名处理。
- **FILE-003**: `src-ui/src/{stores,components,composables,views,styles,api}/` 及 `App.vue`。
- **FILE-004**: `src-python/tests/`、`src-ui/tests/review-regressions.mjs`、`scripts/`、`README.md` 和本计划。
- **FILE-005**: `src-tauri/src/{lib,window_state,window_bounds}.rs` 保存窗口偏好并修正显示器边界；不修改用户既有 Cargo.toml。

## 6. Testing

- **TEST-001**: 隔离库测试迁移幂等/外键、子串搜索与通配符、改名逃逸和 EXIF 方向。
- **TEST-002**: 真实 Pinia actions 验证选择范围、错误状态、分页刷新与无关工作区事件。
- **TEST-003**: 队列阻塞 worker 验证优先级/去重/上限；扫描验证未变化文件零 UPDATE 与取消保留索引。
- **TEST-004**: 前端 build、浏览器尺寸/键盘操作与冷缓存缩略图；所有测试文件均用隔离合成数据。
- **TEST-005**: 10k/100k 合成库容量基准，记录环境、冷/热样本、P50/P95，不把首次连接测量称为 OS 冷缓存。
- **TEST-006**: Rust 离线检查及 3 项窗口边界独立测试；原生多屏/DPI 重启行为留待实机验收。

## 7. Risks & Assumptions

- **RISK-001**: 开启外键前需兼容历史孤儿数据；仅清理无效关联，不删除真实文件或有效标签。
- **RISK-002**: 缩略图版本升级需要重建缓存，队列调度修复必须在同批改动内完成。
- **ASSUMPTION-001**: 阶段计划已获本次“分阶段进行优化”授权，阶段间继续执行，不逐项请求确认。

## 8. Related Specifications / Further Reading

- [仓库指导](../AGENTS.md)
- [优化审查](../reports/taghive-optimization-review-2026-11-12.html)
- [现有回归说明](../README.md)
- [阶段结果与验证边界](../reports/taghive-optimization-results-2026-11-12.html)
- [容量基准数据](../reports/optimization-benchmark-2026-11-12.json)

三阶段核心改动完成：Python 108 项、前端 15 项、窗口边界 3 项通过，前端构建与 Rust 离线检查通过。100k 深页 P95 由 1172.02ms 降至 148.66ms，保留 OFFSET。原报告中的真实视频、多屏/DPI、10 万真实文件扫描、封面端到端 P95、长时内存和滚动压测未全部执行，详见结果文档；“Completed”指上述实施任务完成，不代表每项原始建议都扩展实现或实机验收完毕。

用户交互偏好补充：多选时右侧信息栏跟随最后点选的活动文件，显示其预览、属性及标签；右侧标签编辑只修改该文件，批量操作保留在文件区上方。已补充真实组件渲染、媒体响应和单文件标签作用范围回归。
