use crate::window_bounds::{fit, Bounds};
use serde::{Deserialize, Serialize};
use std::{path::PathBuf, sync::Mutex};
use tauri::{Manager, PhysicalPosition, PhysicalSize, WindowEvent};

#[derive(Clone, Serialize, Deserialize)]
struct Placement {
    x: i32,
    y: i32,
    width: u32,
    height: u32,
    scale: f64,
    maximized: bool,
}

struct SavedWindow {
    path: PathBuf,
    normal: Placement,
}

/// 先修正窗口边界，再显示；不依赖新插件或修改发布版本。
pub fn restore(window: &tauri::WebviewWindow, directory: PathBuf) -> tauri::Result<()> {
    let path = directory.join("window-state.json");
    let saved: Option<Placement> = std::fs::read(&path)
        .ok()
        .and_then(|data| serde_json::from_slice::<Placement>(&data).ok())
        .filter(|p| p.width > 0 && p.height > 0 && p.scale.is_finite() && p.scale > 0.0);
    let monitors = window.available_monitors()?;
    let selected = saved
        .as_ref()
        .and_then(|p| {
            monitors.iter().find(|m| {
                let area = m.work_area();
                (p.x as i64) >= area.position.x as i64
                    && (p.x as i64) < area.position.x as i64 + area.size.width as i64
                    && (p.y as i64) >= area.position.y as i64
                    && (p.y as i64) < area.position.y as i64 + area.size.height as i64
            })
        })
        .cloned()
        .or(window.primary_monitor()?)
        .or_else(|| monitors.first().cloned());
    if let Some(monitor) = selected {
        let scale = monitor.scale_factor();
        let area = monitor.work_area();
        let inner = window.inner_size()?;
        let outer = window.outer_size()?;
        let frame_width = outer.width.saturating_sub(inner.width);
        let frame_height = outer.height.saturating_sub(inner.height);
        let ratio = saved.as_ref().map_or(scale, |p| scale / p.scale);
        let width = saved.as_ref().map_or(1680, |p| p.width);
        let height = saved.as_ref().map_or(900, |p| p.height);
        let desired_width = (width as f64 * ratio).round() as u32;
        let desired_height = (height as f64 * ratio).round() as u32;
        let bounds = fit(
            Bounds {
                x: saved.as_ref().map_or(
                    area.position.x + area.size.width.saturating_sub(desired_width) as i32 / 2,
                    |p| p.x,
                ),
                y: saved.as_ref().map_or(
                    area.position.y + area.size.height.saturating_sub(desired_height) as i32 / 2,
                    |p| p.y,
                ),
                width: desired_width.saturating_add(frame_width),
                height: desired_height.saturating_add(frame_height),
            },
            Bounds {
                x: area.position.x,
                y: area.position.y,
                width: area.size.width,
                height: area.size.height,
            },
        );
        let available_width = area.size.width.saturating_sub(frame_width).max(1);
        let available_height = area.size.height.saturating_sub(frame_height).max(1);
        window.set_min_size(Some(PhysicalSize::new(
            ((1000.0 * scale) as u32).min(available_width),
            ((700.0 * scale) as u32).min(available_height),
        )))?;
        window.set_size(PhysicalSize::new(
            bounds.width.saturating_sub(frame_width).max(1),
            bounds.height.saturating_sub(frame_height).max(1),
        ))?;
        window.set_position(PhysicalPosition::new(bounds.x, bounds.y))?;
    }
    let inner = window.inner_size()?;
    let position = window.outer_position()?;
    let normal = Placement {
        x: position.x,
        y: position.y,
        width: inner.width,
        height: inner.height,
        scale: window.scale_factor()?,
        maximized: saved.as_ref().is_some_and(|p| p.maximized),
    };
    let maximize = normal.maximized;
    window.manage(Mutex::new(SavedWindow { path, normal }));
    if maximize {
        window.maximize()?;
    }
    window.show()
}

/// 事件只更新内存中的正常边界；关闭时保存，避免拖动期间频繁写盘。
pub fn on_event(window: &tauri::Window, event: &WindowEvent) {
    if window.label() != "main" {
        return;
    }
    let Some(state) = window.try_state::<Mutex<SavedWindow>>() else {
        return;
    };
    let Ok(mut state) = state.lock() else {
        return;
    };
    if matches!(
        event,
        WindowEvent::Moved(_)
            | WindowEvent::Resized(_)
            | WindowEvent::ScaleFactorChanged { .. }
            | WindowEvent::CloseRequested { .. }
    ) {
        if !window.is_minimized().unwrap_or(false) {
            state.normal.maximized = window.is_maximized().unwrap_or(false);
            if !state.normal.maximized {
                if let (Ok(position), Ok(size), Ok(scale)) = (
                    window.outer_position(),
                    window.inner_size(),
                    window.scale_factor(),
                ) {
                    state.normal = Placement {
                        x: position.x,
                        y: position.y,
                        width: size.width,
                        height: size.height,
                        scale,
                        maximized: false,
                    };
                }
            }
        }
        if matches!(event, WindowEvent::CloseRequested { .. }) {
            let result = serde_json::to_vec(&state.normal)
                .map_err(std::io::Error::other)
                .and_then(|data| std::fs::write(&state.path, data));
            if let Err(error) = result {
                eprintln!("Failed to save window state: {error}");
            }
        }
    }
}
