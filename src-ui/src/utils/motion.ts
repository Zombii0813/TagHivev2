/**
 * 动效辅助：集中处理「减少动态效果」偏好，以及不适合用纯 CSS 表达的过渡。
 *
 * 纯 CSS 过渡已由 styles/index.css 末尾的 prefers-reduced-motion 规则统一关闭；
 * 这里的 JS 动画（Web Animations / View Transitions）不受该规则约束，需自行判断。
 */

/** 与 styles/index.css 中 --ease-out 保持一致的进场缓动曲线 */
const EASE_OUT = 'cubic-bezier(0.22, 1, 0.36, 1)'

/** fadeInElement 创建的动画标识，用于在重复触发时只取消自己创建的那一条 */
const FADE_ANIMATION_ID = 'th-content-fade'

/** 用户是否开启了系统级「减少动态效果」 */
export function prefersReducedMotion(): boolean {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return false
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

/**
 * 让元素做一次淡入，用于「内容被整体替换」而元素本身并未重新挂载的场景。
 *
 * 只动 opacity、不动 transform：避免影响以该元素为边界做几何测量的逻辑
 * （框选、悬浮导航窗的边界计算等）。重复触发时会重新开始而不是叠加。
 *
 * @param el 目标元素；为空时静默跳过
 * @param from 起始不透明度，取非 0 值可让连续触发时不至于整块闪烁
 * @param duration 时长（毫秒）
 */
export function fadeInElement(el: HTMLElement | null | undefined, from = 0.25, duration = 200): void {
  if (!el || typeof el.animate !== 'function' || prefersReducedMotion()) return
  for (const running of el.getAnimations?.() ?? []) {
    if (running.id === FADE_ANIMATION_ID) running.cancel()
  }
  el.animate([{ opacity: from }, { opacity: 1 }], { duration, easing: EASE_OUT, id: FADE_ANIMATION_ID })
}

/**
 * 用 View Transitions API 把一次界面变更呈现为整页交叉淡化（如切换主题）。
 *
 * 运行环境不支持或用户要求减少动效时直接执行变更，行为与原先一致。
 *
 * @param update 执行实际变更的回调；返回 Promise 时会等待其完成后再截取新画面
 */
export function runViewTransition(update: () => void | Promise<void>): void {
  const start = typeof document === 'undefined'
    ? undefined
    : (document as unknown as { startViewTransition?: (callback: () => void | Promise<void>) => unknown }).startViewTransition
  if (typeof start !== 'function' || prefersReducedMotion()) {
    void update()
    return
  }
  start.call(document, update)
}
