import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { getHealth } from '@/api'
import { useSystemStore } from '@/stores/system'

vi.mock('@/api', () => ({
  getHealth: vi.fn(),
  getProducts: vi.fn(),
  getSources: vi.fn(),
  getReviews: vi.fn(),
  getCollectionTasks: vi.fn(),
}))

describe('system store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('API 异常时提供明确错误状态', async () => {
    vi.mocked(getHealth).mockRejectedValue(new Error('offline'))
    const store = useSystemStore()

    await store.fetchDashboardData()

    expect(store.error).toContain('后端 API')
    expect(store.health).toBeNull()
  })
})
