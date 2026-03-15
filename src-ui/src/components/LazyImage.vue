<template>
  <div
    ref="containerRef"
    class="lazy-image"
    :class="{
      'is-loading': !loaded && !error,
      'is-loaded': loaded,
      'is-error': error,
    }"
    :style="containerStyle"
  >
    <!-- 占位符/模糊图 -->
    <div v-if="!loaded && !error" class="lazy-image__placeholder">
      <slot name="placeholder">
        <div class="lazy-image__skeleton" />
      </slot>
    </div>
    
    <!-- 错误状态 -->
    <div v-if="error" class="lazy-image__error">
      <slot name="error">
        <el-icon :size="32"><Picture /></el-icon>
      </slot>
    </div>
    
    <!-- 实际图片 -->
    <img
      v-if="shouldLoad"
      :src="src"
      :alt="alt"
      :style="imageStyle"
      @load="handleLoad"
      @error="handleError"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { Picture } from '@element-plus/icons-vue'

interface Props {
  src: string
  alt?: string
  width?: number | string
  height?: number | string
  objectFit?: 'contain' | 'cover' | 'fill' | 'none' | 'scale-down'
  threshold?: number
  rootMargin?: string
  blurhash?: string
}

const props = withDefaults(defineProps<Props>(), {
  alt: '',
  objectFit: 'cover',
  threshold: 0.1,
  rootMargin: '50px',
})

const emit = defineEmits<{
  load: []
  error: [Error]
}>()

const containerRef = ref<HTMLElement | null>(null)
const loaded = ref(false)
const error = ref(false)
const shouldLoad = ref(false)
const isInViewport = ref(false)

// Intersection Observer 实例
let observer: IntersectionObserver | null = null

// 容器样式
const containerStyle = computed(() => ({
  width: props.width ? (typeof props.width === 'number' ? `${props.width}px` : props.width) : '100%',
  height: props.height ? (typeof props.height === 'number' ? `${props.height}px` : props.height) : '100%',
}))

// 图片样式
const imageStyle = computed(() => ({
  width: '100%',
  height: '100%',
  objectFit: props.objectFit,
  opacity: loaded.value ? 1 : 0,
  transition: 'opacity 0.3s ease',
}))

// 处理图片加载完成
function handleLoad() {
  loaded.value = true
  error.value = false
  emit('load')
}

// 处理图片加载错误
function handleError() {
  error.value = true
  loaded.value = false
  emit('error', new Error('Failed to load image'))
}

// 设置 Intersection Observer
function setupObserver() {
  if (!containerRef.value || !window.IntersectionObserver) {
    // 如果不支持 Intersection Observer，直接加载
    shouldLoad.value = true
    return
  }

  observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          isInViewport.value = true
          shouldLoad.value = true
          // 加载后停止观察
          observer?.unobserve(entry.target)
        }
      })
    },
    {
      threshold: props.threshold,
      rootMargin: props.rootMargin,
    }
  )

  observer.observe(containerRef.value)
}

// 清理 Observer
function cleanupObserver() {
  if (observer) {
    observer.disconnect()
    observer = null
  }
}

// 监听 src 变化
watch(() => props.src, (newSrc, oldSrc) => {
  if (newSrc !== oldSrc) {
    loaded.value = false
    error.value = false
    // 如果已经在视口中，直接加载新图片
    if (isInViewport.value) {
      shouldLoad.value = true
    }
  }
})

onMounted(() => {
  setupObserver()
})

onUnmounted(() => {
  cleanupObserver()
})

// 暴露方法
defineExpose({
  reload: () => {
    loaded.value = false
    error.value = false
    shouldLoad.value = true
  },
})
</script>

<style scoped>
.lazy-image {
  position: relative;
  overflow: hidden;
  background: var(--color-bg-secondary);
}

.lazy-image__placeholder,
.lazy-image__error {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}

.lazy-image__skeleton {
  width: 100%;
  height: 100%;
  background: linear-gradient(
    90deg,
    var(--color-bg-secondary) 25%,
    var(--color-bg-tertiary) 50%,
    var(--color-bg-secondary) 75%
  );
  background-size: 200% 100%;
  animation: shimmer 1.5s infinite;
}

@keyframes shimmer {
  0% {
    background-position: 200% 0;
  }
  100% {
    background-position: -200% 0;
  }
}

.lazy-image__error {
  color: var(--color-text-tertiary);
}

.lazy-image img {
  display: block;
}
</style>
