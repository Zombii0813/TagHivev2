/// 主窗口的物理像素边界，包含系统边框。
#[derive(Clone, Copy, Debug)]
pub struct Bounds {
    pub x: i32,
    pub y: i32,
    pub width: u32,
    pub height: u32,
}

/// 将初始或历史窗口限制在当前显示器工作区内，兼容负坐标显示器。
pub fn fit(mut window: Bounds, area: Bounds) -> Bounds {
    window.width = window.width.max(1).min(area.width.max(1));
    window.height = window.height.max(1).min(area.height.max(1));
    window.x = (window.x as i64).clamp(
        area.x as i64,
        area.x as i64 + (area.width - window.width) as i64,
    ) as i32;
    window.y = (window.y as i64).clamp(
        area.y as i64,
        area.y as i64 + (area.height - window.height) as i64,
    ) as i32;
    window
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn large_default_fits_small_display() {
        let fitted = fit(
            Bounds {
                x: 0,
                y: 0,
                width: 2100,
                height: 1125,
            },
            Bounds {
                x: 0,
                y: 0,
                width: 1366,
                height: 728,
            },
        );
        assert_eq!((fitted.width, fitted.height), (1366, 728));
        assert_eq!((fitted.x, fitted.y), (0, 0));
    }

    #[test]
    fn disconnected_monitor_restores_inside_current_display() {
        let fitted = fit(
            Bounds {
                x: 3000,
                y: -900,
                width: 1100,
                height: 700,
            },
            Bounds {
                x: 0,
                y: 0,
                width: 1366,
                height: 728,
            },
        );
        assert_eq!((fitted.x, fitted.y), (266, 0));
    }

    #[test]
    fn negative_monitor_keeps_valid_position() {
        let fitted = fit(
            Bounds {
                x: -1800,
                y: 40,
                width: 1200,
                height: 720,
            },
            Bounds {
                x: -1920,
                y: 0,
                width: 1920,
                height: 1040,
            },
        );
        assert_eq!((fitted.x, fitted.y), (-1800, 40));
    }
}
