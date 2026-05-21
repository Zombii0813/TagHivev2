// 为新建标签挑选默认颜色：优先使用调色板中尚未被现有标签使用的颜色；
// 若调色板用尽，则在调色板中选与现有标签"色相距离最远"的颜色，避免与已有标签视觉撞色。

// 标签默认调色板（28 色）。新建/编辑对话框中的色板与 pickDistinctColor 共用。
export const PRESET_COLORS = [
  '#F44336','#E91E63','#9C27B0','#673AB7','#3F51B5','#2196F3','#03A9F4','#00BCD4',
  '#009688','#4CAF50','#8BC34A','#CDDC39','#FFEB3B','#FFC107','#FF9800','#FF5722',
  '#795548','#9E9E9E','#607D8B','#000000','#CA7DF9','#F48FB1','#CE93D8','#90CAF9',
  '#A5D6A7','#FFF176','#FFCC80','#BCAAA4',
]

function hexToRgb(hex: string): [number, number, number] | null {
  const v = hex.trim().replace(/^#/, '')
  const full = v.length === 3
    ? v.split('').map(c => c + c).join('')
    : v
  if (!/^[0-9a-fA-F]{6}$/.test(full)) return null
  return [
    parseInt(full.slice(0, 2), 16),
    parseInt(full.slice(2, 4), 16),
    parseInt(full.slice(4, 6), 16),
  ]
}

function rgbToHsl(r: number, g: number, b: number): [number, number, number] {
  r /= 255; g /= 255; b /= 255
  const max = Math.max(r, g, b)
  const min = Math.min(r, g, b)
  const l = (max + min) / 2
  let h = 0, s = 0
  if (max !== min) {
    const d = max - min
    s = l > 0.5 ? d / (2 - max - min) : d / (max + min)
    switch (max) {
      case r: h = ((g - b) / d + (g < b ? 6 : 0)); break
      case g: h = ((b - r) / d + 2); break
      case b: h = ((r - g) / d + 4); break
    }
    h *= 60
  }
  return [h, s, l]
}

function colorDistance(a: string, b: string): number {
  const ra = hexToRgb(a), rb = hexToRgb(b)
  if (!ra || !rb) return 0
  const [ha] = rgbToHsl(...ra)
  const [hb] = rgbToHsl(...rb)
  // 在色环上的最短距离 (0..180)
  const diff = Math.abs(ha - hb)
  return Math.min(diff, 360 - diff)
}

/**
 * 在 palette 中挑一个与 used 中颜色尽量不同的颜色。
 * - 若有未使用的颜色，从中随机选一个。
 * - 若全部用过，选与所有已用颜色"最近距离最大"的那个（最远者）。
 */
export function pickDistinctColor(used: string[], palette: string[]): string {
  if (palette.length === 0) return '#409EFF'

  const normalize = (c: string) => c.trim().toUpperCase()
  const usedSet = new Set(used.map(normalize).filter(Boolean))

  const unused = palette.filter(c => !usedSet.has(normalize(c)))
  if (unused.length > 0) {
    return unused[Math.floor(Math.random() * unused.length)]
  }

  // 全用过：找与所有 used 颜色最小距离最大的（最远）
  let best = palette[0]
  let bestScore = -1
  for (const c of palette) {
    let minDist = Infinity
    for (const u of usedSet) {
      const d = colorDistance(c, u)
      if (d < minDist) minDist = d
    }
    if (minDist > bestScore) {
      bestScore = minDist
      best = c
    }
  }
  return best
}
