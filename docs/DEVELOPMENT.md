# TagHive 开发文档

## 开发环境搭建

### 1. 安装基础工具

#### Windows

```powershell
# 安装 Node.js (使用 nvm-windows)
nvm install 20.10.0
nvm use 20.10.0

# 安装 Python
# 从 https://python.org 下载 3.11+

# 安装 Rust
# 从 https://rustup.rs 安装
```

#### macOS/Linux

```bash
# 安装 Node.js
curl -fsSL https://fnm.vercel.app/install | bash
fnm install 20
fnm use 20

# 安装 Python
brew install python@3.11

# 安装 Rust
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
```

### 2. 项目初始化

```bash
# 克隆仓库
git clone <repository-url>
cd TagHive

# 安装前端依赖
cd src-ui
npm install

# 创建 Python 虚拟环境
cd ../src-python
python -m venv venv

# Windows
venv\Scripts\activate

# macOS/Linux
source venv/bin/activate

# 安装 Python 依赖
pip install -r requirements.txt
```

### 3. 开发工作流

#### 启动开发服务器

**方式一：分别启动（推荐开发调试）**

终端 1 - 启动 Python Sidecar:
```bash
cd src-python
python -m app.main
```

终端 2 - 启动前端开发服务器:
```bash
cd src-ui
npm run dev
```

**方式二：使用 Tauri 开发模式**

```bash
cd src-tauri
cargo tauri dev
```

### 4. 项目架构详解

#### 前端架构 (Vue3)

```
src-ui/src/
├── api/              # API 客户端封装
│   ├── client.ts     # HTTP 客户端
│   ├── websocket.ts  # WebSocket 客户端
│   ├── files.ts      # 文件相关 API
│   ├── tags.ts       # 标签相关 API
│   └── workspace.ts  # 工作区 API
├── components/       # 可复用组件
│   ├── FileCard.vue      # 文件卡片（网格模式）
│   ├── FileListItem.vue  # 文件列表项（列表模式）
│   └── SearchBar.vue     # 搜索栏
├── stores/           # Pinia 状态管理
│   ├── app.ts        # 应用状态
│   ├── files.ts      # 文件状态
│   └── tags.ts       # 标签状态
├── views/            # 页面组件
│   ├── MainLayout.vue    # 主布局
│   ├── BrowserView.vue   # 文件浏览器
│   ├── TagPanel.vue      # 标签面板
│   ├── DetailPanel.vue   # 详情面板
│   └── SettingsView.vue  # 设置页面
└── types/            # TypeScript 类型定义
```

#### 后端架构 (Python)

```
src-python/app/
├── api/              # API 层
│   ├── routes.py     # REST API 路由
│   ├── models.py     # Pydantic 模型
│   └── websocket.py  # WebSocket 事件
├── core/             # 核心业务逻辑
│   ├── indexer.py    # 文件索引
│   ├── search.py     # 搜索逻辑
│   └── tag_manager.py # 标签管理
├── db/               # 数据访问层
│   ├── models.py     # SQLAlchemy 模型
│   ├── repo.py       # 仓库模式
│   └── session.py    # 数据库会话
└── services/         # 服务层
    ├── scan_service.py   # 扫描服务
    └── watch_service.py  # 文件监控
```

### 5. 数据库设计

```sql
-- files 表
CREATE TABLE files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    ext TEXT,
    size INTEGER DEFAULT 0,
    type TEXT NOT NULL,
    hash TEXT,
    modified_at REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- tags 表
CREATE TABLE tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    color TEXT,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- file_tags 关联表
CREATE TABLE file_tags (
    file_id INTEGER REFERENCES files(id),
    tag_id INTEGER REFERENCES tags(id),
    PRIMARY KEY (file_id, tag_id)
);

-- FTS5 全文搜索虚拟表
CREATE VIRTUAL TABLE files_fts USING fts5(
    name,
    content='files',
    content_rowid='id'
);
```

### 6. 开发规范

#### 代码风格

- **TypeScript**: 使用严格模式，启用所有严格类型检查
- **Python**: 遵循 PEP 8，使用类型注解
- **Rust**: 使用 `cargo fmt` 和 `cargo clippy`

#### 提交规范

```
<type>(<scope>): <subject>

<body>

<footer>
```

类型:
- `feat`: 新功能
- `fix`: 修复
- `docs`: 文档
- `style`: 格式
- `refactor`: 重构
- `test`: 测试
- `chore`: 构建/工具

### 7. 调试技巧

#### 前端调试

```typescript
// 在 stores 中添加调试日志
import { devtools } from 'pinia'

// 使用 Vue DevTools 浏览器扩展
// 查看 Pinia 状态变化
```

#### 后端调试

```python
# 开启详细日志
import logging
logging.basicConfig(level=logging.DEBUG)

# 使用断点调试
import pdb; pdb.set_trace()
```

#### 数据库调试

```bash
# 查看数据库
sqlite3 ~/.taghive/taghive.db

# 查询示例
SELECT * FROM files LIMIT 10;
SELECT * FROM tags;
SELECT * FROM file_tags;
```

### 8. 性能优化

#### 前端优化

- 使用 `vue-virtual-scroller` 处理大量文件列表
- 图片懒加载
- 使用 `v-memo` 防止不必要的重渲染
- 组件懒加载

#### 后端优化

- 数据库查询使用索引
- 批量操作（默认批次 500 条）
- 缩略图缓存
- 连接池管理

### 9. 测试

#### 运行测试

```bash
# Python 测试
cd src-python
pytest

# 前端测试（待添加）
cd src-ui
npm run test
```

#### 编写测试

```python
# test_example.py
def test_search_files():
    # 测试搜索功能
    pass
```

### 10. 发布流程

```bash
# 1. 更新版本号
# 更新 src-ui/package.json
# 更新 src-tauri/Cargo.toml
# 更新 src-tauri/tauri.conf.json
# 更新 src-python/app/__init__.py

# 2. 构建前端
cd src-ui
npm run build

# 3. 构建 Tauri 应用
cd ../src-tauri
cargo tauri build

# 4. 生成的安装包在 src-tauri/target/release/bundle/
```

## 常见问题

### Python Sidecar 启动失败

1. 检查端口 8721 是否被占用
2. 确认 Python 虚拟环境已激活
3. 检查依赖是否完整安装

### 前端无法连接后端

1. 确认 Python Sidecar 已启动
2. 检查 vite.config.ts 中的代理配置
3. 查看浏览器控制台网络请求

### 数据库错误

1. 删除 ~/.taghive/taghive.db 重新初始化
2. 检查 SQLite 版本是否支持 FTS5
3. 查看数据库日志

## 贡献指南

1. Fork 仓库
2. 创建特性分支 (`git checkout -b feature/amazing-feature`)
3. 提交更改 (`git commit -m 'feat: add amazing feature'`)
4. 推送到分支 (`git push origin feature/amazing-feature`)
5. 创建 Pull Request

## 相关资源

- [Vue3 文档](https://vuejs.org/)
- [Tauri 文档](https://tauri.app/)
- [FastAPI 文档](https://fastapi.tiangolo.com/)
- [Element Plus 文档](https://element-plus.org/)
