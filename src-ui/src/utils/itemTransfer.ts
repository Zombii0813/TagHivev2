// 拖放落点的移动/复制执行逻辑。
//
// 从 BrowserView 抽出，供文件夹树、文件夹卡片、explorer 空白区与浏览标签页
// 共用：标签页落点在 BrowserTabsBar 里，取不到 BrowserView 的局部函数，
// 各写一份则四处的边界判断（拖到自身/子目录、跨工作区）容易走偏。

import { ElMessage } from 'element-plus'
import { fileApi } from '../api/files'
import { folderApi } from '../api/folders'
import type { ItemDragState } from './dragItems'

/** 落点信息：目标目录及其所属工作区，copy 为真表示复制而非移动 */
export interface TransferTarget {
  targetPath: string
  targetWs: string
  copy: boolean
}

/**
 * 把拖拽项移动或复制到目标目录。
 *
 * 自行弹出成功/失败提示，不抛异常，便于各落点直接 await。
 * 不负责刷新列表与清理拖拽状态，由调用方按各自时机处理。
 *
 * @param drag 拖拽内容（文件 id 列表或单个文件夹路径）
 * @param target 目标目录、目标工作区与操作类型
 * @returns 是否实际完成了操作；被边界判断拦下或出错时为 false
 */
export async function transferItems(
  drag: ItemDragState,
  target: TransferTarget
): Promise<boolean> {
  const { targetPath, targetWs, copy } = target
  try {
    if (drag.kind === 'file' && drag.fileIds?.length) {
      if (copy) {
        const r = await fileApi.copy(drag.fileIds, targetPath, targetWs)
        ElMessage.success(`已复制 ${r.files.length} 个文件`)
      } else {
        const r = await fileApi.move(drag.fileIds, targetPath, targetWs)
        ElMessage.success(`已移动 ${r.files.length} 个文件`)
      }
      return true
    }

    if (drag.kind === 'folder' && drag.folderPath) {
      // 防止把文件夹拖到自身或子目录
      const src = drag.folderPath.replace(/\\/g, '/')
      const dst = targetPath.replace(/\\/g, '/')
      if (dst === src || dst.startsWith(src + '/')) {
        ElMessage.warning('不能移动到文件夹自身或其子目录')
        return false
      }
      if (copy) {
        await folderApi.copyFolder(drag.folderPath, targetPath)
        ElMessage.success('已复制文件夹')
      } else {
        await folderApi.moveFolder(drag.folderPath, targetPath, targetWs)
        ElMessage.success('已移动文件夹')
      }
      return true
    }

    return false
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || (copy ? '复制失败' : '移动失败'))
    return false
  }
}
