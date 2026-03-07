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
        
        println!("Starting Python sidecar at {:?} on port {}", python_path, port);
        println!("Working directory: {:?}", working_dir);
        println!("Is bundled: {}", is_bundled);
        
        // 使用 std::process::Command 来设置 Windows 特定的标志
        // 然后再转换为 tokio::process::Command
        let mut std_cmd = std::process::Command::new(&python_path);
        std_cmd.current_dir(&working_dir)
            .env("TAGHIVE_PORT", port.to_string())
            .env("TAGHIVE_HOST", "127.0.0.1")
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
        
        let mut process = cmd.spawn()?;
        
        // 获取日志文件路径 - 便携模式：存储在工作目录下的 .taghive/logs/
        let log_dir = get_portable_data_dir(&working_dir).join("logs");
        let log_file_path = log_dir.join("sidecar.log");
        
        // 确保日志目录存在
        if let Some(parent) = log_file_path.parent() {
            let _ = std::fs::create_dir_all(parent);
        }
        
        // 检查日志文件大小，超过阈值则清空
        check_and_rotate_log_file(&log_file_path);
        
        println!("Sidecar log file: {:?}", log_file_path);
        
        // 启动日志处理任务
        let stdout = process.stdout.take().expect("Failed to capture stdout");
        let stderr = process.stderr.take().expect("Failed to capture stderr");
        let log_file_path_clone = log_file_path.clone();
        
        let log_handle = tauri::async_runtime::spawn(async move {
            let stdout_reader = BufReader::new(stdout);
            let stderr_reader = BufReader::new(stderr);
            
            let mut stdout_lines = stdout_reader.lines();
            let mut stderr_lines = stderr_reader.lines();
            
            // 打开日志文件（追加模式）
            let mut log_file = OpenOptions::new()
                .create(true)
                .append(true)
                .open(&log_file_path_clone)
                .ok();
            
            // 写入启动时间
            if let Some(ref mut file) = log_file {
                let timestamp = std::time::SystemTime::now()
                    .duration_since(std::time::UNIX_EPOCH)
                    .unwrap_or_default()
                    .as_secs();
                let _ = writeln!(file, "[{}] Sidecar started", timestamp);
            }
            
            loop {
                tokio::select! {
                    line = stdout_lines.next_line() => {
                        match line {
                            Ok(Some(line)) => {
                                // 同时输出到控制台和日志文件
                                println!("[Sidecar] {}", line);
                                if let Some(ref mut file) = log_file {
                                    let timestamp = std::time::SystemTime::now()
                                        .duration_since(std::time::UNIX_EPOCH)
                                        .unwrap_or_default()
                                        .as_secs();
                                    let _ = writeln!(file, "[{}] [INFO] {}", timestamp, line);
                                }
                            }
                            Ok(None) => break,
                            Err(e) => {
                                eprintln!("Error reading stdout: {}", e);
                                break;
                            }
                        }
                    }
                    line = stderr_lines.next_line() => {
                        match line {
                            Ok(Some(line)) => {
                                // 根据日志内容检测级别
                                let level = detect_log_level(&line);
                                // 同时输出到控制台和日志文件
                                eprintln!("[Sidecar {}] {}", level, line);
                                if let Some(ref mut file) = log_file {
                                    let timestamp = std::time::SystemTime::now()
                                        .duration_since(std::time::UNIX_EPOCH)
                                        .unwrap_or_default()
                                        .as_secs();
                                    let _ = writeln!(file, "[{}] [{}] {}", timestamp, level, line);
                                }
                            }
                            Ok(None) => break,
                            Err(e) => {
                                eprintln!("Error reading stderr: {}", e);
                                break;
                            }
                        }
                    }
                }
            }
            
            // 写入停止时间
            if let Some(ref mut file) = log_file {
                let timestamp = std::time::SystemTime::now()
                    .duration_since(std::time::UNIX_EPOCH)
                    .unwrap_or_default()
                    .as_secs();
                let _ = writeln!(file, "[{}] Sidecar stopped", timestamp);
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
    pub fn stop(mut self) -> Result<(), Box<dyn std::error::Error>> {
        println!("Stopping Python sidecar process...");
        
        // 首先尝试优雅地终止进程
        #[cfg(windows)]
        {
            // Windows: 使用 taskkill 发送 SIGTERM
            let pid = self.process.id();
            if let Some(pid) = pid {
                let _ = std::process::Command::new("taskkill")
                    .args(["/PID", &pid.to_string(), "/T", "/F"])
                    .output();
            }
        }
        
        #[cfg(not(windows))]
        {
            // Unix: 发送 SIGTERM
            let _ = self.process.start_kill();
        }
        
        // 等待进程退出（最多 5 秒）
        let start = std::time::Instant::now();
        loop {
            match self.process.try_wait() {
                Ok(Some(_)) => {
                    println!("Python sidecar process exited");
                    break;
                }
                Ok(None) => {
                    if start.elapsed().as_secs() > 5 {
                        println!("Timeout waiting for sidecar, forcing kill...");
                        let _ = self.process.kill();
                        break;
                    }
                    std::thread::sleep(std::time::Duration::from_millis(100));
                }
                Err(e) => {
                    eprintln!("Error waiting for sidecar: {}", e);
                    break;
                }
            }
        }
        
        // 取消日志任务
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

/// 获取便携模式数据目录
/// 优先使用工作目录下的 .taghive，实现便携模式
fn get_portable_data_dir(working_dir: &PathBuf) -> PathBuf {
    working_dir.join(".taghive")
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
        
        // 然后尝试使用 conda 环境 taghive_env (在用户目录下)
        let home_dir = dirs::home_dir().ok_or("Cannot find home directory")?;
        let conda_python = home_dir.join(".conda").join("envs").join("taghive_env").join(if cfg!(windows) {
            "python.exe"
        } else {
            "bin/python"
        });
        
        if conda_python.exists() {
            println!("Using conda environment: {:?}", conda_python);
            return Ok((conda_python, src_python_dir, false));
        }
        
        // 然后尝试使用 venv 虚拟环境
        let venv_python = src_python_dir.join(if cfg!(windows) {
            "venv\\Scripts\\python.exe"
        } else {
            "venv/bin/python"
        });
        
        if venv_python.exists() {
            println!("Using venv: {:?}", venv_python);
            return Ok((venv_python, src_python_dir, false));
        }
        
        // 最后使用系统 Python
        println!("Using system Python");
        Ok((PathBuf::from(if cfg!(windows) { "python" } else { "python3" }), src_python_dir, false))
    }
    
    // 在生产模式下，首先尝试使用打包的 Python 可执行文件
    // 如果不存在，则尝试查找系统 Python 或 conda 环境
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
        
        // 手动拼接 sidecar 路径（资源文件在 resources 子目录中）
        let sidecar_path = resource_dir.join("resources").join(&sidecar_name);
        println!("Looking for bundled sidecar at: {:?}", sidecar_path);
        
        // 如果打包的 sidecar 存在，使用它
        if sidecar_path.exists() {
            println!("Using bundled sidecar: {:?}", sidecar_path);
            return Ok((sidecar_path, resource_dir, true));
        }
        
        // 否则，尝试查找系统 Python（与开发模式相同的逻辑）
        println!("Bundled sidecar not found at {:?}, trying to find system Python...", sidecar_path);
        
        // 获取应用安装目录作为工作目录
        let app_dir = app.path().app_local_data_dir()
            .or_else(|_| app.path().app_data_dir())
            .unwrap_or_else(|_| std::env::current_dir().unwrap_or_else(|_| PathBuf::from(".")));
        
        // 尝试从环境变量获取 Python 路径
        if let Ok(python_path_str) = std::env::var("TAGHIVE_PYTHON_PATH") {
            let python_path = PathBuf::from(&python_path_str);
            if python_path.exists() {
                println!("Using Python from TAGHIVE_PYTHON_PATH: {:?}", python_path);
                return Ok((python_path, app_dir, false));
            }
        }
        
        // 尝试使用 conda 环境 taghive_env
        if let Some(home_dir) = dirs::home_dir() {
            let conda_python = home_dir.join(".conda").join("envs").join("taghive_env").join(if cfg!(windows) {
                "python.exe"
            } else {
                "bin/python"
            });
            
            if conda_python.exists() {
                println!("Using conda environment: {:?}", conda_python);
                return Ok((conda_python, app_dir, false));
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
