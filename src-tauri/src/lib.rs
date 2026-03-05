use std::process::Stdio;
use std::sync::Arc;
use tauri::async_runtime::Mutex;
use tauri::{Manager, Runtime, State};
use tokio::io::{AsyncBufReadExt, BufReader};
use tokio::process::{Child, Command};

pub mod sidecar;

use sidecar::PythonSidecar;

/// 应用状态
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

/// 启动 Python Sidecar
#[tauri::command]
pub async fn start_sidecar(
    state: State<'_, AppState>,
    app: tauri::AppHandle,
) -> Result<u16, String> {
    let mut sidecar_guard = state.sidecar.lock().await;
    
    if let Some(ref sidecar) = *sidecar_guard {
        // 如果已经启动，返回当前端口
        return Ok(sidecar.port);
    }
    
    // 创建新的 sidecar
    let sidecar = PythonSidecar::start(&app).map_err(|e| e.to_string())?;
    let port = sidecar.port;
    
    *sidecar_guard = Some(sidecar);
    
    Ok(port)
}

/// 停止 Python Sidecar
#[tauri::command]
pub async fn stop_sidecar(state: State<'_, AppState>) -> Result<(), String> {
    let mut sidecar_guard = state.sidecar.lock().await;
    
    if let Some(sidecar) = sidecar_guard.take() {
        sidecar.stop().map_err(|e| e.to_string())?;
    }
    
    Ok(())
}

/// 选择文件夹
#[tauri::command]
pub async fn select_folder(app: tauri::AppHandle) -> Result<Option<String>, String> {
    use tauri_plugin_dialog::DialogExt;
    
    log::info!("select_folder called");
    
    let folder = app
        .dialog()
        .file()
        .pick_folder()
        .await;
    
    log::info!("folder selected: {:?}", folder);
    
    Ok(folder.map(|p| p.to_string()))
}

/// 运行应用
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_fs::init())
        .manage(AppState::new())
        .invoke_handler(tauri::generate_handler![
            start_sidecar,
            stop_sidecar,
            select_folder,
        ])
        .setup(|app| {
            // 应用启动时自动启动 sidecar
            let app_handle = app.handle().clone();
            tauri::async_runtime::spawn(async move {
                let state: State<'_, AppState> = app_handle.state();
                if let Err(e) = start_sidecar(state, app_handle).await {
                    eprintln!("Failed to start sidecar: {}", e);
                }
            });
            
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
