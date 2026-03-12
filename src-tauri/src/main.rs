#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::path::PathBuf;

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

/// 获取便携模式的基础目录
/// 开发模式: 项目根目录
/// 生产模式: 应用安装目录
fn get_portable_base_dir() -> Option<PathBuf> {
    #[cfg(debug_assertions)]
    {
        // 开发模式：使用项目根目录
        get_project_root()
    }
    #[cfg(not(debug_assertions))]
    {
        // 生产模式：使用应用安装目录
        std::env::current_exe()
            .ok()
            .and_then(|exe| exe.parent().map(|p| p.to_path_buf()))
    }
}

fn main() {
    // 在 Windows 上，WebView2 数据目录必须在创建窗口之前设置
    // 通过 WEBVIEW2_USER_DATA_FOLDER 环境变量
    #[cfg(windows)]
    {
        if let Some(base_dir) = get_portable_base_dir() {
            // 检查是否强制使用系统数据目录
            let system_data_flag = base_dir.join("use-system-data-dir");
            if !system_data_flag.exists() {
                // 默认便携模式：设置 WebView2 数据目录
                let webview_data_dir = base_dir.join(".taghive").join("webview");
                std::env::set_var("WEBVIEW2_USER_DATA_FOLDER", &webview_data_dir);
                println!("[main] Set WEBVIEW2_USER_DATA_FOLDER to: {:?}", webview_data_dir);
            } else {
                println!("[main] System data dir mode: using default location");
            }
        }
    }
    
    taghive::run();
}
