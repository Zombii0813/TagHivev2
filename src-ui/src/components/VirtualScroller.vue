<template>
  <div ref="containerRef" class="virtual-scroller" :style="containerStyle">
    <div class="virtual-scroller__wrapper" :style="wrapperStyle">
      <div
        v-for="item in visibleItems"
        :key="item.key"
        class="virtual-scroller__item"
        :style="getItemStyle(item)"
      >
        <slot :item="item.data" :index="item.index" />
      </div>
    </div>
    <!-- 占位符，用于撑开滚动区域 -->
    <div class="virtual-scroller__spacer" :style="spacerStyle" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'

interface Props {
  items: any[]
  itemHeight: number
  bufferSize?: number
  keyField?: string
  scrollToIndex?: number
}

const props = withDefaults(defineProps<Props>(), {
  bufferSize: 5,
  keyField: 'id',
})

const containerRef = ref<HTMLElement | null>(null)
const scrollTop = ref(0)
const containerHeight = ref(0)

// 计算可见区域的起始和结束索引
const visibleRange = computed(() => {
  const startIdx = Math.floor(scrollTop.value / props.itemHeight)
  const visibleCount = Math.ceil(containerHeight.value / props.itemHeight)
  
  // 添加缓冲区
  const start = Math.max(0, startIdx - props.bufferSize)
  const end = Math.min(
    props.items.length,
    startIdx + visibleCount + props.bufferSize
  )
  
  return { start, end }
})

// 可见项目
const visibleItems = computed(() => {
  const { start, end } = visibleRange.value
  return props.items.slice(start, end).map((item, idx) => ({
    data: item,
    index: start + idx,
    key: item[props.keyField] ?? start + idx,
    offset: (start + idx) * props.itemHeight,
  }))
})

// 容器样式
const containerStyle = computed(() => ({
  position: 'relative' as const,
  overflow: 'auto' as const,
  height: '100%',
}))

// 包装器样式
const wrapperStyle = computed(() => ({
  position: 'absolute' as const,
  top: 0,
  left: 0,
  right: 0,
  willChange: 'transform',
  transform: `translateY(${visibleRange.value.start * props.itemHeight}px)`,
}))

// 占位符样式（撑开滚动区域）
const spacerStyle = computed(() => ({
  height: `${props.items.length * props.itemHeight}px`,
  pointerEvents: 'none' as const,
}))

// 获取项目样式
function getItemStyle(item: { offset: number }) {
  return {
    height: `${props.itemHeight}px`,
  }
}

// 处理滚动事件
function handleScroll() {
  if (containerRef.value) {
    scrollTop.value = containerRef.value.scrollTop
  }
}

// 更新容器高度
function updateContainerHeight() {
  if (containerRef.value) {
    containerHeight.value = containerRef.value.clientHeight
  }
}

// 滚动到指定索引
function scrollToIndex(index: number) {
  if (containerRef.value && index >= 0 && index < props.items.length) {
    containerRef.value.scrollTop = index * props.itemHeight
  }
}

// 监听 scrollToIndex 变化
watch(() => props.scrollToIndex, (newIndex) => {
  if (newIndex !== undefined) {
    nextTick(() => scrollToIndex(newIndex))
  }
})

// ResizeObserver 实例
let resizeObserver: ResizeObserver | null = null

onMounted(() => {
  updateContainerHeight()
  
  if (containerRef.value) {
    containerRef.value.addEventListener('scroll', handleScroll)
    
    // 使用 ResizeObserver 监听容器大小变化
    if (typeof ResizeObserver !== 'undefined') {
      resizeObserver = new ResizeObserver(() => {
        updateContainerHeight()
      })
      resizeObserver.observe(containerRef.value)
    }
  }
  
  // 监听窗口大小变化
  window.addEventListener('resize', updateContainerHeight)
})

onUnmounted(() => {
  if (containerRef.value) {
    containerRef.value.removeEventListener('scroll', handleScroll)
  }
  
  if (resizeObserver) {
    resizeObserver.disconnect()
    resizeObserver = null
  }
  
  window.removeEventListener('resize', updateContainerHeight)
})

// 暴露方法
defineExpose({
  scrollToIndex,
  getScrollTop: () => scrollTop.value,
  getVisibleRange: () => visibleRange.value,
})
</script>

<style scoped>
.virtual-scroller {
  position: relative;
  overflow: auto;
  -webkit-overflow-scrolling: touch;
}

.virtual-scroller__wrapper {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
}

.virtual-scroller__item {
  box-sizing: border-box;
}

.virtual-scroller__spacer {
  width: 100%;
}
</style>
