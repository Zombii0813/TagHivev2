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
      path: '/detail/:id',
      name: 'detail',
      component: () => import('../views/DetailPanel.vue'),
    },
  ],
})

export default router
