# TagHive 界面模块命名索引

命名版本：1 · 2026-11-12。后续修改可直接指定本页的固定编号或中文名称。

本页与 HTML 审查报告由 `scripts/ui_module_registry.py` 共用命名源数据生成。修改命名表后运行 `src-python/.venv/Scripts/python.exe scripts/build_optimization_results.py`，不要单独修改生成结果。源码行号为生成时定位。

## 使用约定

- 后续需求使用“编号 + 名称 + 改动”，也可直接使用中文名称；例如 UI-09 文件详情栏。
- UI 表示主界面区域，末两位子编号表示其内部模块；DLG 表示弹窗或编辑浮层，CTX 表示右键菜单。编号不随位置、尺寸或主题改变，新增模块追加编号，删除后的编号不复用。
- 布局图表示区域关系，并非所有状态同时出现的截图。条件栏、浮动导航和弹窗按使用状态显示；抽屉形态沿用 UI-09 文件详情栏。
- 文件搜索框查文件名，标签搜索框查标签定义；浏览标签页栏管理浏览位置，标签树管理文件分类标签。
- 标签定义编辑弹窗修改标签本身，文件标签编辑弹窗修改当前文件的标签关联，批量标签管理弹窗修改固定的所选文件清单。
- 多选时，UI-09 文件详情栏始终跟随最后点选的活动文件；批量操作指定 UI-07 批量操作栏或 DLG-04 批量标签管理弹窗。
- 本文覆盖应用内容区；系统标题栏、窗口控制按钮和系统文件选择器沿用操作系统名称。未单独编号的按钮可用所属模块名称加按钮文字指定。

## 布局位置速查

```text
UI-01 顶部菜单栏
├─ UI-02 左侧导航栏
│  ├─ UI-02-01 应用标识区
│  ├─ UI-02-02 工作区切换区
│  └─ UI-02-03 标签管理区 / UI-02-08 折叠标签捷径区
├─ UI-12-01 左侧宽度调节条
├─ 中央内容列（从上到下）
│  ├─ UI-03 主工具栏
│  ├─ UI-04 浏览标签页栏
│  ├─ UI-05 时长覆盖栏（按需）
│  ├─ UI-06 筛选摘要栏（按需）
│  ├─ UI-07 批量操作栏（有选择时）
│  ├─ UI-08 文件浏览区
│  ├─ UI-10 查询提示栏（失败时）
│  └─ UI-11 底部状态栏
├─ UI-12-02 详情宽度调节条
└─ UI-09 文件详情栏（窄窗为抽屉）
   ├─ UI-09-01 文件预览区
   ├─ UI-09-02 文件属性区
   └─ UI-09-03 文件标签区
```

布局示意和完整条件请结合下表；并非所有区域同时出现。

## 主布局模块

| 编号 | 名称 | 位置、职责与显示条件 | 代码定位 |
| --- | --- | --- | --- |
| UI-01 | 顶部菜单栏 | 窗口内容最上方；文件、编辑、工具、帮助菜单。<br>显示：常驻。 | [src-ui/src/components/AppMenuBar.vue](src-ui/src/components/AppMenuBar.vue) L2 · `class="app-menu-bar"` |
| UI-02 | 左侧导航栏 | 左列整体；包含标识、工作区切换和标签管理。<br>显示：随窗口宽度与侧栏显隐偏好展开、折叠或隐藏。 | [src-ui/src/views/MainLayout.vue](src-ui/src/views/MainLayout.vue) L6 · `class="sidebar"` |
| UI-03 | 主工具栏 | 中列顶部；文件搜索、筛选入口和浏览设置。<br>显示：常驻；按中列可用宽度切换一行或两行。 | [src-ui/src/views/MainLayout.vue](src-ui/src/views/MainLayout.vue) L95 · `class="toolbar"` |
| UI-04 | 浏览标签页栏 | 主工具栏下方；切换、关闭、新建浏览位置标签页。<br>显示：常驻；与文件分类标签分开命名。 | [src-ui/src/components/BrowserTabsBar.vue](src-ui/src/components/BrowserTabsBar.vue) L2 · `class="tabs-bar"` |
| UI-05 | 时长覆盖栏 | 浏览标签页栏下方；媒体时长覆盖率、补探测进度与取消入口。<br>显示：按时长排序时显示。 | [src-ui/src/components/DurationCoverage.vue](src-ui/src/components/DurationCoverage.vue) L2 · `class="coverage"` |
| UI-06 | 筛选摘要栏 | 文件浏览区上方；展示当前范围、关键词、类型及标签筛选摘要，可清除。<br>显示：存在关键词、类型或标签筛选时显示。 | [src-ui/src/views/MainLayout.vue](src-ui/src/views/MainLayout.vue) L270 · `class="filter-summary"` |
| UI-07 | 批量操作栏 | 文件浏览区上方；选择计数、未显示项数量、批量标签、删除与全选已加载文件。<br>显示：有文件被选中时显示，单选也显示。 | [src-ui/src/views/MainLayout.vue](src-ui/src/views/MainLayout.vue) L277 · `class="selection-toolbar"` |
| UI-08 | 文件浏览区 | 中列主体；文件、目录、浏览导航、框选与拖放反馈。<br>显示：常驻；内部内容随浏览模式切换。 | [src-ui/src/views/BrowserView.vue](src-ui/src/views/BrowserView.vue) L3 · `class="browser-view"` |
| UI-09 | 文件详情栏 | 右列整体；显示活动文件的预览、属性和文件标签。<br>显示：启用详情且有选择时显示；768–1279px 为右侧抽屉，≥1280px 停靠，<768px 隐藏。多选跟随最后点选文件。 | [src-ui/src/views/DetailPanel.vue](src-ui/src/views/DetailPanel.vue) L2 · `class="detail-panel"`<br>[src-ui/src/views/MainLayout.vue](src-ui/src/views/MainLayout.vue) L1519 · `@media (max-width: 1279px)` |
| UI-10 | 查询提示栏 | 文件浏览区下方、底部状态栏上方；查询失败说明及重试。<br>显示：查询失败时显示。 | [src-ui/src/views/MainLayout.vue](src-ui/src/views/MainLayout.vue) L300 · `class="query-error"` |
| UI-11 | 底部状态栏 | 中列底部；扫描或加载状态、已加载数量与总数。<br>显示：常驻，状态随任务变化。 | [src-ui/src/views/MainLayout.vue](src-ui/src/views/MainLayout.vue) L305 · `class="status-bar"` |
| UI-12 | 面板调节条 | 左侧导航栏和中列之间、停靠详情栏和中列之间的竖向分隔条。<br>显示：对应面板展开时显示；详情为抽屉时隐藏右侧调节条。 | [src-ui/src/views/MainLayout.vue](src-ui/src/views/MainLayout.vue) L91 · `aria-label="调整侧栏宽度"`<br>[src-ui/src/views/MainLayout.vue](src-ui/src/views/MainLayout.vue) L334 · `aria-label="调整详情宽度"` |

## 左侧导航子模块

| 编号 | 名称 | 位置、职责与显示条件 | 代码定位 |
| --- | --- | --- | --- |
| UI-02-01 | 应用标识区 | 左侧导航栏顶部；TagHive 图标与名称。<br>显示：随侧栏状态调整。 | [src-ui/src/views/MainLayout.vue](src-ui/src/views/MainLayout.vue) L7 · `class="sidebar-header"` |
| UI-02-02 | 工作区切换区 | 标识区下方；全局视图、工作区清单、添加和移除入口。<br>显示：侧栏展开时显示。 | [src-ui/src/views/MainLayout.vue](src-ui/src/views/MainLayout.vue) L15 · `class="workspace-panel"` |
| UI-02-03 | 标签管理区 | 工作区切换区下方；标签标题、新建和管理入口，以及搜索、筛选模式和标签树整体。<br>显示：侧栏展开时显示。 | [src-ui/src/views/TagPanel.vue](src-ui/src/views/TagPanel.vue) L2 · `class="tag-panel"` |
| UI-02-04 | 标签搜索框 | 标签管理区内；按名称查找标签定义。<br>显示：标签管理模式关闭时显示。 | [src-ui/src/views/TagPanel.vue](src-ui/src/views/TagPanel.vue) L26 · `class="tag-search"` |
| UI-02-05 | 标签筛选模式条 | 标签搜索框下方；含子标签、仅本标签及清除标签筛选。<br>显示：标签管理模式关闭时显示。 | [src-ui/src/views/TagPanel.vue](src-ui/src/views/TagPanel.vue) L37 · `class="tag-filter-mode"` |
| UI-02-06 | 标签树 | 标签管理区主体；标签层级、图标、名称、文件计数与拖动。<br>显示：侧栏展开时显示；管理模式下可多选标签定义。 | [src-ui/src/views/TagPanel.vue](src-ui/src/views/TagPanel.vue) L91 · `class="tag-list"` |
| UI-02-07 | 标签管理操作条 | 标签树上方；已选标签数量、全选和删除。<br>显示：标签管理模式开启时显示；操作对象为标签定义。 | [src-ui/src/views/TagPanel.vue](src-ui/src/views/TagPanel.vue) L60 · `class="manage-hint"` |
| UI-02-08 | 折叠标签捷径区 | 侧栏折叠后的窄列；以图标或色点快速筛选标签。<br>显示：侧栏折叠时显示。 | [src-ui/src/views/MainLayout.vue](src-ui/src/views/MainLayout.vue) L66 · `class="sidebar-collapsed-tags"` |

## 主工具栏子模块

| 编号 | 名称 | 位置、职责与显示条件 | 代码定位 |
| --- | --- | --- | --- |
| UI-03-01 | 侧栏折叠按钮 | 主工具栏左端；展开或折叠左侧导航栏。<br>显示：桌面宽度显示。 | [src-ui/src/views/MainLayout.vue](src-ui/src/views/MainLayout.vue) L102 · `@click="appStore.toggleSidebar()"` |
| UI-03-02 | 文件搜索框 | 主工具栏左侧；按文件名搜索，范围跟随当前浏览标签页。<br>显示：常驻。 | [src-ui/src/components/SearchBar.vue](src-ui/src/components/SearchBar.vue) L5 · `aria-label="搜索文件名"` |
| UI-03-03 | 文件类型筛选器 | 文件搜索框旁；全部、图片、视频、文档、音频。<br>显示：常驻。 | [src-ui/src/components/SearchBar.vue](src-ui/src/components/SearchBar.vue) L16 · `@command="handleTypeFilter"` |
| UI-03-04 | 重新扫描入口 | 主工具栏右侧；重新扫描当前或全部工作区。<br>显示：常驻，忙碌时反馈加载状态。 | [src-ui/src/views/MainLayout.vue](src-ui/src/views/MainLayout.vue) L115 · `:title="appStore.isGlobalView ? '重新扫描所有工作区'` |
| UI-03-05 | 排序菜单 | 主工具栏右侧；名称、修改时间、大小、时长及升降序。<br>显示：常驻。 | [src-ui/src/views/MainLayout.vue](src-ui/src/views/MainLayout.vue) L119 · `@command="handleSortCommand"` |
| UI-03-06 | 浏览模式选择器 | 主工具栏右侧；全部文件、蜂巢导航、文件夹树窗、资源管理器模式。<br>显示：常驻。 | [src-ui/src/views/MainLayout.vue](src-ui/src/views/MainLayout.vue) L161 · `popper-class="browse-mode-dropdown"` |
| UI-03-07 | 视图切换器 | 主工具栏右侧；文件网格和列表切换。<br>显示：常驻；实际呈现取决于当前浏览模式。 | [src-ui/src/views/MainLayout.vue](src-ui/src/views/MainLayout.vue) L187 · `class="view-mode-group"` |
| UI-03-08 | 卡片大小与密度面板 | 卡片大小按钮展开的浮层；卡片尺寸滑块与紧凑密度开关。<br>显示：网格视图中打开卡片大小面板时显示。 | [src-ui/src/views/MainLayout.vue](src-ui/src/views/MainLayout.vue) L218 · `class="size-slider-panel"` |
| UI-03-09 | 显示与主题区 | 主工具栏右端；详情显隐、浅深色主题；空间不足时收进更多菜单。<br>显示：宽工具栏直接显示，紧凑工具栏通过更多菜单显示。 | [src-ui/src/views/MainLayout.vue](src-ui/src/views/MainLayout.vue) L237 · `@click="appStore.toggleDetailPanel()"`<br>[src-ui/src/views/MainLayout.vue](src-ui/src/views/MainLayout.vue) L249 · `:icon="MoreFilled"` |

## 文件浏览子模块

| 编号 | 名称 | 位置、职责与显示条件 | 代码定位 |
| --- | --- | --- | --- |
| UI-08-01 | 文件网格 | 文件浏览区内的文件网格容器；负责排列、滚动与加载。<br>显示：全部文件或导航模式的网格视图；资源管理器模式另有网格容器。 | [src-ui/src/components/FileScrollerArea.vue](src-ui/src/components/FileScrollerArea.vue) L6 · `class="scroller grid-view"`<br>[src-ui/src/views/BrowserView.vue](src-ui/src/views/BrowserView.vue) L247 · `class="explorer-grid" role="listbox"` |
| UI-08-02 | 文件列表 | 文件浏览区内的虚拟列表容器；按行浏览与加载文件。<br>显示：全部文件或导航模式的列表视图。 | [src-ui/src/components/FileScrollerArea.vue](src-ui/src/components/FileScrollerArea.vue) L61 · `class="scroller list-view"` |
| UI-08-03 | 文件卡片 | 网格中的单个文件单元；缩略图、名称、标签、选中与等待状态。<br>显示：文件网格内重复显示。 | [src-ui/src/components/FileCard.vue](src-ui/src/components/FileCard.vue) L3 · `class="file-card"` |
| UI-08-04 | 文件列表项 | 列表中的单个文件行；文件信息和选中状态。<br>显示：文件列表内重复显示。 | [src-ui/src/components/FileListItem.vue](src-ui/src/components/FileListItem.vue) L3 · `class="file-list-item"` |
| UI-08-05 | 目录路径栏 | 资源管理器模式顶部的面包屑路径；逐级返回目录。<br>显示：资源管理器模式显示。 | [src-ui/src/views/BrowserView.vue](src-ui/src/views/BrowserView.vue) L217 · `class="explorer-breadcrumb"` |
| UI-08-06 | 目录卡片区 | 资源管理器模式中文件网格前的子目录卡片；目录封面、名称和进入入口。<br>显示：资源管理器模式且存在子目录时显示。 | [src-ui/src/views/BrowserView.vue](src-ui/src/views/BrowserView.vue) L251 · `class="explorer-dir-cell"`<br>[src-ui/src/components/FolderCard.vue](src-ui/src/components/FolderCard.vue) L3 · `class="folder-card"` |
| UI-08-07 | 蜂巢导航窗 | 悬浮的蜂巢目录导航；包括收起图标、目录六边形和返回上级入口。<br>显示：蜂巢导航模式显示；位置可拖动。 | [src-ui/src/components/HoneycombTree.vue](src-ui/src/components/HoneycombTree.vue) L9 · `class="hc-float"` |
| UI-08-08 | 目录树导航窗 | 悬浮的树形目录导航；包括收起图标、可拖动标题和目录树。<br>显示：文件夹树窗模式显示；与左侧标签树分开命名。 | [src-ui/src/components/FolderTreePanel.vue](src-ui/src/components/FolderTreePanel.vue) L10 · `class="ft-float"` |
| UI-08-09 | 空状态与加载提示区 | 文件浏览区内的无工作区引导、空目录、无结果和加载更多提示。<br>显示：按数据和请求状态显示，位置随模式变化。 | [src-ui/src/views/BrowserView.vue](src-ui/src/views/BrowserView.vue) L11 · `class="empty-state-container"`<br>[src-ui/src/views/BrowserView.vue](src-ui/src/views/BrowserView.vue) L302 · `class="explorer-empty"`<br>[src-ui/src/views/BrowserView.vue](src-ui/src/views/BrowserView.vue) L66 · `class="load-more"` |
| UI-08-10 | 框选与拖放反馈层 | 文件浏览区上的框选矩形、外部拖入高亮和文件接收标签的反馈。<br>显示：框选或拖放交互期间显示。 | [src-ui/src/views/BrowserView.vue](src-ui/src/views/BrowserView.vue) L39 · `class="lasso-rect"`<br>[src-ui/src/views/BrowserView.vue](src-ui/src/views/BrowserView.vue) L4 · `'external-drop-active':`<br>[src-ui/src/components/FileScrollerArea.vue](src-ui/src/components/FileScrollerArea.vue) L46 · `class="tag-drop-badge"` |

## 详情、状态与调节子模块

| 编号 | 名称 | 位置、职责与显示条件 | 代码定位 |
| --- | --- | --- | --- |
| UI-09-01 | 文件预览区 | 文件详情栏上部；图片、视频播放器或类型图标。<br>显示：跟随活动文件类型显示。 | [src-ui/src/views/DetailPanel.vue](src-ui/src/views/DetailPanel.vue) L10 · `class="preview"` |
| UI-09-02 | 文件属性区 | 文件详情栏中部；可打开的文件名、类型、大小、路径、修改时间和媒体参数。<br>显示：有活动文件时显示。 | [src-ui/src/views/DetailPanel.vue](src-ui/src/views/DetailPanel.vue) L43 · `class="info"` |
| UI-09-03 | 文件标签区 | 文件详情栏下部；展示及增删当前活动文件的标签关联。<br>显示：有活动文件时显示；多选下也只作用于此文件。 | [src-ui/src/views/DetailPanel.vue](src-ui/src/views/DetailPanel.vue) L106 · `class="tags-section"` |
| UI-09-04 | 文件路径操作区 | 文件属性区中的路径及按钮；打开所在文件夹、展开或复制路径。<br>显示：有活动文件时显示。 | [src-ui/src/views/DetailPanel.vue](src-ui/src/views/DetailPanel.vue) L78 · `class="path-actions"` |
| UI-09-05 | 媒体参数区 | 文件属性区中的媒体时长、视频分辨率和比特率。<br>显示：当前活动文件为音频或视频时显示。 | [src-ui/src/views/DetailPanel.vue](src-ui/src/views/DetailPanel.vue) L88 · `v-if="showMediaMeta"` |
| UI-11-01 | 扫描进度区 | 底部状态栏左侧；进度条、文件计数、当前文件及取消全部扫描。<br>显示：扫描期间显示；非扫描加载时显示加载提示。 | [src-ui/src/views/MainLayout.vue](src-ui/src/views/MainLayout.vue) L308 · `class="scan-progress-container"` |
| UI-11-02 | 文件计数区 | 底部状态栏右侧；已加载文件数与当前查询总数。<br>显示：常驻。 | [src-ui/src/views/MainLayout.vue](src-ui/src/views/MainLayout.vue) L327 · `class="status-bar-right"` |
| UI-12-01 | 左侧宽度调节条 | 左侧导航栏右边界；拖动、键盘调整宽度或双击恢复。<br>显示：侧栏展开时显示。 | [src-ui/src/views/MainLayout.vue](src-ui/src/views/MainLayout.vue) L91 · `aria-label="调整侧栏宽度"` |
| UI-12-02 | 详情宽度调节条 | 停靠文件详情栏左边界；拖动、键盘调整宽度或双击恢复。<br>显示：详情停靠且可见时显示。 | [src-ui/src/views/MainLayout.vue](src-ui/src/views/MainLayout.vue) L334 · `aria-label="调整详情宽度"` |

## 弹窗与浮层模块

| 编号 | 名称 | 位置、职责与显示条件 | 代码定位 |
| --- | --- | --- | --- |
| DLG-01 | 新建标签弹窗 | 创建标签定义或子标签，设置名称、颜色和图标。<br>显示：从标签管理区或标签右键菜单打开。 | [src-ui/src/views/TagPanel.vue](src-ui/src/views/TagPanel.vue) L148 · `v-model="showCreateDialog"` |
| DLG-02 | 标签定义编辑弹窗 | 修改标签本身的名称、颜色、图标或层级。<br>显示：界面标题为“编辑标签”；从左侧标签右键菜单打开。 | [src-ui/src/views/TagPanel.vue](src-ui/src/views/TagPanel.vue) L253 · `v-model="showEditDialog"` |
| DLG-03 | 文件标签编辑弹窗 | 选择当前活动文件关联的标签，编辑对象为单个文件。<br>显示：界面标题也为“编辑标签”；从右侧文件标签区打开。 | [src-ui/src/views/DetailPanel.vue](src-ui/src/views/DetailPanel.vue) L140 · `v-model="showTagDialog"` |
| DLG-04 | 批量标签管理弹窗 | 为固定的所选文件清单添加或移除标签，显示已有标签覆盖数。<br>显示：从批量操作栏打开。 | [src-ui/src/components/BatchOperations.vue](src-ui/src/components/BatchOperations.vue) L4 · `v-model="showAddTagsDialog"` |
| DLG-05 | 文件删除确认弹窗 | 展示固定文件名称清单、系统回收站说明和失败重试。<br>显示：批量操作栏、文件右键菜单或 Delete 调起；单文件也复用。 | [src-ui/src/components/BatchOperations.vue](src-ui/src/components/BatchOperations.vue) L84 · `v-model="showDeleteDialog"` |
| DLG-06 | 文件重命名弹窗 | 编辑文件名并提示名称校验结果；扩展名变化另行确认。<br>显示：文件右键菜单或 F2 调起。 | [src-ui/src/views/BrowserView.vue](src-ui/src/views/BrowserView.vue) L455 · `v-model="showRenameDialog"` |
| DLG-07 | 文件移动复制弹窗 | 选择目标工作区、目标目录或内联新建目录。<br>显示：从文件或导航目录的移动、复制操作打开。 | [src-ui/src/views/BrowserView.vue](src-ui/src/views/BrowserView.vue) L483 · `v-model="showFileOpDialog"` |
| DLG-08 | 外部拖入目标弹窗 | 把外部拖入的文件移动到选定目录；包括目录选择与内联新建目录。<br>显示：外部文件拖入后打开；当前界面标题为“选择移动目标目录”。 | [src-ui/src/views/BrowserView.vue](src-ui/src/views/BrowserView.vue) L609 · `v-model="showImportDialog"` |
| DLG-09 | 目录封面选择弹窗 | 从目录内媒体选择目录卡片封面。<br>显示：目录卡片右键菜单的目录内选封面操作打开。 | [src-ui/src/views/BrowserView.vue](src-ui/src/views/BrowserView.vue) L433 · `v-model="showCoverPicker"` |
| DLG-10 | 新建子目录弹窗 | 在导航中指定的目录下新建子目录。<br>显示：蜂巢导航窗或目录树导航窗的右键菜单打开。 | [src-ui/src/components/HoneycombTree.vue](src-ui/src/components/HoneycombTree.vue) L180 · `v-model="showDlg"`<br>[src-ui/src/components/FolderTreePanel.vue](src-ui/src/components/FolderTreePanel.vue) L111 · `v-model="showCreateDialog"` |
| DLG-11 | 标签包导入导出向导 | 标签包预览、标签与文件匹配、导入结果及导出流程。<br>显示：顶部文件菜单的导入或导出标签包入口打开。 | [src-ui/src/views/TagTransferDialog.vue](src-ui/src/views/TagTransferDialog.vue) L4 · `v-model="dialogShown"` |
| DLG-12 | 设置弹窗 | 当前工作区、主题和相关设置入口。<br>显示：顶部工具菜单的设置入口打开。 | [src-ui/src/components/SettingsDialog.vue](src-ui/src/components/SettingsDialog.vue) L9 · `class="settings-dialog"` |
| DLG-13 | 日志查看弹窗 | Sidecar 日志工具栏、行数控制和日志内容区。<br>显示：顶部工具菜单或设置中的日志入口打开。 | [src-ui/src/components/LogViewer.vue](src-ui/src/components/LogViewer.vue) L7 · `class="log-viewer-dialog"` |
| DLG-14 | 设置内扫描进度弹窗 | 设置流程中显示的扫描进度；与主界面底部扫描进度区分开命名。<br>显示：由设置内扫描流程调起。 | [src-ui/src/components/SettingsDialog.vue](src-ui/src/components/SettingsDialog.vue) L48 · `title="扫描工作区"` |
| DLG-15 | 标签图标选择面板 | 标签新建或定义编辑时的分类表情图标选择器。<br>显示：点击标签图标按钮时显示。 | [src-ui/src/views/TagPanel.vue](src-ui/src/views/TagPanel.vue) L333 · `class="emoji-picker-popup"` |

## 右键菜单模块

| 编号 | 名称 | 位置、职责与显示条件 | 代码定位 |
| --- | --- | --- | --- |
| CTX-01 | 文件右键菜单 | 文件打开、移动、复制、重命名、删除等命令。<br>显示：右键文件时显示。 | [src-ui/src/views/BrowserView.vue](src-ui/src/views/BrowserView.vue) L359 · `:virtual-ref="fileContextMenuTrigger"` |
| CTX-02 | 目录卡片右键菜单 | 选择或清除目录封面等目录卡片命令。<br>显示：右键资源管理器模式中的目录卡片时显示。 | [src-ui/src/views/BrowserView.vue](src-ui/src/views/BrowserView.vue) L403 · `:virtual-ref="dirContextMenuTrigger"` |
| CTX-03 | 导航目录右键菜单 | 蜂巢或树形导航中的新建、移动、复制等目录命令。<br>显示：右键导航目录时显示；菜单项随导航类型与节点变化。 | [src-ui/src/components/HoneycombTree.vue](src-ui/src/components/HoneycombTree.vue) L152 · `:virtual-ref="ctxAnchorEl"`<br>[src-ui/src/components/FolderTreePanel.vue](src-ui/src/components/FolderTreePanel.vue) L85 · `:virtual-ref="ctxTrigger"` |
| CTX-04 | 标签右键菜单 | 新建子标签、编辑和删除标签定义。<br>显示：非管理模式下右键左侧标签时显示。 | [src-ui/src/views/TagPanel.vue](src-ui/src/views/TagPanel.vue) L227 · `:virtual-ref="contextMenuTrigger"` |

## 需求表达示例

- 将 UI-02-02 工作区切换区的行高缩小。
- 增加 UI-03-02 文件搜索框的宽度。
- 把 UI-08-07 蜂巢导航窗的展开位置向上移动。
- 让 UI-09-02 文件属性区的路径默认展开。
- 调整 DLG-04 批量标签管理弹窗的标签间距。
