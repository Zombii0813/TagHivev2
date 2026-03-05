use std::path::PathBuf;
use std::process::Stdio;
use std::time::Duration;
use tauri::async_runtime::JoinHandle;
use tauri::{Manager, Runtime};
use tokio::io::{AsyncBufReadExt, BufReader};
use tokio::process::{Child, Command};
use tokio::time::sleep;

/// Python Sidecar 管理
pub struct PythonSidecar {
    pub process: Child,
    pub port: u16,
    pub log_handle: JoinHandle<()>,
}

impl PythonSidecar {
    /// 启动 Python Sidecar
    pub fn start<R: Runtime>(app: &tauri::AppHandle<R>) -> Result<Self, Box<dyn std::error::Error>> {
        let port = find_available_port(8721)?;
        
        // 获取 Python sidecar 路径
        let sidecar_path = get_sidecar_path(app)?;
        
        println!("Starting Python sidecar at {:?} on port {}", sidecar_path, port);
        
        // 设置环境变量
        let mut cmd = Command::new(sidecar_path);
        cmd.env("TAGHIVE_PORT", port.to_string())
            .env("TAGHIVE_HOST", "127.0.0.1")
            .stdout(Stdio::piped())
            .stderr(Stdio::piped());
        
        // 在开发模式下启用调试
        #[cfg(debug_assertions)]
        cmd.env("TAGHIVE_DEBUG", "1");
        
        let mut process = cmd.spawn()?;
        
        // 启动日志处理任务
        let stdout = process.stdout.take().expect("Failed to capture stdout");
        let stderr = process.stderr.take().expect("Failed to capture stderr");
        
        let log_handle = tauri::async_runtime::spawn(async move {
            let stdout_reader = BufReader::new(stdout);
            let stderr_reader = BufReader::new(stderr);
            
            let mut stdout_lines = stdout_reader.lines();
            let mut stderr_lines = stderr_reader.lines();
            
            loop {
                tokio::select! {
                    line = stdout_lines.next_line() => {
                        match line {
                            Ok(Some(line)) => println!("[Sidecar] {}", line),
                            Ok(None) => break,
                            Err(e) => {
                                eprintln!("Error reading stdout: {}", e);
                                break;
                            }
                        }
                    }
                    line = stderr_lines.next_line() => {
                        match line {
                            Ok(Some(line)) => eprintln!("[Sidecar Error] {}", line),
                            Ok(None) => break,
                            Err(e) => {
                                eprintln!("Error reading stderr: {}", e);
                                break;
                            }
                        }
                    }
                }
            }
        });
        
        // 等待服务启动
        tauri::async_runtime::block_on(async {
            sleep(Duration::from_millis(1000)).await;
        });
        
        Ok(Self {
            process,
            port,
            log_handle,
        })
    }
    
    /// 停止 Sidecar
    pub fn stop(mut self) -> Result<(), Box<dyn std::error::Error>> {
        // 尝试优雅地终止进程
        let _ = self.process.start_kill();
        
        // 取消日志任务
        self.log_handle.abort();
        
        Ok(())
    }
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

/// 获取 sidecar 路径
fn get_sidecar_path<R: Runtime>(app: &tauri::AppHandle<R>) -> Result<PathBuf, Box<dyn std::error::Error>> {
    // 在开发模式下，使用项目目录中的 Python
    #[cfg(debug_assertions)]
    {
        let app_dir = app.path().app_local_data_dir()?;
        let project_dir = app_dir.parent().unwrap().parent().unwrap();
        let python_path = project_dir.join("src-python").join(if cfg!(windows) {
            "venv\\Scripts\\python.exe"
        } else {
            "venv/bin/python"
        });
        
        if python_path.exists() {
            // 使用虚拟环境中的 Python
            Ok(python_path)
        } else {
            // 使用系统 Python
            Ok(PathBuf::from(if cfg!(windows) { "python" } else { "python3" }))
        }
    }
    
    // 在生产模式下，使用打包的 Python 可执行文件
    #[cfg(not(debug_assertions))]
    {
        let sidecar_name = if cfg!(windows) {
            "taghive-sidecar.exe"
        } else {
            "taghive-sidecar"
        };
        
        let sidecar_path = app.path()
            .resolve(sidecar_name, tauri::path::BaseDirectory::Resource)?;
        
        Ok(sidecar_path)
    }
}
