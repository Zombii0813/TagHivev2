import { createRouter, createWebHistory } from 'vue-router'
import MainLayout from '../views/MainLayout.vue'

// 路由配置
const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      component: MainLayout,
      children: [
        {
          path: '',
          name: 'browser',
          component: () => import('../views/BrowserView.vue'),
        },
      ],
    },
    {
      path: '/settings',
      name: 'settings',
      component: () => import('../views/SettingsView.vue'),
    },
    // 懒加载路由示例
    {
      path: '/detail/:id',
      name: 'detail',
      component: () => import('../views/DetailPanel.vue'),
    },
  ],
})

// 路由懒加载优化
// 添加路由守卫，实现预加载
let prefetchTimeout: ReturnType<typeof setTimeout> | null = null

router.beforeEach((to, from, next) => {
  // 清除之前的预加载定时器
  if (prefetchTimeout) {
    clearTimeout(prefetchTimeout)
  }
  
  next()
})

router.afterEach((to) => {
  // 预加载可能访问的页面
  if (to.name === 'browser') {
    // 延迟预加载设置页面
    prefetchTimeout = setTimeout(() => {
      import('../views/SettingsView.vue')
    }, 2000)
  }
})

export default router
