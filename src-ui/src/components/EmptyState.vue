<template>
  <div class="empty-state" :class="{ animated: animate }">
    <div class="empty-state__illustration">
      <div class="floating-shapes">
        <div class="shape shape-1"></div>
        <div class="shape shape-2"></div>
        <div class="shape shape-3"></div>
      </div>
      <div class="icon-container">
        <el-icon :size="64" class="main-icon">
          <component :is="icon" />
        </el-icon>
      </div>
    </div>
    
    <h3 class="empty-state__title">{{ title }}</h3>
    <p class="empty-state__description">{{ description }}</p>
    
    <div class="empty-state__actions">
      <slot name="actions">
        <el-button 
          v-if="actionText" 
          type="primary" 
          size="large"
          @click="$emit('action')"
          class="action-button"
        >
          {{ actionText }}
        </el-button>
      </slot>
    </div>
    
    <div v-if="hint" class="empty-state__hint">
      <el-icon><InfoFilled /></el-icon>
      <span>{{ hint }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { InfoFilled, FolderOpened, Search, Box } from '@element-plus/icons-vue'

interface Props {
  icon?: 'folder' | 'search' | 'box' | string
  title: string
  description: string
  actionText?: string
  hint?: string
  animate?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  icon: 'box',
  animate: true,
})

defineEmits<{
  action: []
}>()

// 图标映射
const iconMap: Record<string, any> = {
  folder: FolderOpened,
  search: Search,
  box: Box,
}

const icon = computed(() => {
  return iconMap[props.icon] || Box
})
</script>

<style scoped>
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 48px 24px;
  text-align: center;
  min-height: 400px;
}

.empty-state__illustration {
  position: relative;
  width: 160px;
  height: 160px;
  margin-bottom: 32px;
}

.floating-shapes {
  position: absolute;
  inset: 0;
}

.shape {
  position: absolute;
  border-radius: 50%;
  opacity: 0.6;
  filter: blur(40px);
}

.shape-1 {
  width: 100px;
  height: 100px;
  background: linear-gradient(135deg, var(--color-accent) 0%, var(--color-accent-hover) 100%);
  top: 10%;
  left: 10%;
  animation: float 6s ease-in-out infinite;
}

.shape-2 {
  width: 80px;
  height: 80px;
  background: linear-gradient(135deg, var(--color-success) 0%, var(--color-accent) 100%);
  top: 40%;
  right: 10%;
  animation: float 8s ease-in-out infinite 1s;
}

.shape-3 {
  width: 60px;
  height: 60px;
  background: linear-gradient(135deg, var(--color-warning) 0%, var(--color-success) 100%);
  bottom: 10%;
  left: 30%;
  animation: float 7s ease-in-out infinite 2s;
}

@keyframes float {
  0%, 100% {
    transform: translateY(0) scale(1);
  }
  50% {
    transform: translateY(-20px) scale(1.1);
  }
}

.icon-container {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1;
}

.main-icon {
  color: var(--color-accent);
  filter: drop-shadow(0 4px 12px rgba(99, 102, 241, 0.3));
  animation: pulse-icon 3s ease-in-out infinite;
}

@keyframes pulse-icon {
  0%, 100% {
    transform: scale(1);
    opacity: 1;
  }
  50% {
    transform: scale(1.1);
    opacity: 0.8;
  }
}

.empty-state__title {
  font-size: 24px;
  font-weight: 700;
  color: var(--color-text-primary);
  margin: 0 0 12px 0;
  letter-spacing: -0.5px;
}

.empty-state__description {
  font-size: 15px;
  color: var(--color-text-secondary);
  margin: 0 0 24px 0;
  max-width: 400px;
  line-height: 1.6;
}

.empty-state__actions {
  margin-bottom: 16px;
}

.action-button {
  background: linear-gradient(135deg, var(--color-accent) 0%, var(--color-accent-hover) 100%);
  border: none;
  padding: 12px 32px;
  font-size: 15px;
  font-weight: 600;
  border-radius: var(--radius-md);
  box-shadow: 0 4px 14px rgba(99, 102, 241, 0.4);
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.action-button:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 20px rgba(99, 102, 241, 0.5);
}

.empty-state__hint {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 20px;
  background: var(--glass-bg);
  backdrop-filter: var(--glass-blur);
  -webkit-backdrop-filter: var(--glass-blur);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-md);
  font-size: 13px;
  color: var(--color-text-tertiary);
}

.empty-state__hint .el-icon {
  color: var(--color-accent);
}

/* 入场动画 */
.empty-state.animated {
  animation: fadeInUp 0.6s ease-out;
}

@keyframes fadeInUp {
  from {
    opacity: 0;
    transform: translateY(30px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

/* 响应式 */
@media (max-width: 768px) {
  .empty-state {
    padding: 32px 16px;
    min-height: 300px;
  }
  
  .empty-state__illustration {
    width: 120px;
    height: 120px;
    margin-bottom: 24px;
  }
  
  .shape-1 {
    width: 70px;
    height: 70px;
  }
  
  .shape-2 {
    width: 55px;
    height: 55px;
  }
  
  .shape-3 {
    width: 40px;
    height: 40px;
  }
  
  .empty-state__title {
    font-size: 20px;
  }
  
  .empty-state__description {
    font-size: 14px;
  }
}
</style>
