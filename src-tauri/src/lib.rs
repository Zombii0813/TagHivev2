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
    
    let sidecar = PythonSidecar::start(&app).map_err(|e| e.to_string())?;
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
        ])
        .setup(|app| {
            let app_handle = app.handle().clone();
            tauri::async_runtime::spawn(async move {
                let state: State<'_, AppState> = app_handle.state();
                let mut sidecar_guard = state.sidecar.lock().await;
                
                if sidecar_guard.is_none() {
                    match PythonSidecar::start(&app_handle) {
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
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
