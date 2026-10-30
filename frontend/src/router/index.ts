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
        meta: { title: '智能驾驶舱' },
      },
      {
        path: 'ai-assistant',
        name: 'ai-assistant',
        component: () => import('@/views/AIAssistantView.vue'),
        meta: { title: 'AI 智能助手' },
      },
      {
        path: 'comparison',
        name: 'comparison',
        component: () => import('@/views/ComparisonView.vue'),
        meta: { title: '产品对比中心' },
      },
      {
        path: 'issues',
        name: 'issues',
        component: () => import('@/views/IssuesView.vue'),
        meta: { title: '用户问题洞察' },
      },
      {
        path: 'insight-reports',
        name: 'insight-reports',
        component: () => import('@/views/InsightReportsView.vue'),
        meta: { title: 'AI 洞察报告' },
      },
      {
        path: 'operations',
        redirect: '/system',
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
        path: 'threads',
        name: 'threads',
        component: () => import('@/views/ThreadsView.vue'),
        meta: { title: '帖子视图' },
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
        path: 'structured-analysis',
        name: 'structured-analysis',
        component: () => import('@/views/StructuredAnalysisView.vue'),
        meta: { title: 'AI 结构化分析' },
      },
      {
        path: 'ai-tasks',
        name: 'ai-tasks',
        component: () => import('@/views/AITasksView.vue'),
        meta: { title: 'AI 任务中心', writeOnly: true },
      },
      {
        path: 'ai-settings',
        name: 'ai-settings',
        component: () => import('@/views/AISettingsView.vue'),
        meta: { title: 'AI 配置', adminOnly: true },
      },
      {
        path: 'system',
        name: 'system',
        component: () => import('@/views/SystemView.vue'),
        meta: { title: '运行监控', writeOnly: true },
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
  if (to.meta.writeOnly && !auth.canWrite) return '/dashboard'
  return true
})

router.afterEach((to) => {
  document.title = `${String(to.meta.title || 'PVI')} - Phone Voice Insight`
})

export default router
