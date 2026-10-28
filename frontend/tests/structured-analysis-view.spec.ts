import ElementPlus from 'element-plus'
import { createApp, nextTick } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  getProducts,
  getStructuredAggregates,
  getStructuredAnalyses,
  getStructuredBatches,
  getStructuredQuality,
  getTaxonomy,
} from '@/api'
import StructuredAnalysisView from '@/views/StructuredAnalysisView.vue'

vi.mock('@/api', () => ({
  getStructuredAnalyses: vi.fn(),
  getStructuredAggregates: vi.fn(),
  getStructuredBatches: vi.fn(),
  getStructuredQuality: vi.fn(),
  getProducts: vi.fn(),
  getTaxonomy: vi.fn(),
  reviewStructuredAnalysis: vi.fn(),
}))

async function flush(): Promise<void> {
  await new Promise((resolve) => setTimeout(resolve, 0))
  await nextTick()
}

describe('StructuredAnalysisView', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
    vi.mocked(getTaxonomy).mockResolvedValue({ taxonomy_version: '1.0.0', name: 'V1', domains: [] })
    vi.mocked(getStructuredAnalyses).mockResolvedValue({
      count: 0,
      next: null,
      previous: null,
      results: [],
    })
    vi.mocked(getProducts).mockResolvedValue({ count: 0, next: null, previous: null, results: [] })
    vi.mocked(getStructuredQuality).mockResolvedValue({
      total_runs: 0,
      successful_runs: 0,
      success_rate: null,
      schema_valid_rate: null,
      review_required: 0,
      human_evaluation_status: 'NOT_EVALUATED',
      accuracy_metrics: null,
    })
    vi.mocked(getStructuredAggregates).mockResolvedValue({
      disclaimer: '',
      content_count: 0,
      opinion_count: 0,
      domain_distribution: [],
      topic_distribution: [],
      sentiment_distribution: [],
      severity_distribution: [],
      high_frequency_clusters: [],
    })
    vi.mocked(getStructuredBatches).mockResolvedValue({
      count: 0,
      next: null,
      previous: null,
      results: [],
    })
  })

  it('加载空状态且不会触发模型调用', async () => {
    const container = document.createElement('div')
    document.body.appendChild(container)
    const app = createApp(StructuredAnalysisView)
    app.use(ElementPlus)
    app.mount(container)
    await flush()
    await flush()
    expect(getStructuredAnalyses).toHaveBeenCalledWith(expect.objectContaining({ page_size: 10 }))
    expect(container.textContent).toContain('自动流水线将在治理通过且预算可用时运行')
    app.unmount()
  })

  it('接口失败时显示错误状态', async () => {
    vi.mocked(getStructuredAnalyses).mockRejectedValueOnce(new Error('network'))
    const container = document.createElement('div')
    document.body.appendChild(container)
    const app = createApp(StructuredAnalysisView)
    app.use(ElementPlus)
    app.mount(container)
    await flush()
    expect(container.textContent).toContain('结构化分析数据加载失败')
    app.unmount()
  })
})
