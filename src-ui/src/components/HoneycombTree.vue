<template>
  <Teleport to="body">
    <!--
      hc-float: 固定定位，transform 控制位置
      内容：图标 + SVG 蜂巢（直接裸露，无面板背景）
    -->
    <div
      ref="floatRef"
      class="hc-float"
      :class="{ expanded: isExpanded, dragging: isDragging }"
      :style="floatStyle"
    >
      <!-- 图标（始终可见，可拖拽）：裸六边形，无背景方框 -->
      <div class="hc-icon" @mousedown.left.prevent="startDrag" @mouseenter="onEnter" @mouseleave="onLeave">
        <svg
          :viewBox="`${-R-2} ${-R-2} ${(R+2)*2} ${(R+2)*2}`"
          :width="ICON_W + 4"
          :height="ICON_H + 4"
          class="hc-icon-svg"
          style="overflow:visible"
        >
          <!-- 脉冲波纹（悬停时） -->
          <circle v-if="isExpanded" class="hc-ripple r1" cx="0" cy="0" :r="R * 0.8"/>
          <circle v-if="isExpanded" class="hc-ripple r2" cx="0" cy="0" :r="R * 0.8"/>
          <!-- 六边形填充 -->
          <polygon :points="hexPts(R - 1)" class="hc-icon-poly"/>
          <!-- 文字标签 -->
          <text class="hc-icon-txt" text-anchor="middle" dy="4">{{ iconLabel }}</text>
        </svg>
        <!-- 返回上级徽章（有上级时显示） -->
        <div
          v-if="canGoBack"
          class="hc-back-badge"
          title="返回上级"
          @mousedown.stop
          @click.stop="goBack"
        >↩</div>
      </div>

      <!-- 蜂巢 SVG（展开时，以图标为原点向外扩散） -->
      <svg
        v-if="isExpanded && !loading && visibleNodes.length > 0"
        class="hc-scene"
        :style="sceneStyle"
        :viewBox="sceneViewBox"
        :width="sceneW"
        :height="sceneH"
        @click.self.stop
        @mouseenter="onEnter"
        @mouseleave="onLeave"
      >
        <!-- 连线 -->
        <line
          v-for="e in edges"
          :key="e.id"
          :x1="e.x1" :y1="e.y1" :x2="e.x2" :y2="e.y2"
          class="hc-edge"
          :class="{ ring2: e.ring === 2 }"
          :style="{ animationDelay: `${e.ring * 60}ms` }"
        />

        <!-- 节点 -->
        <g
          v-for="node in visibleNodes"
          :key="node.path"
          :transform="`translate(${node.cx},${node.cy})`"
        >
          <!-- 内层 g 负责动画（不含 translate，避免与 CSS transform 冲突） -->
          <g
            class="hc-node-g"
            :class="{
              'is-ring2': node.ring === 2,
              'is-page-btn': node.type === 'prev' || node.type === 'next',
              'is-page-inactive': (node.type === 'prev' || node.type === 'next') && node.parentPath !== 'active',
              'is-selected': selectedPath === node.path,
            }"
            :style="{ animationDelay: `${node.ring * 60}ms` }"
            @click.stop="handleClick(node)"
            @contextmenu.prevent.stop="handleCtx(node, $event)"
          >
            <!-- 描边六边形 -->
            <polygon
              :points="hexPts(node.r)"
              class="hc-hex-stroke"
              :class="{ 'stroke-selected': selectedPath === node.path }"
            />
            <!-- 填色六边形 -->
            <polygon
              :points="hexPts(node.r - 2)"
              class="hc-hex-fill"
              :class="{ 'fill-selected': selectedPath === node.path }"
              :style="hexFillStyle(node)"
            />
            <!-- 翻页按钮：仅显示箭头符号 -->
            <text v-if="node.type === 'prev' || node.type === 'next'"
              class="hc-page-arrow" text-anchor="middle" dy="5">{{ node.shortName }}</text>
            <!-- 普通节点：文字 -->
            <template v-else>
              <text class="hc-lbl" :class="{ 'hc-lbl-sm': node.ring === 2 }" text-anchor="middle" dy="-4">{{ node.shortName }}</text>
              <text class="hc-cnt" text-anchor="middle" dy="10">{{ node.file_count }}</text>
              <!-- 有子目录指示点 -->
              <circle v-if="node.hasChildren" class="hc-dot" cx="0" :cy="node.r*0.74" r="2.5"/>
            </template>
          </g>
        </g>
      </svg>

      <!-- 加载动画（展开中） -->
      <div v-if="isExpanded && loading" class="hc-loading-hint">
        <el-icon class="hc-spin"><Loading /></el-icon>
      </div>
    </div>
  </Teleport>

  <!-- 右键菜单 -->
  <el-popover
    :visible="ctxVisible"
    :virtual-ref="ctxAnchorEl"
    virtual-triggering
    trigger="contextmenu"
    placement="bottom-start"
    :width="148"
    popper-class="context-menu-popover"
    @update:visible="(v:boolean)=>{ if(!v) ctxVisible=false }"
  >
    <div class="context-menu">
      <div class="context-menu-item" @click="openCreateDlg">
        <el-icon><FolderAdd /></el-icon>
        <span>新建子目录</span>
      </div>
    </div>
  </el-popover>

  <el-dialog v-model="showDlg" title="新建子目录" width="400px" append-to-body destroy-on-close>
    <div class="create-hint">在 <strong>{{ ctxNode?.name }}</strong> 下创建</div>
    <el-input v-model="newName" placeholder="输入目录名称" maxlength="80" clearable style="margin-top:12px" @keyup.enter="confirmCreate"/>
    <template #footer>
      <el-button @click="showDlg=false">取消</el-button>
      <el-button type="primary" :loading="creating" :disabled="!newName.trim()" @click="confirmCreate">创建</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { Loading, FolderAdd } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { invoke } from '@tauri-apps/api/core'
import { folderApi } from '../api/folders'
import type { FolderNode } from '../types'

// ─── Props & Emits ────────────────────────────────────────────
const props = defineProps<{
  rootPath?: string | null
  workspaces?: string[]
  boundary?: HTMLElement | null   // 拖拽边界容器（文件列表区域）
}>()

const emit = defineEmits<{
  select: [path: string, wsPath?: string]
}>()

// ─── 几何 ─────────────────────────────────────────────────────
const R    = 36          // 六边形外接圆半径（缩小，原44）
const GAP  = 3           // 间距（缩小，原6）
const STEP = R * 2 + GAP // 相邻中心距

// 图标六边形尺寸（与蜂巢中心节点同尺寸，直接裸露无背景）
const ICON_R = R         // 图标六边形半径与节点一致
const ICON_W = ICON_R * 2
const ICON_H = ICON_R * Math.sqrt(3)

function makePts(r: number) {
  return Array.from({length:6},(_,i)=>{
    const a = (Math.PI/3)*i - Math.PI/2
    return `${(r*Math.cos(a)).toFixed(2)},${(r*Math.sin(a)).toFixed(2)}`
  }).join(' ')
}
// 动态生成任意半径的六边形顶点字符串
function hexPts(r: number) { return makePts(r) }


// ─── 类型 ─────────────────────────────────────────────────────
type NodeType = 'normal' | 'prev' | 'next'
interface HcNode {
  path:string; name:string; shortName:string
  file_count:number; hasChildren:boolean; children:FolderNode[]
  cx:number; cy:number; ring:number
  isCenter:boolean; isChild:boolean
  wsIndex:number; wsPath:string
  type: NodeType
  r: number  // 实际渲染半径（ring-2 缩小）
  parentPath?: string  // ring-2 节点的父节点路径（用于 navStack）
}
interface StackEntry { node:FolderNode; wsPath:string }
interface Edge { id:string; x1:number; y1:number; x2:number; y2:number; ring:number }
interface Crumb { name:string; path:string; wsPath:string }

// ─── 状态 ─────────────────────────────────────────────────────
const loading     = ref(false)
const wsTreeMap   = ref<Map<string,FolderNode>>(new Map())
const navStack    = ref<StackEntry[]>([])
const selectedPath = ref('')
const pageOffset  = ref(0)   // 分页：当前页起始索引
const PAGE_SIZE   = 12       // 每页最多12个子节点（ring-1 有6个槽 + ring-2 外圈的12个方向）

// 展开/收起：用 document mousemove 检测鼠标是否在浮层任意子元素范围内
const isExpanded = ref(false)
let leaveTimer: ReturnType<typeof setTimeout>|null = null

// ─── 拖拽（限制在 boundary 内） ───────────────────────────────
const floatRef   = ref<HTMLElement>()
const isDragging = ref(false)
const posX = ref(-9999)
const posY = ref(-9999)
const posInitialized = ref(false)

const floatStyle = computed(() => ({
  transform: `translate(${posX.value}px, ${posY.value}px)`,
  visibility: (posInitialized.value ? 'visible' : 'hidden') as 'visible' | 'hidden',
}))

function onEnter() {
  if (leaveTimer) { clearTimeout(leaveTimer); leaveTimer = null }
  isExpanded.value = true
}
function onLeave() {
  leaveTimer = setTimeout(() => { isExpanded.value = false }, 280)
}

function clampToBoundary(x: number, y: number) {
  const el = props.boundary
  if (!el) return { x, y }
  const rect = el.getBoundingClientRect()
  const cx = Math.max(rect.left, Math.min(x, rect.right  - ICON_W))
  const cy = Math.max(rect.top,  Math.min(y, rect.bottom - ICON_H))
  return { x: cx, y: cy }
}

function startDrag(e: MouseEvent) {
  isDragging.value = true
  isExpanded.value = false

  const ox = e.clientX - posX.value
  const oy = e.clientY - posY.value

  function onMove(ev: MouseEvent) {
    const { x, y } = clampToBoundary(ev.clientX - ox, ev.clientY - oy)
    posX.value = x; posY.value = y
  }
  function onUp() {
    isDragging.value = false
    window.removeEventListener('mousemove', onMove)
    window.removeEventListener('mouseup', onUp)
  }
  window.addEventListener('mousemove', onMove)
  window.addEventListener('mouseup', onUp)
}

// ─── 图标标签 ─────────────────────────────────────────────────
function lastName(p:string) { return p.split(/[/\\]/).filter(Boolean).pop() || p }
function truncate(s:string, n:number) { return s.length>n ? s.slice(0,n-1)+'…' : s }

const iconLabel = computed(() => {
  if (!navStack.value.length) return '⬡'
  const top = navStack.value[navStack.value.length-1]
  return truncate(lastName(top.node.path||top.node.name), 3)
})

// 面包屑（面板里用不到了，但保留供未来使用）
const breadcrumbs = computed<Crumb[]>(() =>
  navStack.value.map(e=>({ name:lastName(e.node.path||e.node.name), path:e.node.path, wsPath:e.wsPath }))
)
// eslint-disable-next-line @typescript-eslint/no-unused-vars
void breadcrumbs  // 抑制未使用警告

// ─── 蜂巢场景：SVG 位置相对 icon 中心偏移，并感知边界 ──────────
const PAD = R + 8

// 边界感知偏移：计算将蜂巢整体平移多少才能不溢出边界
const bounds = computed(() => {
  if (!visibleNodes.value.length) return { minX:0, maxX:0, minY:0, maxY:0 }
  let minX=Infinity, maxX=-Infinity, minY=Infinity, maxY=-Infinity
  for (const n of visibleNodes.value) {
    minX=Math.min(minX,n.cx-R); maxX=Math.max(maxX,n.cx+R)
    minY=Math.min(minY,n.cy-R); maxY=Math.max(maxY,n.cy+R)
  }
  return { minX:minX-PAD, maxX:maxX+PAD, minY:minY-PAD, maxY:maxY+PAD }
})

const sceneW = computed(() => bounds.value.maxX - bounds.value.minX)
const sceneH = computed(() => bounds.value.maxY - bounds.value.minY)

const sceneViewBox = computed(() => {
  const b = bounds.value
  return `${b.minX} ${b.minY} ${b.maxX-b.minX} ${b.maxY-b.minY}`
})

// SVG 左上角相对 hc-float 的偏移：让 SVG 坐标(0,0) 始终对准图标中心
// 边界感知完全由 BFS 的 slotMargin 负责，此处不做额外平移
const sceneStyle = computed(() => {
  const b = bounds.value
  const icx = ICON_W / 2
  const icy = ICON_H / 2
  return {
    left: `${icx + b.minX}px`,
    top:  `${icy + b.minY}px`,
  }
})


// ─── 几何辅助 ─────────────────────────────────────────────────
// 六边形轴坐标系的6个相邻方向（pointy-top）
const DIRS6: [number,number][] = [[1,-1],[1,0],[0,1],[-1,1],[-1,0],[0,-1]]

// 轴坐标 key（整数，无浮点误差）
function axKey(q: number, r: number): string { return `${q},${r}` }

// 轴坐标 → 像素（相对 SVG 原点，即图标中心）
function axialPx(q: number, r: number): {x:number, y:number} {
  return { x: STEP*(q + r*0.5), y: STEP*(r*Math.sqrt(3)/2) }
}

// 某轴坐标位置的节点在边界内的富裕距离（越大越安全，负值=溢出）
function slotMargin(q: number, r: number): number {
  const el = props.boundary
  if (!el) return Infinity
  const br = el.getBoundingClientRect()
  const icx = posX.value + ICON_W / 2
  const icy = posY.value + ICON_H / 2
  const margin = R + 4
  const px = axialPx(q, r)
  const sx = icx + px.x
  const sy = icy + px.y
  return Math.min(sx - margin - br.left, br.right - (sx + margin),
                  sy - margin - br.top,  br.bottom - (sy + margin))
}

// ─── BFS 槽位生成：从中心(0,0)向外波浪扩散，保证结构连续 ──────
// 返回按扩散顺序排列的轴坐标列表（已剔除中心自身）
// 策略：同一波内优先选边界内的格子（margin >= 0）；边界外的格子不放节点，
// 但仍加入 frontier 继续向外探索，从而能绕过边缘找到更内侧的格子
function bfsSlots(maxSlots: number): {q:number, r:number}[] {
  const result: {q:number, r:number}[] = []
  // seen：防止同一格子重复进入候选队列
  const seen = new Set<string>()
  seen.add(axKey(0, 0))

  let frontier: {q:number, r:number}[] = [{q:0, r:0}]

  while (result.length < maxSlots && frontier.length > 0) {
    const candidates: {q:number, r:number, margin:number}[] = []
    for (const {q, r} of frontier) {
      for (const [dq, dr] of DIRS6) {
        const nq = q + dq, nr = r + dr
        const k = axKey(nq, nr)
        if (!seen.has(k)) {
          seen.add(k)
          candidates.push({ q: nq, r: nr, margin: slotMargin(nq, nr) })
        }
      }
    }
    // 同一波内按 margin 降序：边界内(margin>=0)在前，边界外在后
    candidates.sort((a, b) => b.margin - a.margin)

    // 下一波的 frontier 包含本波所有候选格（无论是否在边界内，都继续扩散）
    frontier = candidates.map(c => ({ q: c.q, r: c.r }))

    // 只把边界内的格子放入 result；边界外的跳过（但 frontier 仍保留，用于绕行）
    for (const c of candidates) {
      if (c.margin < 0) continue
      result.push({ q: c.q, r: c.r })
      if (result.length >= maxSlots) break
    }
  }
  return result
}

// ─── 布局 ─────────────────────────────────────────────────────
const visibleNodes = computed<HcNode[]>(() => {
  if (!wsTreeMap.value.size) return []
  if (!navStack.value.length) return layoutRoots()
  return layoutCenter(navStack.value[navStack.value.length-1])
})

function layoutRoots(): HcNode[] {
  const wsList = props.workspaces ?? (props.rootPath ? [props.rootPath] : [])
  if (wsList.length === 1) {
    const ws = wsList[0]
    const root = wsTreeMap.value.get(ws)
    if (!root) return []
    return layoutCenter({ node:root, wsPath:ws })
  }
  // 多工作区：BFS 扩散分配槽位
  const slots = bfsSlots(wsList.length)
  return wsList.flatMap((ws, wi) => {
    const root = wsTreeMap.value.get(ws)
    if (!root) return []
    const s = slots[wi] ?? slots[0]
    const px = axialPx(s.q, s.r)
    return [mkNode(root, px.x, px.y, 1, false, true, wi, ws)]
  })
}

function layoutCenter(entry: StackEntry): HcNode[] {
  const { node: center, wsPath: ws } = entry
  const wi = wsIdx(ws)
  const nodes: HcNode[] = []

  const allChildren = [...(center.children ?? [])].sort((a, b) => (b.file_count ?? 0) - (a.file_count ?? 0))
  const total = allChildren.length
  if (total === 0) return nodes

  const pageCh = allChildren.slice(pageOffset.value, pageOffset.value + PAGE_SIZE)
  const needPaging = total > PAGE_SIZE

  if (needPaging) {
    // 分页模式：用 BFS 获取足够槽位，最后两个给翻页按钮
    const need = pageCh.length + 2
    const slots = bfsSlots(need)
    // 翻页按钮放在 BFS 最末两个槽（最远/最边缘，不占中心好位置）
    const prevS = slots[need - 2]
    const nextS = slots[need - 1]
    const prevPx = axialPx(prevS.q, prevS.r)
    const nextPx = axialPx(nextS.q, nextS.r)
    nodes.push(mkPageNode('prev', prevPx.x, prevPx.y, wi, ws, pageOffset.value > 0))
    nodes.push(mkPageNode('next', nextPx.x, nextPx.y, wi, ws, pageOffset.value + PAGE_SIZE < total))
    slots.slice(0, pageCh.length).forEach((s, i) => {
      const px = axialPx(s.q, s.r)
      nodes.push(mkNode(pageCh[i], px.x, px.y, 1, false, true, wi, ws))
    })
  } else {
    // 无分页：BFS 扩散填充子节点
    const slots = bfsSlots(pageCh.length)
    const occupied = new Set<string>(['0,0'])
    slots.forEach((s, i) => {
      occupied.add(axKey(s.q, s.r))
      const px = axialPx(s.q, s.r)
      nodes.push(mkNode(pageCh[i], px.x, px.y, 1, false, true, wi, ws))
    })

    // 孙节点：仅当子节点 ≤ 6 且总孙节点不多时展示
    if (pageCh.length <= 6) {
      const grandTotal = pageCh.reduce((s, c) => s + (c.children?.length ?? 0), 0)
      if (grandTotal > 0 && grandTotal <= 12) {
        // 从每个 ring-1 子节点出发，BFS 找其外侧未占用槽
        const ring1Nodes = nodes.filter(n => n.ring === 1)
        ring1Nodes.forEach(r1Node => {
          const grandChildren = (r1Node.children ?? [])
            .slice(0, Math.max(1, Math.floor(12 / ring1Nodes.length)))
          // 找 r1Node 轴坐标反推的邻格
          const candidates: {q:number,r:number,margin:number}[] = []
          for (const [dq, dr] of DIRS6) {
            // 从 r1Node 像素坐标推算邻格轴坐标（逆变换 axialPx）
            const nx = r1Node.cx + STEP*(dq + dr*0.5)
            const ny = r1Node.cy + STEP*(dr*Math.sqrt(3)/2)
            // 用像素坐标近似还原轴坐标（已知网格，直接算）
            const nr = Math.round(ny / (STEP * Math.sqrt(3) / 2))
            const nq = Math.round(nx / STEP - nr * 0.5)
            const k = axKey(nq, nr)
            if (!occupied.has(k)) {
              candidates.push({ q: nq, r: nr, margin: slotMargin(nq, nr) })
            }
          }
          candidates.sort((a, b) => b.margin - a.margin)
          grandChildren.forEach((gc, gi) => {
            const s = candidates[gi]
            if (!s) return
            occupied.add(axKey(s.q, s.r))
            const px = axialPx(s.q, s.r)
            nodes.push(mkGrandNode(gc, px.x, px.y, wi, ws, r1Node.path))
          })
        })
      }
    }
  }

  return nodes
}

function mkNode(folder:FolderNode, cx:number, cy:number, ring:number, isCenter:boolean, isChild:boolean, wsIndex:number, wsPath:string): HcNode {
  return {
    path:folder.path, name:folder.name, shortName:truncate(folder.name,7),
    file_count:folder.file_count,
    hasChildren:(folder.children?.length??0)>0,
    children:folder.children??[],
    cx, cy, ring, isCenter, isChild, wsIndex, wsPath,
    type: 'normal', r: R,
  }
}

function mkPageNode(dir: 'prev'|'next', cx:number, cy:number, wsIndex:number, wsPath:string, active: boolean): HcNode {
  return {
    path: `__page_${dir}__`,
    name: dir === 'prev' ? '◁' : '▷',
    shortName: dir === 'prev' ? '◁' : '▷',
    file_count: 0, hasChildren: false, children: [],
    cx, cy, ring: 1, isCenter: false, isChild: false,
    wsIndex, wsPath,
    type: dir,
    r: R * 0.7,
    parentPath: active ? 'active' : 'inactive',
  }
}

function mkGrandNode(folder:FolderNode, cx:number, cy:number, wsIndex:number, wsPath:string, parentPath:string): HcNode {
  return {
    path:folder.path, name:folder.name, shortName:truncate(folder.name,5),
    file_count:folder.file_count,
    hasChildren:(folder.children?.length??0)>0,
    children:folder.children??[],
    cx, cy, ring: 2, isCenter: false, isChild: true,
    wsIndex, wsPath,
    type: 'normal', r: Math.round(R * 0.72),
    parentPath,
  }
}

function wsIdx(ws:string) {
  const list = props.workspaces ?? []
  const i = list.indexOf(ws)
  return i>=0 ? i : 0
}

// ─── 连线 ─────────────────────────────────────────────────────
// 无中心节点，连线从图标原点(0,0)出发到各子节点
const edges = computed<Edge[]>(() => {
  const result: Edge[] = []
  for (const n of visibleNodes.value) {
    if (n.ring === 2 && n.parentPath) {
      const parent = visibleNodes.value.find(p => p.path === n.parentPath)
      if (parent) {
        result.push({ id:`${parent.path}→${n.path}`, x1:parent.cx,y1:parent.cy, x2:n.cx,y2:n.cy, ring:2 })
      }
    } else {
      result.push({ id:`__icon__→${n.path}`, x1:0,y1:0, x2:n.cx,y2:n.cy, ring:1 })
    }
  }
  return result
})

// ─── 样式辅助 ─────────────────────────────────────────────────
function hexFillStyle(node:HcNode): Record<string,string> {
  if (node.ring === 2) {
    return { fill: 'color-mix(in srgb, var(--color-bg-secondary) 55%, transparent)', opacity: '0.85' }
  }
  if (node.type === 'prev' || node.type === 'next') {
    const active = node.parentPath === 'active'
    return { fill: active
      ? 'color-mix(in srgb, var(--color-accent-light) 60%, transparent)'
      : 'color-mix(in srgb, var(--color-bg-secondary) 40%, transparent)',
      opacity: active ? '1' : '0.5' }
  }
  return {}
}

// ─── 交互 ─────────────────────────────────────────────────────
const canGoBack = computed(() => navStack.value.length > 1)

function goBack() {
  if (!canGoBack.value) return
  navStack.value = navStack.value.slice(0, -1)
  const top = navStack.value[navStack.value.length - 1]
  selectedPath.value = top.node.path
  emit('select', top.node.path, top.wsPath)
}

function handleClick(node: HcNode) {
  // 翻页按钮
  if (node.type === 'prev') {
    if (pageOffset.value > 0) pageOffset.value = Math.max(0, pageOffset.value - PAGE_SIZE)
    return
  }
  if (node.type === 'next') {
    const center = navStack.value[navStack.value.length - 1]
    const total = center?.node.children?.length ?? 0
    if (pageOffset.value + PAGE_SIZE < total) pageOffset.value += PAGE_SIZE
    return
  }

  if (node.path === '__ws_root__') { navStack.value = []; return }

  // ring-2 孙节点
  if (node.ring === 2 && node.parentPath) {
    const parentFound = findNode(node.parentPath, node.wsPath)
    const selfFound   = findNode(node.path, node.wsPath)
    if (parentFound && selfFound) {
      const cur = navStack.value
      // 若 ring-1 父节点不在栈顶，先 push 父节点
      const stackTop = cur[cur.length-1]
      if (stackTop?.node.path !== node.parentPath) {
        navStack.value = [...cur, { node:parentFound, wsPath:node.wsPath }]
      }
      navStack.value = [...navStack.value, { node:selfFound, wsPath:node.wsPath }]
      pageOffset.value = 0
      selectedPath.value = node.path
      emit('select', node.path, node.wsPath)
    }
    return
  }

  // 点击 ring-1 子节点 → 进入
  const found = findNode(node.path, node.wsPath)
  if (!found) return
  navStack.value = [...navStack.value, { node:found, wsPath:node.wsPath }]
  pageOffset.value = 0
  selectedPath.value = node.path
  emit('select', node.path, node.wsPath)
}

function findNode(path:string, wsPath:string): FolderNode|null {
  const root = wsTreeMap.value.get(wsPath)
  if (!root) return null
  if (root.path===path) return root
  return searchKids(root.children, path)
}
function searchKids(nodes:FolderNode[]|undefined, path:string): FolderNode|null {
  if (!nodes) return null
  for (const n of nodes) {
    if (n.path===path) return n
    const f = searchKids(n.children, path)
    if (f) return f
  }
  return null
}

// ─── 数据 ─────────────────────────────────────────────────────
async function loadWs(ws:string) {
  try {
    const res = await folderApi.getTree(ws)
    const root: FolderNode = {
      name:lastName(ws), path:ws,
      file_count:res.root_file_count,
      children:res.folders, is_expanded:true,
    }
    wsTreeMap.value = new Map(wsTreeMap.value).set(ws, root)
  } catch(e){ console.error('HoneycombTree: failed to load', ws, e) }
}

async function loadAll() {
  const list = props.workspaces?.length ? props.workspaces : (props.rootPath?[props.rootPath]:[])
  if (!list.length) return
  loading.value = true
  navStack.value = []
  wsTreeMap.value = new Map()
  await Promise.all(list.map(ws=>loadWs(ws)))
  if (list.length===1) {
    const ws = list[0]
    const root = wsTreeMap.value.get(ws)
    if (root) {
      navStack.value = [{ node:root, wsPath:ws }]
      selectedPath.value = root.path
      emit('select', root.path, ws)
    }
  }
  loading.value = false
}

// ─── 右键菜单 ─────────────────────────────────────────────────
const ctxVisible  = ref(false)
const ctxAnchorEl = ref<HTMLElement>()
const ctxNode     = ref<HcNode|null>(null)
const showDlg     = ref(false)
const newName     = ref('')
const creating    = ref(false)

const ctxEl = (() => {
  const el = document.createElement('div')
  el.style.cssText = 'position:fixed;left:-9999px;top:-9999px;width:1px;height:1px;pointer-events:none'
  document.body.appendChild(el)
  return el
})()

function handleCtx(node:HcNode, e:MouseEvent) {
  if (node.path==='__ws_root__') return
  ctxNode.value = node
  window.dispatchEvent(new Event('close-context-menus'))
  ctxEl.style.left=`${e.clientX}px`; ctxEl.style.top=`${e.clientY}px`
  ctxAnchorEl.value = ctxEl; ctxVisible.value = true
}
function openCreateDlg() { ctxVisible.value=false; newName.value=''; showDlg.value=true }

async function confirmCreate() {
  const name = newName.value.trim()
  const node = ctxNode.value
  if (!name||!node) return
  creating.value = true
  const ws = node.wsPath
  try {
    try {
      await folderApi.createFolder(ws, node.path, name)
    } catch(err:any) {
      if (err?.response?.status!==404) throw err
      await invoke('create_folder',{ path:`${node.path.replace(/[/\\]+$/,'')}/${name}` })
    }
    showDlg.value=false
    ElMessage.success(`已创建目录：${name}`)
    await loadWs(ws)
    const cur = navStack.value[navStack.value.length-1]
    if (cur) {
      const rf = findNode(cur.node.path, cur.wsPath)
      if (rf) navStack.value=[...navStack.value.slice(0,-1),{node:rf,wsPath:cur.wsPath}]
    }
  } catch(err:any) {
    ElMessage.error(err?.response?.data?.detail||'创建目录失败')
  } finally { creating.value=false }
}

// ─── 生命周期 ─────────────────────────────────────────────────
function closeCtx() { ctxVisible.value=false }

function initPosition() {
  const el = props.boundary
  if (!el) return
  const rect = el.getBoundingClientRect()
  if (rect.width === 0 && rect.height === 0) return
  posX.value = Math.max(rect.left, rect.right - ICON_W - 16)
  posY.value = Math.max(rect.top, rect.bottom - ICON_H - 16)
  posInitialized.value = true
}

onMounted(async ()=>{
  window.addEventListener('close-context-menus',closeCtx)
  // 等待下一帧再读取 boundary 的位置，确保 DOM 已渲染
  await nextTick()
  initPosition()
})
onUnmounted(()=>{
  window.removeEventListener('close-context-menus',closeCtx)
  ctxEl.remove()
  if (leaveTimer) clearTimeout(leaveTimer)
})

watch(()=>[props.rootPath,...(props.workspaces??[])], ()=>loadAll(), { immediate:true })

// navStack 变化时重置分页（但翻页操作本身不触发，因为 navStack 不变）
watch(()=>navStack.value.length, () => { pageOffset.value = 0 })

// boundary 可能在 onMounted 之后才赋值（父组件 ref 在模板解析后才就绪），延迟补位
watch(()=>props.boundary, async (el)=>{ if (el && !posInitialized.value) { await nextTick(); initPosition() } })
</script>

<style scoped>
/* ─── 浮层根 ────────────────────────────────── */
.hc-float {
  position: fixed;
  top: 0; left: 0;
  z-index: 300;
  pointer-events: none;   /* 子元素按需开启 */
  display: flex;
  align-items: flex-start;
}

/* ─── 图标 ──────────────────────────────────── */
.hc-icon {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  pointer-events: all;
  cursor: grab;
  user-select: none;
  position: relative;
  z-index: 1;
  /* 无背景、无边框、无圆角——直接裸露六边形 */
  transition: transform 0.15s;
  filter: drop-shadow(0 3px 10px rgba(0,0,0,0.28));
}
.hc-float.expanded .hc-icon {
  transform: scale(1.06);
}
.hc-float.dragging .hc-icon {
  cursor: grabbing;
  transform: scale(1.1);
}
.hc-icon-svg { display: block; }
.hc-icon-poly {
  fill: color-mix(in srgb, var(--color-accent-light) 90%, transparent);
  stroke: var(--color-accent);
  stroke-width: 1.8;
}
.hc-icon-txt {
  font-size: 12px;
  font-weight: 700;
  fill: var(--color-accent);
  pointer-events: none;
}
/* 返回上级徽章 */
.hc-back-badge {
  position: absolute;
  top: -8px;
  right: -8px;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: var(--color-accent);
  color: #fff;
  font-size: 11px;
  line-height: 18px;
  text-align: center;
  cursor: pointer;
  pointer-events: all;
  box-shadow: 0 2px 6px rgba(0,0,0,0.25);
  transition: transform 0.12s, background 0.12s;
  z-index: 2;
}
.hc-back-badge:hover {
  transform: scale(1.18);
  background: var(--color-accent-hover, var(--color-accent));
}

/* 脉冲波纹 */
.hc-ripple {
  fill: none;
  stroke: var(--color-accent);
  stroke-width: 1.2;
  opacity: 0;
  transform-origin: 0 0;
  animation: ripple 1.6s ease-out infinite;
}
.hc-ripple.r2 { animation-delay: 0.8s; }
@keyframes ripple {
  0%   { opacity: 0.5; transform: scale(1); }
  100% { opacity: 0;   transform: scale(1.8); }
}

/* ─── 蜂巢场景 SVG ──────────────────────────── */
.hc-scene {
  position: absolute;
  pointer-events: all;
  overflow: visible;
  /* left/top 由 sceneStyle 控制，让 SVG 原点 = 图标中心 */
  transition: left 0.22s cubic-bezier(0.25, 0.46, 0.45, 0.94),
              top  0.22s cubic-bezier(0.25, 0.46, 0.45, 0.94);
}

/* ─── 连线 ──────────────────────────────────── */
.hc-edge {
  stroke: color-mix(in srgb, var(--color-accent) 30%, var(--color-border));
  stroke-width: 1.4;
  stroke-dasharray: 4 3;
  animation: edgeFadeIn 0.3s ease both;
}
.hc-edge.ring2 {
  stroke: color-mix(in srgb, var(--color-border) 50%, transparent);
  stroke-width: 0.8;
  stroke-dasharray: 3 4;
  opacity: 0.6;
}
@keyframes edgeFadeIn {
  from { opacity: 0; stroke-dashoffset: 20; }
  to   { opacity: 1; stroke-dashoffset: 0; }
}

/* ─── 节点 ──────────────────────────────────── */
.hc-node-g {
  cursor: pointer;
  animation: nodeSpawn 0.32s cubic-bezier(0.34,1.56,0.64,1) both;
}

/* ring-2 孙节点 */
.hc-node-g.is-ring2 {
  opacity: 0.82;
}
.hc-node-g.is-ring2:hover { opacity: 1; }

/* 翻页按钮 */
.hc-node-g.is-page-btn { cursor: pointer; }
.hc-node-g.is-page-inactive { cursor: default; pointer-events: none; }

@keyframes nodeSpawn {
  from { opacity: 0; transform: scale(0.4); }
  to   { opacity: 1; transform: scale(1); }
}

.hc-hex-stroke {
  fill: none;
  stroke: color-mix(in srgb, var(--color-border) 70%, transparent);
  stroke-width: 1.2;
  transition: stroke 0.18s;
}
.hc-hex-stroke.stroke-selected {
  stroke: var(--color-accent);
  stroke-width: 2;
}

.hc-hex-fill {
  fill: color-mix(in srgb, var(--color-bg-secondary) 80%, transparent);
  transition: fill 0.15s;
}
.hc-node-g:hover .hc-hex-fill {
  fill: color-mix(in srgb, var(--color-bg-hover) 88%, transparent);
}
.hc-hex-fill.fill-selected {
  fill: color-mix(in srgb, var(--color-accent-light) 85%, transparent);
}

/* 毛玻璃滤镜（SVG filter） */
.hc-scene { filter: drop-shadow(0 4px 16px rgba(0,0,0,0.22)); }

/* ─── 文字 ──────────────────────────────────── */
.hc-lbl {
  font-size: 11px;
  font-weight: 500;
  fill: var(--color-text-primary);
  pointer-events: none;
  paint-order: stroke fill;
  stroke: color-mix(in srgb, var(--color-bg-primary) 60%, transparent);
  stroke-width: 3;
  stroke-linejoin: round;
}
.hc-lbl-sm {
  font-size: 9px;
}
.hc-cnt {
  font-size: 9.5px;
  fill: var(--color-text-secondary);
  pointer-events: none;
}
.hc-dot {
  fill: var(--color-accent);
  opacity: 0.7;
}
.hc-page-arrow {
  font-size: 16px;
  fill: var(--color-accent);
  pointer-events: none;
  font-weight: 600;
}

/* ─── 加载 ──────────────────────────────────── */
.hc-loading-hint {
  position: absolute;
  top: 56px; left: 50%;
  transform: translateX(-50%);
  color: var(--color-text-secondary);
  pointer-events: none;
}
.hc-spin { animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

/* ─── 右键菜单 ──────────────────────────────── */
.context-menu { padding: 4px 0; }
.context-menu-item {
  display: flex; align-items: center; gap: 8px;
  padding: 8px 12px; cursor: pointer; font-size: 13px;
  border-radius: 6px; transition: background 0.12s;
}
.context-menu-item:hover { background: var(--color-bg-secondary); }
.create-hint { font-size: 13px; color: var(--color-text-secondary); }
</style>
