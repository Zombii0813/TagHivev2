// 工作区配色：按工作区路径生成稳定的淡彩配色，用于标签页底色与侧栏圆点记号。
//
// 采用「哈希 → 色相」而非真随机：真随机需要落盘保存映射，且新增/移除工作区
// 时容易漂移；哈希是纯函数，同一路径在任何会话、任何窗口都得到同一颜色，
// 无需持久化。

/** 一个工作区在当前主题下的配色 */
export interface WorkspacePalette {
  /** 侧栏圆形记号 */
  dot: string
  /** 非活动标签页底色 */
  bg: string
  /** 活动标签页底色 */
  bgActive: string
  /** 非活动标签页文字 */
  text: string
  /** 活动标签页文字 */
  textActive: string
}

/**
 * 由工作区路径计算色相。
 *
 * FNV-1a 哈希后再乘黄金角，使路径仅差一个字符的两个工作区也能分到
 * 明显不同的色相，而不是聚在相邻色带里难以区分。
 *
 * @param ws 工作区根路径
 * @returns 0–360 的色相值
 */
export function workspaceHue(ws: string): number {
  let h = 2166136261
  for (let i = 0; i < ws.length; i++) {
    h ^= ws.charCodeAt(i)
    h = Math.imul(h, 16777619)
  }
  return ((h >>> 0) * 137.508) % 360
}

/**
 * 取工作区在指定主题下的配色。
 *
 * 底色统一低饱和高明度（暗色主题下为低明度），保证「偏淡、对比度不高」；
 * 文字另取同色相的深/浅端，避免为了淡雅牺牲可读性。
 *
 * @param ws 工作区根路径；空串表示全局视图或未归属，返回中性灰
 * @param dark 是否为暗色主题
 * @returns 该工作区的配色
 */
export function workspacePalette(ws: string, dark: boolean): WorkspacePalette {
  if (!ws) {
    return dark
      ? {
          dot: 'hsl(0, 0%, 55%)',
          bg: 'hsl(220, 6%, 24%)',
          bgActive: 'hsl(220, 8%, 34%)',
          text: 'hsl(220, 5%, 70%)',
          textActive: 'hsl(220, 8%, 90%)',
        }
      : {
          dot: 'hsl(0, 0%, 62%)',
          bg: 'hsl(220, 12%, 94%)',
          bgActive: 'hsl(220, 14%, 86%)',
          text: 'hsl(220, 8%, 42%)',
          textActive: 'hsl(220, 12%, 26%)',
        }
  }

  const h = workspaceHue(ws).toFixed(1)
  return dark
    ? {
        dot: `hsl(${h}, 38%, 56%)`,
        bg: `hsl(${h}, 20%, 24%)`,
        bgActive: `hsl(${h}, 26%, 34%)`,
        text: `hsl(${h}, 14%, 70%)`,
        textActive: `hsl(${h}, 24%, 89%)`,
      }
    : {
        dot: `hsl(${h}, 52%, 62%)`,
        bg: `hsl(${h}, 48%, 94%)`,
        bgActive: `hsl(${h}, 52%, 85%)`,
        text: `hsl(${h}, 22%, 42%)`,
        textActive: `hsl(${h}, 42%, 26%)`,
      }
}
