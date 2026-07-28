use std::fs::{self, OpenOptions};
use std::io::Write;
use std::path::PathBuf;
use std::process::Stdio;
use std::time::Duration;
use tauri::async_runtime::JoinHandle;
use tauri::{Manager, Runtime};
use tokio::io::{AsyncBufReadExt, BufReader};
use tokio::process::{Child, Command};
use tokio::time::sleep;
use serde::Deserialize;

/// 日志文件大小限制：10MB
const LOG_FILE_MAX_SIZE: u64 = 10 * 1024 * 1024;

/// Python 配置
#[derive(Debug, Deserialize)]
struct PythonConfig {
    #[serde(rename = "type")]
    env_type: String,
    path: String,
}

#[derive(Debug, Deserialize)]
struct Config {
    python: PythonConfig,
    #[serde(default = "default_data_dir")]
    data_dir: String,
}

fn default_data_dir() -> String {
    ".taghive".to_string()
}

impl Config {
    fn load(project_dir: &PathBuf) -> Option<Self> {
        let config_path = project_dir.join("src-tauri").join("config.json");
        if config_path.exists() {
            let content = std::fs::read_to_string(&config_path).ok()?;
            serde_json::from_str(&content).ok()
        } else {
            None
        }
    }
    
    fn resolve_python_path(&self) -> PathBuf {
        let path = &self.python.path;
        if path.starts_with("~/") || path.starts_with("~\\") {
            // 展开 ~ 为用户主目录
            if let Some(home) = dirs::home_dir() {
                let without_tilde = &path[2..];
                return home.join(without_tilde);
            }
        }
        PathBuf::from(path)
    }
    
    fn resolve_data_dir(&self, working_dir: &PathBuf) -> PathBuf {
        let path = &self.data_dir;
        
        // 展开 ~ 为用户主目录
        if path.starts_with("~/") || path.starts_with("~\\") {
            if let Some(home) = dirs::home_dir() {
                let without_tilde = &path[2..];
                return home.join(without_tilde);
            }
        }
        
        let path_buf = PathBuf::from(path);
        
        // 如果是相对路径，相对于工作目录解析
        if path_buf.is_relative() {
            return working_dir.join(path_buf);
        }
        
        path_buf
    }
}

/// Python Sidecar 管理
pub struct PythonSidecar {
    pub process: Child,
    pub port: u16,
    pub log_handle: JoinHandle<()>,
}

impl PythonSidecar {
    /// 启动 Python Sidecar
    pub async fn start<R: Runtime>(app: &tauri::AppHandle<R>) -> Result<Self, Box<dyn std::error::Error>> {
        let port = find_available_port(8721)?;
        
        // 获取 Python sidecar 路径和工作目录
        let (python_path, working_dir, is_bundled) = get_sidecar_path(app)?;
        
        // 创建启动日志（用于诊断）
        // let startup_log_path = std::env::temp_dir().join("taghive_startup.log");
        // let startup_log = format!(
        //     "[{}] Starting sidecar\n  Path: {:?}\n  Port: {}\n  Working dir: {:?}\n  Is bundled: {}\n",
        //     std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap_or_default().as_secs(),
        //     python_path, port, working_dir, is_bundled
        // );
        // let _ = std::fs::write(&startup_log_path, startup_log);
        
        println!("Starting Python sidecar at {:?} on port {}", python_path, port);
        println!("Working directory: {:?}", working_dir);
        println!("Is bundled: {}", is_bundled);
        // println!("Startup log: {:?}", startup_log_path);
        
        // DEBUG: 记录当前系统工作目录
        let current_exe = std::env::current_exe().unwrap_or_default();
        let current_dir = std::env::current_dir().unwrap_or_default();
        println!("DEBUG - Current exe: {:?}", current_exe);
        println!("DEBUG - Current dir: {:?}", current_dir);
        
        // 使用 std::process::Command 来设置 Windows 特定的标志
        // 然后再转换为 tokio::process::Command
        let mut std_cmd = std::process::Command::new(&python_path);
        
        // 关键修复：传递 TAGHIVE_DATA_DIR 环境变量（必须在其他配置之前）
        if let Ok(data_dir) = std::env::var("TAGHIVE_DATA_DIR") {
            std_cmd.env("TAGHIVE_DATA_DIR", data_dir);
        }
        
        std_cmd.current_dir(&working_dir)
            .env("TAGHIVE_PORT", port.to_string())
            .env("TAGHIVE_HOST", "127.0.0.1")
            // 传入主进程 PID，供 sidecar 监控父进程存活；父进程异常退出时
            // sidecar 自我终止，避免孤儿进程锁定安装目录文件
            .env("TAGHIVE_PARENT_PID", std::process::id().to_string())
            // 强制 Python 以 UTF-8 输出 stdout/stderr。中文 Windows 默认本地编码
            // (GBK/CP936)，而 Rust 端按 UTF-8 解码日志，含中文时会报
            // "stream did not contain valid UTF-8" 并中断日志流。
            .env("PYTHONUTF8", "1")
            .env("PYTHONIOENCODING", "utf-8")
            .stdout(Stdio::piped())
            .stderr(Stdio::piped());
        
        // Windows: 如果是打包的 sidecar，隐藏控制台窗口
        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            const CREATE_NO_WINDOW: u32 = 0x08000000;
            const CREATE_NEW_PROCESS_GROUP: u32 = 0x00000200;
            
            if is_bundled {
                // 打包版本：完全隐藏窗口
                std_cmd.creation_flags(CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP);
                println!("Windows: CREATE_NO_WINDOW flag set for bundled sidecar");
            } else {
                // 开发模式：也隐藏窗口，但保留进程组
                std_cmd.creation_flags(CREATE_NEW_PROCESS_GROUP);
            }
        }
        
        // 如果不是打包的 sidecar，需要添加 -m app.main 参数
        if !is_bundled {
            std_cmd.arg("-m").arg("app.main");
        }
        
        // 在开发模式下启用调试
        #[cfg(debug_assertions)]
        std_cmd.env("TAGHIVE_DEBUG", "1");
        
        // 转换为 tokio::process::Command
        let mut cmd = Command::from(std_cmd);
        
        let mut process = match cmd.spawn() {
            Ok(p) => {
                println!("Sidecar process spawned successfully (PID: {:?})", p.id());
                p
            }
            Err(e) => {
                eprintln!("CRITICAL: Failed to spawn sidecar: {}", e);
                eprintln!("Python path: {:?}", python_path);
                eprintln!("Working dir: {:?}", working_dir);
                return Err(e.into());
            }
        };
        
        // 获取日志文件路径 - 便携模式：存储在工作目录下的 .taghive/logs/
        let log_dir = get_portable_data_dir(&working_dir).join("logs");
        let log_file_path = log_dir.join("sidecar.log");
        
        // 确保日志目录存在
        let log_dir_result = match std::fs::create_dir_all(&log_dir) {
            Ok(_) => {
                println!("Log directory created/verified: {:?}", log_dir);
                format!("OK: {:?}", log_dir)
            }
            Err(e) => {
                let msg = format!("FAILED: {:?} - {}", log_dir, e);
                eprintln!("Warning: Failed to create log directory {:?}: {}", log_dir, e);
                msg
            }
        };
        // 追加到启动日志（已禁用）
        // let startup_log_append = format!(
        //     "Log dir result: {}\nLog file path: {:?}\n",
        //     log_dir_result, log_file_path
        // );
        // let _ = std::fs::OpenOptions::new()
        //     .create(true)
        //     .append(true)
        //     .open(&startup_log_path)
        //     .and_then(|mut f| std::io::Write::write_all(&mut f, startup_log_append.as_bytes()));
        
        
        // 检查日志文件大小，超过阈值则清空
        check_and_rotate_log_file(&log_file_path);
        
        println!("Sidecar log file: {:?}", log_file_path);
        
        // 启动日志处理任务
        let stdout = process.stdout.take().expect("Failed to capture stdout");
        let stderr = process.stderr.take().expect("Failed to capture stderr");
        let log_file_path_clone = log_file_path.clone();
        
        let log_handle = tauri::async_runtime::spawn(async move {
            let mut stdout_reader = BufReader::new(stdout);
            let mut stderr_reader = BufReader::new(stderr);

            // 按裸字节读取而非 .lines()：后者对每行强制 UTF-8 解码，中文 Windows 下
            // 若子进程输出非 UTF-8 字节会返回 Err 并中断整个日志流。改为 read_until
            // 读取原始字节，再用 from_utf8_lossy 容错解码，单行乱码也不会中断后续日志。
            let mut stdout_buf: Vec<u8> = Vec::with_capacity(1024);
            let mut stderr_buf: Vec<u8> = Vec::with_capacity(1024);

            // 打开日志文件（追加模式）
            let mut log_file = match OpenOptions::new()
                .create(true)
                .append(true)
                .open(&log_file_path_clone)
            {
                Ok(file) => {
                    println!("Log file opened successfully: {:?}", log_file_path_clone);
                    Some(file)
                }
                Err(e) => {
                    eprintln!("Warning: Failed to open log file {:?}: {}", log_file_path_clone, e);
                    None
                }
            };
            
            // 写入启动时间
            if let Some(ref mut file) = log_file {
                let _ = writeln!(file, "[{}] Sidecar started", unix_ts());
            }
            
            // 标记两条流是否已到达 EOF，都结束后退出循环
            let mut stdout_done = false;
            let mut stderr_done = false;

            while !(stdout_done && stderr_done) {
                tokio::select! {
                    n = stdout_reader.read_until(b'\n', &mut stdout_buf), if !stdout_done => {
                        match n {
                            Ok(0) => stdout_done = true, // EOF
                            Ok(_) => {
                                let line = decode_log_line(&stdout_buf);
                                stdout_buf.clear();
                                println!("[Sidecar] {}", line);
                                if let Some(ref mut file) = log_file {
                                    let _ = writeln!(file, "[{}] [INFO] {}", unix_ts(), line);
                                }
                            }
                            Err(e) => {
                                // I/O 错误（非解码错误）：记录并标记该流结束，不影响另一条流
                                eprintln!("Error reading stdout: {}", e);
                                stdout_done = true;
                            }
                        }
                    }
                    n = stderr_reader.read_until(b'\n', &mut stderr_buf), if !stderr_done => {
                        match n {
                            Ok(0) => stderr_done = true, // EOF
                            Ok(_) => {
                                let line = decode_log_line(&stderr_buf);
                                stderr_buf.clear();
                                let level = detect_log_level(&line);
                                eprintln!("[Sidecar {}] {}", level, line);
                                if let Some(ref mut file) = log_file {
                                    let _ = writeln!(file, "[{}] [{}] {}", unix_ts(), level, line);
                                }
                            }
                            Err(e) => {
                                eprintln!("Error reading stderr: {}", e);
                                stderr_done = true;
                            }
                        }
                    }
                }
            }
            
            // 写入停止时间
            if let Some(ref mut file) = log_file {
                let _ = writeln!(file, "[{}] Sidecar stopped", unix_ts());
            }
        });
        
        // 等待服务启动
        sleep(Duration::from_millis(1000)).await;
        
        Ok(Self {
            process,
            port,
            log_handle,
        })
    }
    
    /// 停止 Sidecar
    ///
    /// 关键：本方法在 `CloseRequested` 的 `block_on` 中于 **UI 线程**同步执行，
    /// 因此必须近乎瞬时返回，否则窗口会卡住不消失。此前实现有两处阻塞：
    ///   1. `taskkill ... .output()` 会 spawn taskkill.exe 并同步等它跑完
    ///      （生产环境叠加杀软扫描可达数秒）；
    ///   2. 之后最长 5s 的 `try_wait` 轮询循环。
    /// 现改为「fire-and-forget」策略：
    ///   - Windows：派发 `taskkill /T /F` 清扫进程树（含扫描期 ProcessPoolExecutor
    ///     子进程），用 `spawn` 而非 `output`，**不等待其完成**；
    ///   - 其它平台：直接对进程句柄发 kill 信号。
    /// 立即返回，窗口即时关闭。`parent_watch.py` 的父进程监控作为兜底：宿主一旦
    /// 退出，sidecar 会通过 WaitForSingleObject 感知并 `os._exit(0)` 自我终止，
    /// 不会残留孤儿进程。由于原本就是 `/F` 强杀（无优雅关闭窗口），此改动不引入
    /// 额外的数据风险（SQLite WAL 下次打开自动恢复）。
    pub fn stop(mut self) -> Result<(), Box<dyn std::error::Error>> {
        println!("Stopping Python sidecar process (non-blocking)...");

        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            // 隐藏 taskkill 可能弹出的控制台窗口
            const CREATE_NO_WINDOW: u32 = 0x08000000;

            // taskkill /PID x /T /F 会同时杀掉主进程与其全部子孙进程；
            // 用 spawn 派发后立即返回，taskkill 作为独立进程会在后台完成清理，
            // 即使宿主随后退出也不受影响。
            if let Some(pid) = self.process.id() {
                let _ = std::process::Command::new("taskkill")
                    .args(["/PID", &pid.to_string(), "/T", "/F"])
                    .creation_flags(CREATE_NO_WINDOW)
                    .spawn(); // 注意：spawn 而非 output，绝不阻塞 UI 线程
            }
        }

        #[cfg(not(windows))]
        {
            // Unix: 直接发送 kill 信号，非阻塞
            let _ = self.process.start_kill();
        }

        // 取消日志转发任务，随后立即返回
        self.log_handle.abort();

        Ok(())
    }
}

/// 检查日志文件大小，超过阈值则清空
fn check_and_rotate_log_file(log_file_path: &PathBuf) {
    if let Ok(metadata) = fs::metadata(log_file_path) {
        let file_size = metadata.len();
        if file_size > LOG_FILE_MAX_SIZE {
            println!("Log file size ({} bytes) exceeds limit ({} bytes), clearing...", file_size, LOG_FILE_MAX_SIZE);
            // 清空日志文件
            if let Err(e) = fs::write(log_file_path, "") {
                eprintln!("Failed to clear log file: {}", e);
            } else {
                println!("Log file cleared successfully");
            }
        }
    }
}

/// 获取项目根目录（开发模式使用）
fn get_project_root() -> Option<PathBuf> {
    // 尝试从当前工作目录找到项目根目录
    let current_dir = std::env::current_dir().ok()?;
    
    // 如果在 src-tauri 目录中，向上两级找到项目根目录
    if current_dir.file_name().map(|n| n == "src-tauri").unwrap_or(false) {
        return current_dir.parent().map(|p| p.to_path_buf());
    }
    
    // 如果在项目根目录，直接返回
    if current_dir.join("src-python").exists() {
        return Some(current_dir);
    }
    
    // 尝试向上查找包含 src-python 的目录
    let mut dir = current_dir.clone();
    for _ in 0..5 {
        if dir.join("src-python").exists() {
            return Some(dir);
        }
        if let Some(parent) = dir.parent() {
            dir = parent.to_path_buf();
        } else {
            break;
        }
    }
    
    Some(current_dir)
}

/// 获取数据目录
/// 默认便携模式：使用应用目录下的 .taghive
/// 标准模式（需创建 use-system-data-dir 标志）：使用工作目录
fn get_portable_data_dir(working_dir: &PathBuf) -> PathBuf {
    // 首先检查环境变量 TAGHIVE_DATA_DIR（由主程序设置）
    if let Ok(data_dir) = std::env::var("TAGHIVE_DATA_DIR") {
        println!("Using TAGHIVE_DATA_DIR from env: {}", data_dir);
        let path = PathBuf::from(data_dir);
        // 如果路径以 /data 或 \data 结尾（lib.rs 中设置的），去掉这层
        // 日志应该放在 .taghive/logs/ 而不是 .taghive/data/logs/
        if path.file_name().map(|n| n == "data").unwrap_or(false) {
            let parent = path.parent().unwrap_or(&path).to_path_buf();
            println!("Adjusted data dir (removed 'data' suffix): {:?}", parent);
            return parent;
        }
        return path;
    }
    
    // 尝试获取应用目录（对于打包的应用）
    let app_dir = std::env::current_exe()
        .ok()
        .and_then(|exe| exe.parent().map(|p| p.to_path_buf()));
    
    if let Some(ref app_dir) = app_dir {
        // 检查是否强制使用系统数据目录
        let system_data_flag = app_dir.join("use-system-data-dir");
        if system_data_flag.exists() {
            // 标准模式：使用工作目录
            println!("System data dir mode: using working directory");
            return working_dir.join(".taghive");
        }
        
        // 检查应用目录是否可写（Windows Program Files 需要管理员权限）
        let test_file = app_dir.join(".write_test");
        match std::fs::File::create(&test_file) {
            Ok(_) => {
                let _ = std::fs::remove_file(&test_file);
                println!("App directory is writable: {:?}", app_dir);
            }
            Err(e) => {
                eprintln!("WARNING: App directory is not writable: {:?} - {}", app_dir, e);
                eprintln!("Consider: 1) Run as administrator, 2) Create 'use-system-data-dir' file, or 3) Install to user directory");
            }
        }
        
        // 默认便携模式：使用应用目录下的 .taghive
        println!("Portable mode (default): using app directory");
        return app_dir.join(".taghive");
    }
    
    // 回退到工作目录
    working_dir.join(".taghive")
}

/// 从环境变量获取数据目录（由主程序设置）
fn get_data_dir_from_env() -> Option<PathBuf> {
    std::env::var("TAGHIVE_DATA_DIR")
        .ok()
        .map(PathBuf::from)
}

/// 查找可用端口
fn find_available_port(start: u16) -> Result<u16, Box<dyn std::error::Error>> {
    for port in start..=65535 {
        if is_port_available(port) {
            return Ok(port);
        }
    }
    Err("No available port found".into())
}

/// 检查端口是否可用
fn is_port_available(port: u16) -> bool {
    use std::net::TcpListener;
    TcpListener::bind(("127.0.0.1", port)).is_ok()
}

/// 获取当前 Unix 时间戳（秒）
fn unix_ts() -> u64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs()
}

/// 将一行原始字节容错解码为字符串，并去除行尾的 \r\n。
/// 使用 from_utf8_lossy：非法字节替换为 U+FFFD，绝不因编码问题丢弃整行或中断流。
fn decode_log_line(raw: &[u8]) -> String {
    let s = String::from_utf8_lossy(raw);
    s.trim_end_matches(['\n', '\r']).to_string()
}

/// 根据日志内容检测日志级别
/// 优先检测 Python 日志格式中的级别字段，避免误匹配文件名等包含关键字的文本
fn detect_log_level(line: &str) -> &'static str {
    // Python 日志格式: "2025-03-07 21:00:34,123 - app.main - INFO - message"
    // 尝试匹配 " - LEVEL - " 模式
    if let Some(start) = line.find(" - ") {
        let after_first = &line[start + 3..];
        if let Some(end) = after_first.find(" - ") {
            let level_part = &after_first[..end];
            // 检查是否是已知的日志级别
            match level_part.trim() {
                "CRITICAL" | "FATAL" => return "CRITICAL",
                "ERROR" => return "ERROR",
                "WARNING" | "WARN" => return "WARNING",
                "INFO" => return "INFO",
                "DEBUG" => return "DEBUG",
                _ => {}
            }
        }
    }
    
    // 备用：检查行首的级别标记（如 "[ERROR]" 或 "ERROR:"）
    let trimmed = line.trim_start();
    if trimmed.starts_with("[CRITICAL]") || trimmed.starts_with("[FATAL]") {
        return "CRITICAL";
    } else if trimmed.starts_with("[ERROR]") {
        return "ERROR";
    } else if trimmed.starts_with("[WARNING]") || trimmed.starts_with("[WARN]") {
        return "WARNING";
    } else if trimmed.starts_with("[DEBUG]") {
        return "DEBUG";
    } else if trimmed.starts_with("[INFO]") {
        return "INFO";
    }
    
    // 检查 "LEVEL:" 格式
    if trimmed.starts_with("CRITICAL:") || trimmed.starts_with("FATAL:") {
        return "CRITICAL";
    } else if trimmed.starts_with("ERROR:") {
        return "ERROR";
    } else if trimmed.starts_with("WARNING:") || trimmed.starts_with("WARN:") {
        return "WARNING";
    } else if trimmed.starts_with("DEBUG:") {
        return "DEBUG";
    } else if trimmed.starts_with("INFO:") {
        return "INFO";
    }
    
    // 默认级别
    "INFO"
}

/// 获取 sidecar 路径和工作目录，返回 (路径, 工作目录, 是否为打包的sidecar)
fn get_sidecar_path<R: Runtime>(app: &tauri::AppHandle<R>) -> Result<(PathBuf, PathBuf, bool), Box<dyn std::error::Error>> {
    // 在开发模式下，使用项目目录中的 Python
    #[cfg(debug_assertions)]
    {
        // 尝试从当前工作目录找到项目根目录
        let current_dir = std::env::current_dir()?;
        
        // 如果在 src-tauri 目录中，向上两级找到项目根目录
        let project_dir = if current_dir.file_name().map(|n| n == "src-tauri").unwrap_or(false) {
            current_dir.parent().unwrap().to_path_buf()
        } else {
            current_dir
        };
        
        let src_python_dir = project_dir.join("src-python");
        
        // 首先检查环境变量 TAGHIVE_PYTHON_PATH（最高优先级，用于临时覆盖）
        if let Ok(python_path_str) = std::env::var("TAGHIVE_PYTHON_PATH") {
            let python_path = PathBuf::from(&python_path_str);
            if python_path.exists() {
                println!("Using Python from TAGHIVE_PYTHON_PATH: {:?}", python_path);
                return Ok((python_path, src_python_dir, false));
            } else {
                eprintln!("Warning: TAGHIVE_PYTHON_PATH set but path does not exist: {:?}", python_path);
            }
        }
        
        // 然后尝试从配置文件读取（持久化配置）
        let _data_dir = if let Some(config) = Config::load(&project_dir) {
            let python_path = config.resolve_python_path();
            let data_dir = config.resolve_data_dir(&src_python_dir);
            
            // 设置数据目录环境变量
            std::env::set_var("TAGHIVE_DATA_DIR", &data_dir);
            println!("Data directory: {:?}", data_dir);
            
            if python_path.exists() {
                println!("Using Python from config: {:?} (type: {})", python_path, config.python.env_type);
                return Ok((python_path, src_python_dir, false));
            } else {
                eprintln!("Warning: Configured Python path does not exist: {:?}", python_path);
            }
            
            Some(data_dir)
        } else {
            None
        };

        // 然后尝试使用 src-python/.venv 虚拟环境（uv sync 默认创建）
        let venv_python = src_python_dir.join(if cfg!(windows) {
            ".venv\\Scripts\\python.exe"
        } else {
            ".venv/bin/python"
        });

        if venv_python.exists() {
            println!("Using src-python/.venv: {:?}", venv_python);
            return Ok((venv_python, src_python_dir, false));
        }

        // 最后使用系统 Python
        println!("Using system Python");
        Ok((PathBuf::from(if cfg!(windows) { "python" } else { "python3" }), src_python_dir, false))
    }

    // 在生产模式下，首先尝试使用打包的 Python 可执行文件
    // 如果不存在，则回退到系统 Python
    #[cfg(not(debug_assertions))]
    {
        let sidecar_name = if cfg!(windows) {
            "taghive-sidecar.exe"
        } else {
            "taghive-sidecar"
        };

        // 获取资源目录
        let resource_dir = app.path().resource_dir()?;
        println!("Resource directory: {:?}", resource_dir);

        // onedir 模式：sidecar 在 resources/taghive-sidecar/ 子目录中
        let sidecar_dir = resource_dir.join("resources").join("taghive-sidecar");
        let sidecar_path = sidecar_dir.join(sidecar_name);
        println!("Looking for bundled sidecar at: {:?}", sidecar_path);

        // 如果打包的 sidecar 存在，使用它（working_dir 设为 sidecar 目录，让动态库能被找到）
        if sidecar_path.exists() {
            println!("Using bundled sidecar (onedir): {:?}", sidecar_path);
            return Ok((sidecar_path, sidecar_dir, true));
        }
        
        // 否则，尝试查找系统 Python（与开发模式相同的逻辑）
        println!("Bundled sidecar not found at {:?}, trying to find system Python...", sidecar_path);
        
        // 获取应用安装目录
        let install_dir = std::env::current_exe()
            .ok()
            .and_then(|exe| exe.parent().map(|p| p.to_path_buf()));
        
        // 检查是否强制使用系统数据目录
        let use_system_data = install_dir.as_ref()
            .map(|dir| dir.join("use-system-data-dir").exists())
            .unwrap_or(false);
        
        // 确定工作目录
        let app_dir = if use_system_data {
            // 标准模式：使用系统数据目录
            app.path().app_local_data_dir()
                .or_else(|_| app.path().app_data_dir())
                .unwrap_or_else(|_| std::env::current_dir().unwrap_or_else(|_| PathBuf::from(".")))
        } else {
            // 默认便携模式：使用应用安装目录
            install_dir.unwrap_or_else(|| std::env::current_dir().unwrap_or_else(|_| PathBuf::from(".")))
        };
        
        // 设置数据目录环境变量供 Python sidecar 使用
        if !use_system_data {
            let data_dir = app_dir.join(".taghive").join("data");
            std::env::set_var("TAGHIVE_DATA_DIR", &data_dir);
            println!("Portable mode (default): data directory set to {:?}", data_dir);
        } else {
            println!("System data dir mode: using system directories");
        }
        
        // 尝试从环境变量获取 Python 路径
        if let Ok(python_path_str) = std::env::var("TAGHIVE_PYTHON_PATH") {
            let python_path = PathBuf::from(&python_path_str);
            if python_path.exists() {
                println!("Using Python from TAGHIVE_PYTHON_PATH: {:?}", python_path);
                return Ok((python_path, app_dir, false));
            }
        }

        // 尝试使用系统 Python
        let system_python = if cfg!(windows) { "python" } else { "python3" };
        println!("Using system Python: {}", system_python);
        
        // 检查系统 Python 是否可用
        if let Ok(output) = std::process::Command::new(system_python).arg("--version").output() {
            if output.status.success() {
                println!("System Python is available");
            } else {
                eprintln!("Warning: System Python may not be available");
            }
        }
        
        Ok((PathBuf::from(system_python), app_dir, false))
    }
}
