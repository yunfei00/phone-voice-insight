import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

import MainLayout from '@/layouts/MainLayout.vue'
import { useAuthStore } from '@/stores/auth'
import { pinia } from '@/stores/pinia'

export const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'login',
    component: () => import('@/views/LoginView.vue'),
    meta: { title: '登录', public: true },
  },
  {
    path: '/',
    component: MainLayout,
    redirect: '/dashboard',
    children: [
      {
        path: 'users',
        name: 'users',
        component: () => import('@/views/UsersView.vue'),
        meta: { title: '用户管理', adminOnly: true },
      },
      {
        path: 'dashboard',
        name: 'dashboard',
        component: () => import('@/views/DashboardView.vue'),
        meta: { title: '数据总览' },
      },
      {
        path: 'products',
        name: 'products',
        component: () => import('@/views/ProductsView.vue'),
        meta: { title: '手机产品' },
      },
      {
        path: 'collection-tasks',
        name: 'collection-tasks',
        component: () => import('@/views/CollectionTasksView.vue'),
        meta: { title: '采集任务' },
      },
      {
        path: 'reviews',
        name: 'reviews',
        component: () => import('@/views/ReviewsView.vue'),
        meta: { title: '原始反馈' },
      },
      {
        path: 'data-quality',
        name: 'data-quality',
        component: () => import('@/views/DataQualityView.vue'),
        meta: { title: '数据质量' },
      },
      {
        path: 'analysis',
        name: 'analysis',
        component: () => import('@/views/AnalysisView.vue'),
        meta: { title: 'AI 分析' },
      },
      {
        path: 'ai-settings',
        name: 'ai-settings',
        component: () => import('@/views/AISettingsView.vue'),
        meta: { title: 'AI 配置' },
      },
      {
        path: 'system',
        name: 'system',
        component: () => import('@/views/SystemView.vue'),
        meta: { title: '系统状态' },
      },
    ],
  },
  { path: '/:pathMatch(.*)*', redirect: '/dashboard' },
]

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes,
})

router.beforeEach(async (to) => {
  const auth = useAuthStore(pinia)
  await auth.initialize()
  if (to.meta.public) return auth.isAuthenticated ? '/dashboard' : true
  if (!auth.isAuthenticated) return { name: 'login', query: { redirect: to.fullPath } }
  if (to.meta.adminOnly && !auth.isAdmin) return '/dashboard'
  return true
})

router.afterEach((to) => {
  document.title = `${String(to.meta.title || 'PVI')} - Phone Voice Insight`
})

export default router
