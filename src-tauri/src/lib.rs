use std::path::PathBuf;
use std::sync::Arc;
use tauri::async_runtime::Mutex;
use tauri::{Manager, State};

mod sidecar;
use sidecar::PythonSidecar;

pub struct AppState {
    pub sidecar: Arc<Mutex<Option<PythonSidecar>>>,
}

impl AppState {
    pub fn new() -> Self {
        Self {
            sidecar: Arc::new(Mutex::new(None)),
        }
    }
}

#[tauri::command]
async fn cmd_start_sidecar(
    state: State<'_, AppState>,
    app: tauri::AppHandle,
) -> Result<u16, String> {
    let mut sidecar_guard = state.sidecar.lock().await;
    
    if let Some(ref sidecar) = *sidecar_guard {
        return Ok(sidecar.port);
    }
    
    let sidecar = PythonSidecar::start(&app).await.map_err(|e| e.to_string())?;
    let port = sidecar.port;
    *sidecar_guard = Some(sidecar);
    
    Ok(port)
}

#[tauri::command]
async fn cmd_stop_sidecar(state: State<'_, AppState>) -> Result<(), String> {
    let mut sidecar_guard = state.sidecar.lock().await;
    
    if let Some(sidecar) = sidecar_guard.take() {
        sidecar.stop().map_err(|e| e.to_string())?;
    }
    
    Ok(())
}

#[tauri::command]
async fn select_folder(app: tauri::AppHandle) -> Result<Option<String>, String> {
    use tauri_plugin_dialog::DialogExt;
    
    log::info!("select_folder called");
    
    let folder = app.dialog()
        .file()
        .blocking_pick_folder();
    
    let result = folder.map(|p| p.into_path().map(|path| path.to_string_lossy().to_string()).ok())
        .flatten();
    log::info!("folder selected: {:?}", result);
    
    Ok(result)
}

#[tauri::command]
async fn open_file(path: String) -> Result<(), String> {
    use std::process::Command;
    
    log::info!("open_file called: {}", path);
    
    #[cfg(target_os = "windows")]
    {
        Command::new("cmd")
            .args(["/c", "start", "", &path])
            .spawn()
            .map_err(|e| format!("Failed to open file: {}", e))?;
    }
    
    #[cfg(target_os = "macos")]
    {
        Command::new("open")
            .arg(&path)
            .spawn()
            .map_err(|e| format!("Failed to open file: {}", e))?;
    }
    
    #[cfg(target_os = "linux")]
    {
        Command::new("xdg-open")
            .arg(&path)
            .spawn()
            .map_err(|e| format!("Failed to open file: {}", e))?;
    }
    
    Ok(())
}

#[tauri::command]
async fn open_folder(path: String, file_path: Option<String>) -> Result<(), String> {
    use std::process::Command;
    
    log::info!("open_folder called: {}, file: {:?}", path, file_path);
    
    #[cfg(target_os = "windows")]
    {
        // 如果提供了文件路径，使用 /select 参数打开并选中文件
        if let Some(file) = file_path {
            // 确保路径使用反斜杠（Windows标准格式）
            let file_normalized = file.replace('/', "\\");
            log::info!("Opening folder with file selection: {}", file_normalized);
            Command::new("explorer")
                .args(["/select,", &file_normalized])
                .spawn()
                .map_err(|e| format!("Failed to open folder: {}", e))?;
        } else {
            let path_normalized = path.replace('/', "\\");
            Command::new("explorer")
                .arg(&path_normalized)
                .spawn()
                .map_err(|e| format!("Failed to open folder: {}", e))?;
        }
    }
    
    #[cfg(target_os = "macos")]
    {
        // macOS: 使用 -R 参数在 Finder 中显示文件
        if let Some(file) = file_path {
            Command::new("open")
                .args(["-R", &file])
                .spawn()
                .map_err(|e| format!("Failed to open folder: {}", e))?;
        } else {
            Command::new("open")
                .arg(&path)
                .spawn()
                .map_err(|e| format!("Failed to open folder: {}", e))?;
        }
    }
    
    #[cfg(target_os = "linux")]
    {
        // Linux: 尝试使用 dbus-send 或其他工具显示文件
        if let Some(file) = file_path {
            // 尝试使用 xdg-open 打开文件夹，然后使用 dbus 选中文件
            let _ = Command::new("dbus-send")
                .args([
                    "--session",
                    "--dest=org.freedesktop.FileManager1",
                    "--type=method_call",
                    "/org/freedesktop/FileManager1",
                    "org.freedesktop.FileManager1.ShowItems",
                    format!("array:string:{}", file).as_str(),
                    "string:"
                ])
                .spawn();
        }
        Command::new("xdg-open")
            .arg(&path)
            .spawn()
            .map_err(|e| format!("Failed to open folder: {}", e))?;
    }
    
    Ok(())
}

/// 获取开发模式下的项目根目录
/// 在开发模式下，日志存储在 src-python/.taghive/logs/
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

/// 获取便携模式日志文件路径
/// 开发模式: {project_root}/src-python/.taghive/logs/sidecar.log
/// 生产模式: {app_dir}/.taghive/logs/sidecar.log
fn get_log_file_path() -> PathBuf {
    // 首先尝试获取项目根目录（开发模式）
    if let Some(project_root) = get_project_root() {
        let src_python_dir = project_root.join("src-python");
        if src_python_dir.exists() {
            return src_python_dir.join(".taghive").join("logs").join("sidecar.log");
        }
    }
    
    // 回退到当前工作目录
    let working_dir = std::env::current_dir().unwrap_or_else(|_| PathBuf::from("."));
    working_dir.join(".taghive").join("logs").join("sidecar.log")
}

/// 读取 sidecar 日志文件
#[tauri::command]
async fn get_sidecar_logs(app: tauri::AppHandle, lines: Option<usize>) -> Result<String, String> {
    use std::fs::File;
    use std::io::{BufRead, BufReader};
    
    // 获取日志文件路径
    let log_file_path = get_log_file_path();
    
    if !log_file_path.exists() {
        return Ok(format!("日志文件不存在: {:?}", log_file_path));
    }
    
    let file = File::open(&log_file_path)
        .map_err(|e| format!("Failed to open log file: {}", e))?;
    let reader = BufReader::new(file);
    
    let all_lines: Vec<String> = reader.lines()
        .filter_map(|line| line.ok())
        .collect();
    
    // 如果指定了行数，返回最后 N 行
    let result = if let Some(n) = lines {
        let start = all_lines.len().saturating_sub(n);
        all_lines[start..].join("\n")
    } else {
        all_lines.join("\n")
    };
    
    Ok(result)
}

/// 打开日志文件所在文件夹
#[tauri::command]
async fn open_logs_folder(app: tauri::AppHandle) -> Result<(), String> {
    use std::process::Command;
    
    // 获取日志文件路径
    let log_file_path = get_log_file_path();
    let log_dir = log_file_path.parent()
        .ok_or("Failed to get log directory")?;
    
    // 确保日志目录存在
    if !log_dir.exists() {
        std::fs::create_dir_all(log_dir)
            .map_err(|e| format!("Failed to create log directory: {}", e))?;
    }
    
    // 确保日志文件存在
    if !log_file_path.exists() {
        // 创建空日志文件
        std::fs::write(&log_file_path, "")
            .map_err(|e| format!("Failed to create log file: {}", e))?;
    }
    
    let path_str = log_file_path.to_string_lossy().to_string();
    
    #[cfg(target_os = "windows")]
    {
        let file_normalized = path_str.replace('/', "\\");
        Command::new("explorer")
            .args(["/select,", &file_normalized])
            .spawn()
            .map_err(|e| format!("Failed to open folder: {}", e))?;
    }
    
    #[cfg(target_os = "macos")]
    {
        Command::new("open")
            .args(["-R", &path_str])
            .spawn()
            .map_err(|e| format!("Failed to open folder: {}", e))?;
    }
    
    #[cfg(target_os = "linux")]
    {
        Command::new("xdg-open")
            .arg(log_dir)
            .spawn()
            .map_err(|e| format!("Failed to open folder: {}", e))?;
    }
    
    Ok(())
}

pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_fs::init())
        .manage(AppState::new())
        .invoke_handler(tauri::generate_handler![
            cmd_start_sidecar,
            cmd_stop_sidecar,
            select_folder,
            open_file,
            open_folder,
            get_sidecar_logs,
            open_logs_folder,
        ])
        .setup(|app| {
            let app_handle = app.handle().clone();
            tauri::async_runtime::spawn(async move {
                let state: State<'_, AppState> = app_handle.state();
                let mut sidecar_guard = state.sidecar.lock().await;
                
                if sidecar_guard.is_none() {
                    match PythonSidecar::start(&app_handle).await {
                        Ok(sidecar) => {
                            *sidecar_guard = Some(sidecar);
                        }
                        Err(e) => {
                            eprintln!("Failed to start sidecar: {}", e);
                        }
                    }
                }
            });
            
            Ok(())
        })
        .on_window_event(|app, event| {
            if let tauri::WindowEvent::CloseRequested { .. } = event {
                // 窗口关闭时停止 sidecar
                let app_handle = app.clone();
                tauri::async_runtime::block_on(async move {
                    let state: State<'_, AppState> = app_handle.state();
                    let mut sidecar_guard = state.sidecar.lock().await;
                    if let Some(sidecar) = sidecar_guard.take() {
                        println!("Stopping Python sidecar...");
                        if let Err(e) = sidecar.stop() {
                            eprintln!("Failed to stop sidecar: {}", e);
                        } else {
                            println!("Python sidecar stopped successfully");
                        }
                    }
                });
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
