import { beforeEach, describe, expect, it, vi } from 'vitest'

import { getStructuredAggregates } from '@/api'
import apiClient from '@/api/client'

vi.mock('@/api/client', () => ({
  default: {
    get: vi.fn(),
  },
}))

describe('结构化聚合 API 客户端', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(apiClient.get).mockResolvedValue({ data: { opinion_count: 0 } })
  })

  it('仅 aggregates 请求使用 60 秒超时并支持静默模块错误', async () => {
    const controller = new AbortController()
    await getStructuredAggregates(
      { product: 2 },
      { signal: controller.signal, suppressGlobalError: true },
    )

    expect(apiClient.get).toHaveBeenCalledWith(
      '/structured-analyses/aggregates/',
      expect.objectContaining({
        params: { product: 2 },
        timeout: 60_000,
        signal: controller.signal,
        skipGlobalError: true,
      }),
    )
  })
})
