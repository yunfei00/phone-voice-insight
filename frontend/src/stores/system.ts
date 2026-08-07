import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { getCollectionTasks, getHealth, getProducts, getReviews, getSources } from '@/api'
import type { DashboardMetrics, HealthStatus } from '@/types/api'

export const useSystemStore = defineStore('system', () => {
  const health = ref<HealthStatus | null>(null)
  const metrics = ref<DashboardMetrics>({
    products: 0,
    sources: 0,
    reviews: 0,
    collectionTasks: 0,
  })
  const loading = ref(false)
  const error = ref('')
  const isHealthy = computed(() => health.value?.status === 'ok')

  async function fetchDashboardData(): Promise<void> {
    loading.value = true
    error.value = ''
    try {
      const [healthData, products, sources, reviews, tasks] = await Promise.all([
        getHealth(),
        getProducts({ page_size: 1 }),
        getSources({ page_size: 1 }),
        getReviews({ page_size: 1 }),
        getCollectionTasks({ page_size: 1 }),
      ])
      health.value = healthData
      metrics.value = {
        products: products.count,
        sources: sources.count,
        reviews: reviews.count,
        collectionTasks: tasks.count,
      }
    } catch {
      health.value = null
      error.value = '无法读取系统状态，请确认后端 API 已启动。'
    } finally {
      loading.value = false
    }
  }

  return { health, metrics, loading, error, isHealthy, fetchDashboardData }
})
