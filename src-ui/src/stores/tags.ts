import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import type { Tag } from '../types'
import { tagApi } from '../api/tags'
import { useFileStore } from './files'

function buildTagOrderKey(root?: string | null) {
  return `taghive:tag-order:${root || '__global__'}`
}

function buildTagFilterModeKey(root?: string | null) {
  return `taghive:tag-filter-mode:${root || '__global__'}`
}

/** 标签过滤模式：
 * - with-descendants：选中父标签时连同所有后代标签一起作为过滤条件（默认，与历史行为一致）
 * - self-only：仅以用户实际点选的标签作为过滤条件，不展开后代
 */
export type TagFilterMode = 'with-descendants' | 'self-only'

export interface TagTreeNode {
  tag: Tag
  children: TagTreeNode[]
  depth: number
}

/** 将平铺的标签列表构建为树形结构（顶级 → children） */
function buildTagTree(tags: Tag[]): TagTreeNode[] {
  const map = new Map<number, TagTreeNode>()
  const roots: TagTreeNode[] = []

  for (const tag of tags) {
    map.set(tag.id, { tag, children: [], depth: 0 })
  }

  for (const tag of tags) {
    const node = map.get(tag.id)!
    if (tag.parent_id != null && map.has(tag.parent_id)) {
      const parentNode = map.get(tag.parent_id)!
      node.depth = parentNode.depth + 1
      parentNode.children.push(node)
    } else {
      roots.push(node)
    }
  }

  // 递归设置正确的 depth
  function setDepth(nodes: TagTreeNode[], depth: number) {
    for (const n of nodes) {
      n.depth = depth
      setDepth(n.children, depth + 1)
    }
  }
  setDepth(roots, 0)

  return roots
}

/** 将树形结构展开为有序的平铺列表（尊重折叠状态） */
function flattenTree(nodes: TagTreeNode[], expandedIds: Set<number>): TagTreeNode[] {
  const result: TagTreeNode[] = []
  for (const node of nodes) {
    result.push(node)
    if (node.children.length > 0 && expandedIds.has(node.tag.id)) {
      result.push(...flattenTree(node.children, expandedIds))
    }
  }
  return result
}

export const useTagStore = defineStore('tags', () => {
  // State
  const tags = ref<Tag[]>([])
  const selectedTagIds = ref<Set<number>>(new Set())
  const isLoading = ref(false)
  const orderIds = ref<number[]>([])
  const lastLoadedRoot = ref<string>()
  const expandedTagIds = ref<Set<number>>(new Set())
  const tagFilterMode = ref<TagFilterMode>('with-descendants')

  // Getters
  const tagMap = computed(() => {
    const map = new Map<number, Tag>()
    tags.value.forEach(tag => map.set(tag.id, tag))
    return map
  })

  const selectedTags = computed(() => {
    return tags.value.filter(t => selectedTagIds.value.has(t.id))
  })

  const hasSelection = computed(() => selectedTagIds.value.size > 0)

  const orderedTags = computed(() => {
    if (!orderIds.value.length) {
      return tags.value
    }

    const orderMap = new Map(orderIds.value.map((id, index) => [id, index]))
    return [...tags.value].sort((left, right) => {
      const leftOrder = orderMap.get(left.id) ?? Number.MAX_SAFE_INTEGER
      const rightOrder = orderMap.get(right.id) ?? Number.MAX_SAFE_INTEGER
      if (leftOrder !== rightOrder) {
        return leftOrder - rightOrder
      }
      return left.name.localeCompare(right.name, 'zh-CN')
    })
  })

  /** 树形结构（按 orderedTags 顺序构建） */
  const tagTree = computed<TagTreeNode[]>(() => buildTagTree(orderedTags.value))

  /** parent_id → 直接子标签 ID 列表，用于 O(1) 父子查找 */
  const childrenIndex = computed<Map<number, number[]>>(() => {
    const map = new Map<number, number[]>()
    for (const tag of tags.value) {
      if (tag.parent_id != null) {
        const list = map.get(tag.parent_id)
        if (list) list.push(tag.id)
        else map.set(tag.parent_id, [tag.id])
      }
    }
    return map
  })

  /** 展开后的平铺列表（用于渲染） */
  const flatTagList = computed<TagTreeNode[]>(() =>
    flattenTree(tagTree.value, expandedTagIds.value)
  )

  /** 所有子标签的ID（递归） - 走 childrenIndex，避免 O(n²) */
  function getDescendantIds(tagId: number): number[] {
    const result: number[] = []
    const idx = childrenIndex.value
    const stack = [tagId]
    while (stack.length) {
      const cur = stack.pop()!
      const children = idx.get(cur)
      if (!children) continue
      for (const cid of children) {
        result.push(cid)
        stack.push(cid)
      }
    }
    return result
  }

  /** 实际下发给查询的标签 ID 集合。
   * - with-descendants：用户选中的标签 ∪ 其所有后代
   * - self-only：仅用户选中的标签本身
   * 注意：selectedTagIds 始终只保存"用户实际点击的标签"，后代展开放在此处计算，便于模式切换。
   */
  const effectiveTagIds = computed<Set<number>>(() => {
    if (tagFilterMode.value === 'self-only') {
      return new Set(selectedTagIds.value)
    }
    const result = new Set<number>(selectedTagIds.value)
    for (const id of selectedTagIds.value) {
      for (const cid of getDescendantIds(id)) {
        result.add(cid)
      }
    }
    return result
  })

  /** 标签是否处于"激活"视觉态（用于侧栏高亮）。
   * 与 effectiveTagIds 对齐：
   * - self-only：仅用户实际点选的标签高亮
   * - with-descendants：点选的标签及其所有后代标签都高亮
   */
  function isTagActive(tagId: number): boolean {
    return effectiveTagIds.value.has(tagId)
  }

  function syncTagOrder(root?: string) {
    const storageKey = buildTagOrderKey(root)
    let storedOrder: number[] = []

    try {
      const raw = localStorage.getItem(storageKey)
      if (raw) {
        const parsed = JSON.parse(raw)
        if (Array.isArray(parsed)) {
          storedOrder = parsed.filter((id): id is number => typeof id === 'number')
        }
      }
    } catch (error) {
      console.warn('Failed to parse tag order:', error)
    }

    const tagIdSet = new Set(tags.value.map(tag => tag.id))
    const seen = new Set<number>()
    const validStored: number[] = []
    for (const id of storedOrder) {
      if (tagIdSet.has(id) && !seen.has(id)) {
        validStored.push(id)
        seen.add(id)
      }
    }
    const missingIds: number[] = []
    for (const id of tagIdSet) {
      if (!seen.has(id)) missingIds.push(id)
    }
    orderIds.value = [...validStored, ...missingIds]
    localStorage.setItem(storageKey, JSON.stringify(orderIds.value))
  }

  function persistTagOrder(root?: string) {
    localStorage.setItem(buildTagOrderKey(root), JSON.stringify(orderIds.value))
  }

  // Actions
  async function loadTags(root?: string) {
    isLoading.value = true
    lastLoadedRoot.value = root
    loadTagFilterMode(root)
    try {
      tags.value = await tagApi.getAll(root)
      syncTagOrder(root)
      // 默认展开所有有子标签的父标签 - 走 childrenIndex 避免 O(n²)
      expandedTagIds.value = new Set(childrenIndex.value.keys())
    } catch (error) {
      console.error('Failed to load tags:', error)
    } finally {
      isLoading.value = false
    }
  }

  async function reloadTags() {
    await loadTags(lastLoadedRoot.value)
  }

  async function createTag(name: string, color?: string, description?: string, workspace?: string, icon?: string, parentId?: number | null) {
    try {
      const tag = await tagApi.create({ name, color, description, workspace, icon, parent_id: parentId })
      tags.value.push(tag)
      syncTagOrder(workspace)
      return tag
    } catch (error) {
      console.error('Failed to create tag:', error)
      throw error
    }
  }

  async function updateTag(id: number, updates: Partial<Tag> & { parent_id?: number | null }) {
    try {
      const tag = await tagApi.update(id, updates)
      const index = tags.value.findIndex(t => t.id === id)
      if (index !== -1) {
        tags.value[index] = tag
      }
      return tag
    } catch (error) {
      console.error('Failed to update tag:', error)
      throw error
    }
  }

  async function deleteTag(id: number) {
    try {
      await tagApi.delete(id)
      tags.value = tags.value.filter(t => t.id !== id)
      selectedTagIds.value.delete(id)
      orderIds.value = orderIds.value.filter(tagId => tagId !== id)
      persistTagOrder(lastLoadedRoot.value)
      const fileStore = useFileStore()
      fileStore.removeTagFromAllFiles(id)
    } catch (error) {
      console.error('Failed to delete tag:', error)
      throw error
    }
  }

  function toggleExpand(tagId: number) {
    if (expandedTagIds.value.has(tagId)) {
      expandedTagIds.value.delete(tagId)
    } else {
      expandedTagIds.value.add(tagId)
    }
  }

  function selectTag(id: number, multi: boolean = false) {
    // 仅记录"用户点击的标签"。是否在查询时展开后代，由 tagFilterMode + effectiveTagIds 决定。
    if (multi) {
      if (selectedTagIds.value.has(id)) {
        selectedTagIds.value.delete(id)
      } else {
        selectedTagIds.value.add(id)
      }
    } else {
      selectedTagIds.value.clear()
      selectedTagIds.value.add(id)
    }
  }

  function setTagFilterMode(mode: TagFilterMode) {
    if (tagFilterMode.value === mode) return
    tagFilterMode.value = mode
    try {
      localStorage.setItem(buildTagFilterModeKey(lastLoadedRoot.value), mode)
    } catch (error) {
      console.warn('Failed to persist tag filter mode:', error)
    }
  }

  function loadTagFilterMode(root?: string | null) {
    try {
      const raw = localStorage.getItem(buildTagFilterModeKey(root))
      tagFilterMode.value = raw === 'self-only' ? 'self-only' : 'with-descendants'
    } catch {
      tagFilterMode.value = 'with-descendants'
    }
  }

  function clearSelection() {
    selectedTagIds.value.clear()
  }

  function selectAll() {
    tags.value.forEach(t => selectedTagIds.value.add(t.id))
  }

  function getTagById(id: number): Tag | undefined {
    return tagMap.value.get(id)
  }

  function getTagsByIds(ids: number[]): Tag[] {
    return ids.map(id => tagMap.value.get(id)).filter((t): t is Tag => t !== undefined)
  }

  function reorderTags(draggedTagId: number, targetTagId?: number | null) {
    const currentOrder = [...orderedTags.value.map(tag => tag.id)]
    const draggedIndex = currentOrder.indexOf(draggedTagId)

    if (draggedIndex === -1) {
      return
    }

    currentOrder.splice(draggedIndex, 1)

    if (targetTagId == null) {
      currentOrder.push(draggedTagId)
    } else {
      const targetIndex = currentOrder.indexOf(targetTagId)
      if (targetIndex === -1) {
        currentOrder.push(draggedTagId)
      } else {
        currentOrder.splice(targetIndex, 0, draggedTagId)
      }
    }

    orderIds.value = currentOrder
    persistTagOrder(lastLoadedRoot.value)
  }

  async function assignTagsToFiles(fileIds: number[], tagIds: number[]) {
    const uniqueFileIds = Array.from(new Set(fileIds))
    const uniqueTagIds = Array.from(new Set(tagIds))

    if (!uniqueFileIds.length || !uniqueTagIds.length) {
      return { files: 0, tags: 0 }
    }

    try {
      const result = await tagApi.batchAssign(uniqueFileIds, uniqueTagIds)
      const fileStore = useFileStore()
      fileStore.addTagsToFiles(uniqueFileIds, uniqueTagIds)
      await reloadTags()
      return result
    } catch (error) {
      console.error('Failed to assign tags to files:', error)
      throw error
    }
  }

  async function removeTagFromFiles(fileIds: number[], tagId: number) {
    const uniqueFileIds = Array.from(new Set(fileIds))

    if (!uniqueFileIds.length) {
      return { files: 0, affected: 0 }
    }

    try {
      const result = await tagApi.batchUnassign(uniqueFileIds, tagId)
      const fileStore = useFileStore()
      fileStore.removeTagFromFiles(uniqueFileIds, tagId)
      await reloadTags()
      return result
    } catch (error) {
      console.error('Failed to unassign tag from files:', error)
      throw error
    }
  }

  return {
    tags,
    selectedTagIds,
    isLoading,
    tagMap,
    selectedTags,
    hasSelection,
    orderedTags,
    tagTree,
    flatTagList,
    expandedTagIds,
    lastLoadedRoot,
    tagFilterMode,
    effectiveTagIds,
    isTagActive,
    setTagFilterMode,
    loadTags,
    reloadTags,
    createTag,
    updateTag,
    deleteTag,
    selectTag,
    clearSelection,
    selectAll,
    getTagById,
    getTagsByIds,
    getDescendantIds,
    toggleExpand,
    reorderTags,
    assignTagsToFiles,
    removeTagFromFiles,
  }
})
