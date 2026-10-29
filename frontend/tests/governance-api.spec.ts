import { beforeEach, describe, expect, it, vi } from 'vitest'

import { startFullGovernance } from '@/api'
import apiClient from '@/api/client'

vi.mock('@/api/client', () => ({
  default: {
    post: vi.fn(),
  },
}))

describe('一键全量治理 API', () => {
  beforeEach(() => {
    vi.mocked(apiClient.post)
      .mockReset()
      .mockResolvedValue({
        data: { task: { id: 12, total: 3 } },
      })
  })

  it.each([
    [{ product_id: 1 }],
    [{ product_id: 1, source_id: null }],
    [{ product_id: 1, source_id: 2 }],
  ])('按原样提交可选来源参数 %#', async (payload) => {
    await startFullGovernance(payload)

    expect(apiClient.post).toHaveBeenCalledWith('/review-quality/start-full/', payload)
  })
})
