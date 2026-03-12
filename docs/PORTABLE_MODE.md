# TagHive 数据目录说明

## 默认行为：便携模式

**TagHive 默认以便携模式运行**，所有数据（包括应用数据、WebView 缓存、日志等）都存储在应用安装目录下的 `.taghive/` 文件夹中。

### 便携模式目录结构

```
TagHive/                          # 应用安装目录
├── TagHive.exe                   # 主程序
└── .taghive/                     # 数据根目录（自动创建）
    ├── data/                     # 应用数据
    │   ├── taghive.db            # SQLite 数据库
    │   ├── config.json           # 配置文件
    │   └── ...
    ├── webview/                  # WebView 数据（缓存、Cookie 等）
    │   ├── EBWebView/
    │   └── ...
    └── logs/                     # 日志文件
        └── sidecar.log
```

### 便携模式的优势

- ✅ **即插即用**：将应用文件夹复制到 U 盘，在任何电脑上使用
- ✅ **数据随行**：所有数据跟随应用，方便备份和迁移
- ✅ **绿色软件**：无需安装，解压即可运行
- ✅ **多实例**：可在不同目录运行多个独立实例
- ✅ **重装无忧**：系统重装后数据不会丢失

---

## 切换到标准模式（系统数据目录）

如果你希望将数据存储在系统标准位置（如 `%LOCALAPPDATA%`），可以切换到标准模式。

### 方法：创建 `use-system-data-dir` 标志文件

1. 找到 TagHive 的安装目录（包含 `TagHive.exe` 的文件夹）
2. 在该目录下创建一个名为 `use-system-data-dir` 的空文件或空文件夹
3. 重新启动 TagHive

**Windows PowerShell:**
```powershell
# 进入 TagHive 安装目录
cd "C:\Program Files\TagHive"
# 或你的自定义安装目录

# 创建标准模式标志文件
New-Item -ItemType File -Name "use-system-data-dir"
```

**Windows CMD:**
```cmd
cd "C:\Program Files\TagHive"
type nul > use-system-data-dir
```

**文件资源管理器:**
1. 打开 TagHive 安装目录
2. 右键 → 新建 → 文本文档
3. 命名为 `use-system-data-dir`（删除 `.txt` 扩展名）

### 标准模式的数据位置

启用标准模式后，数据将存储在系统默认位置：
- **Windows**: `%LOCALAPPDATA%\com.taghive.app\`
- **macOS**: `~/Library/Application Support/com.taghive.app/`
- **Linux**: `~/.local/share/com.taghive.app/`

---

## 切换回便携模式

要切换回便携模式（默认行为）：

1. 关闭 TagHive
2. 删除或重命名 `use-system-data-dir` 文件
3. 重新启动 TagHive

数据将重新存储在应用目录下的 `.taghive/` 文件夹中。

---

## 开发版本数据存储位置

开发版本（`cargo tauri dev`）的数据存储位置与生产版本略有不同：

### 开发模式目录结构

```
taghive/                          # 项目根目录
├── .taghive/                     # 数据根目录（自动创建在项目根目录）
│   ├── data/                     # 应用数据
│   │   ├── taghive.db            # SQLite 数据库
│   │   ├── config.json           # 配置文件
│   │   └── ...
│   ├── webview/                  # WebView 数据（缓存、Cookie 等）
│   │   ├── EBWebView/
│   │   └── ...
│   └── logs/                     # 日志文件
│       └── sidecar.log
├── src-tauri/
├── src-python/
└── ...
```

### 开发模式与生产模式的区别

| 数据类型 | 开发模式位置 | 生产模式位置 |
|---------|------------|------------|
| **WebView 数据** | `{project}/.taghive/webview/` | `{app_dir}/.taghive/webview/` |
| **应用数据** | `{project}/.taghive/data/` | `{app_dir}/.taghive/data/` |
| **日志文件** | `{project}/.taghive/logs/` | `{app_dir}/.taghive/logs/` |

**注意**: 开发模式下，所有数据都存储在项目根目录的 `.taghive/` 文件夹中，便于开发和调试。

### 切换到系统数据目录（开发模式）

即使在开发模式下，你也可以通过创建标志文件强制使用系统数据目录：

```powershell
# 在项目根目录创建标志文件
New-Item -ItemType File -Name "use-system-data-dir"
```

这样开发版本也会使用 `%LOCALAPPDATA%/com.taghive.app/` 存储数据。

---

## 数据迁移

### 从标准模式迁移到便携模式

```powershell
# 1. 关闭 TagHive

# 2. 备份并复制现有数据（可选）
$source = "$env:LOCALAPPDATA\com.taghive.app"
$target = "C:\Path\To\TagHive\.taghive\webview"
Copy-Item -Recurse $source $target

# 3. 删除标准模式标志（如果存在）
cd "C:\Path\To\TagHive"
Remove-Item "use-system-data-dir" -ErrorAction SilentlyContinue

# 4. 启动 TagHive
```

### 从便携模式迁移到标准模式

```powershell
# 1. 关闭 TagHive

# 2. 备份便携模式数据（可选）
$source = "C:\Path\To\TagHive\.taghive"
$backup = "$env:USERPROFILE\Desktop\taghive-backup"
Copy-Item -Recurse $source $backup

# 3. 创建标准模式标志
cd "C:\Path\To\TagHive"
New-Item -ItemType File -Name "use-system-data-dir"

# 4. 复制数据到标准位置（可选）
$target = "$env:LOCALAPPDATA\com.taghive.app"
Copy-Item -Recurse "$source\webview\*" $target

# 5. 启动 TagHive
```

---

## 注意事项

1. **权限问题**: 便携模式需要应用目录有写入权限。
   - 如果安装在 `C:\Program Files`，可能需要管理员权限
   - 建议将应用安装在用户目录，如 `C:\Users\YourName\TagHive`

2. **数据同步**: 两种模式的数据不会自动同步，切换模式时请注意数据迁移

3. **多实例**: 便携模式允许在同一台电脑上运行多个独立的 TagHive 实例，只要它们位于不同的目录

4. **自动更新**: 某些自动更新机制可能会覆盖标志文件，更新后可能需要重新创建

---

## 技术细节

### 数据目录优先级

1. 检查应用目录下是否存在 `use-system-data-dir` 文件
2. 如果存在：使用系统标准数据目录 `%LOCALAPPDATA%/com.taghive.app/`
3. 如果不存在（默认）：使用应用目录下的 `.taghive/`

### 环境变量

在便携模式下，以下环境变量会被自动设置：
- `WEBVIEW2_USER_DATA_FOLDER`: WebView2 数据目录（**必须在 main() 中、创建窗口前设置**）
- `TAGHIVE_DATA_DIR`: Python sidecar 数据目录

### 关键实现说明

**WebView2 数据目录设置时机**：
- `WEBVIEW2_USER_DATA_FOLDER` 环境变量必须在 `main()` 函数中、调用 `tauri::Builder` 之前设置
- 如果在 `setup` 钩子中设置，WebView 已经初始化，设置将无效
- 因此我们在 `src-tauri/src/main.rs` 中提前设置此环境变量

### 代码实现

数据目录逻辑位于：
- `src-tauri/src/main.rs`: 设置 `WEBVIEW2_USER_DATA_FOLDER` 环境变量
- `src-tauri/src/lib.rs`: `get_app_data_dir()`, `get_webview_data_dir()`
- `src-tauri/src/sidecar.rs`: `get_portable_data_dir()`, `get_sidecar_path()`
