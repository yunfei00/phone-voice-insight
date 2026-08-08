import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { getDataQualitySummary, getHealth, getReviews, getSources } from '@/api'
import type { DashboardMetrics, DataSource, HealthStatus } from '@/types/api'

export const useSystemStore = defineStore('system', () => {
  const health = ref<HealthStatus | null>(null)
  const metrics = ref<DashboardMetrics>({
    threads: 0,
    replies: 0,
    rawRecords: 0,
    eligibleCorpus: 0,
    excludedRecords: 0,
    latestCollection: null,
  })
  const sources = ref<DataSource[]>([])
  const loading = ref(false)
  const error = ref('')
  const isHealthy = computed(() => health.value?.status === 'ok')

  async function fetchDashboardData(): Promise<void> {
    loading.value = true
    error.value = ''
    try {
      const [healthData, sourcePage, threads, replies, officialReplies, reviews, latest, quality] =
        await Promise.all([
          getHealth(),
          getSources({ page_size: 100 }),
          getReviews({ page_size: 1, record_type: 'THREAD' }),
          getReviews({ page_size: 1, record_type: 'REPLY' }),
          getReviews({ page_size: 1, record_type: 'OFFICIAL_REPLY' }),
          getReviews({ page_size: 1 }),
          getReviews({ page_size: 1, ordering: '-collected_at' }),
          getDataQualitySummary(),
        ])
      health.value = healthData
      sources.value = sourcePage.results
      metrics.value = {
        threads: threads.count,
        replies: replies.count + officialReplies.count,
        rawRecords: reviews.count,
        eligibleCorpus: quality.eligible,
        excludedRecords: quality.excluded,
        latestCollection: latest.results[0]?.collected_at || null,
      }
    } catch {
      health.value = null
      error.value = '无法读取系统状态，请确认后端 API 已启动。'
    } finally {
      loading.value = false
    }
  }

  return { health, metrics, sources, loading, error, isHealthy, fetchDashboardData }
})
