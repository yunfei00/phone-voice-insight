import ElementPlus, { ElMessage } from 'element-plus'
import { createApp, nextTick } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  getProducts,
  getStructuredAggregates,
  getStructuredAnalyses,
  getStructuredBatches,
  getStructuredCorpusProgress,
  getStructuredQuality,
  getTaxonomy,
} from '@/api'
import type { StructuredAggregates } from '@/types/api'
import StructuredAnalysisView from '@/views/StructuredAnalysisView.vue'

vi.mock('@/api', () => ({
  createStructuredBatch: vi.fn(),
  getStructuredAnalyses: vi.fn(),
  getStructuredAggregates: vi.fn(),
  getStructuredBatches: vi.fn(),
  getStructuredCorpusProgress: vi.fn(),
  getStructuredQuality: vi.fn(),
  getProducts: vi.fn(),
  getTaxonomy: vi.fn(),
  reviewStructuredAnalysis: vi.fn(),
  runAllStructuredAnalysis: vi.fn(),
}))

const emptyAggregates = (opinionCount = 0): StructuredAggregates => ({
  disclaimer: '',
  content_count: opinionCount ? 1 : 0,
  opinion_count: opinionCount,
  domain_distribution: [],
  topic_distribution: [],
  sentiment_distribution: [],
  severity_distribution: [],
  high_frequency_clusters: [],
})

const products = {
  count: 2,
  next: null,
  previous: null,
  results: [
    { id: 1, name: '荣耀 Power', brand_name: '荣耀' },
    { id: 2, name: '荣耀 Power2', brand_name: '荣耀' },
  ],
}

function httpError(status: number): Error & { response: { status: number } } {
  return Object.assign(new Error(`HTTP ${status}`), { response: { status } })
}

function deferred<T>(): { promise: Promise<T>; resolve: (value: T) => void } {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((resolver) => {
    resolve = resolver
  })
  return { promise, resolve }
}

async function flush(delay = 0): Promise<void> {
  await new Promise((resolve) => setTimeout(resolve, delay))
  await nextTick()
  await Promise.resolve()
}

function mountView(): {
  app: ReturnType<typeof createApp>
  container: HTMLDivElement
  vm: { selectedProduct?: number; changeProduct: () => Promise<void> }
} {
  const container = document.createElement('div')
  document.body.appendChild(container)
  const app = createApp(StructuredAnalysisView)
  app.use(ElementPlus)
  const vm = app.mount(container) as unknown as {
    selectedProduct?: number
    changeProduct: () => Promise<void>
  }
  return { app, container, vm }
}

describe('StructuredAnalysisView', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
    vi.clearAllMocks()
    vi.mocked(getTaxonomy).mockResolvedValue({
      taxonomy_version: '1.0.0',
      name: 'V1',
      domains: [],
    })
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
    vi.mocked(getStructuredAggregates).mockResolvedValue(emptyAggregates())
    vi.mocked(getStructuredBatches).mockResolvedValue({
      count: 0,
      next: null,
      previous: null,
      results: [],
    })
    vi.mocked(getStructuredCorpusProgress).mockResolvedValue({
      total: 0,
      completed: 0,
      remaining: 0,
      active: false,
      batch: null,
    })
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  it('四个主接口全部成功并独立写入页面', async () => {
    const { app, container } = mountView()
    await flush()
    await flush()

    expect(getStructuredAnalyses).toHaveBeenCalledWith(
      expect.objectContaining({ page_size: 10 }),
      expect.objectContaining({ suppressGlobalError: true }),
    )
    expect(getStructuredQuality).toHaveBeenCalledOnce()
    expect(getStructuredAggregates).toHaveBeenCalledOnce()
    expect(getStructuredBatches).toHaveBeenCalledOnce()
    expect(container.textContent).toContain('自动流水线将在治理通过且预算可用时运行')
    app.unmount()
  })

  it('aggregates 超时不影响任务进度和结果列表且不会重复弹窗', async () => {
    vi.mocked(getProducts).mockResolvedValue(products as never)
    vi.mocked(getStructuredAggregates).mockRejectedValue(
      Object.assign(new Error('timeout'), { code: 'ECONNABORTED' }),
    )
    vi.mocked(getStructuredCorpusProgress).mockResolvedValue({
      total: 10,
      completed: 2,
      remaining: 8,
      active: true,
      batch: null,
    })
    const messageSpy = vi.spyOn(ElMessage, 'error')
    const { app, container } = mountView()
    await flush(500)

    expect(getStructuredAggregates).toHaveBeenCalledTimes(3)
    expect(getStructuredCorpusProgress).toHaveBeenCalled()
    expect(container.textContent).toContain('聚合统计加载失败，任务进度仍会继续更新')
    expect(container.textContent).toContain('有效语料 10')
    expect(container.textContent).toContain('暂无结构化分析结果')
    expect(messageSpy).not.toHaveBeenCalled()
    app.unmount()
  })

  it('quality、batches 和 taxonomy 失败不会清空聚合结果', async () => {
    vi.mocked(getStructuredQuality).mockRejectedValue(httpError(400))
    vi.mocked(getStructuredBatches).mockRejectedValue(httpError(400))
    vi.mocked(getTaxonomy).mockRejectedValue(httpError(400))
    vi.mocked(getStructuredAggregates).mockResolvedValue(emptyAggregates(7))
    const { app, container } = mountView()
    await flush(20)

    expect(container.textContent).toContain('质量统计加载失败')
    expect(container.textContent).toContain('任务列表加载失败')
    expect(container.textContent).toContain('分类体系暂时不可用')
    expect(container.textContent).toContain('明确问题/观点7')
    app.unmount()
  })

  it('任务运行期间每 5 秒刷新进度并在完成时刷新统计', async () => {
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
    vi.mocked(getProducts).mockResolvedValue(products as never)
    vi.mocked(getStructuredCorpusProgress)
      .mockResolvedValueOnce({ total: 10, completed: 2, remaining: 8, active: true, batch: null })
      .mockResolvedValueOnce({ total: 10, completed: 10, remaining: 0, active: false, batch: null })
    const { app } = mountView()
    await flush(20)
    expect(getStructuredCorpusProgress).toHaveBeenCalledTimes(1)
    expect(getStructuredAggregates).toHaveBeenCalledTimes(1)

    await vi.advanceTimersByTimeAsync(5000)
    await flush(20)

    expect(getStructuredCorpusProgress).toHaveBeenCalledTimes(2)
    expect(getStructuredAggregates).toHaveBeenCalledTimes(2)
    expect(getStructuredQuality).toHaveBeenCalledTimes(2)
    app.unmount()
  })

  it('快速切换产品时旧聚合请求不能覆盖新产品数据', async () => {
    vi.mocked(getProducts).mockResolvedValue(products as never)
    const firstProduct = deferred<StructuredAggregates>()
    vi.mocked(getStructuredAggregates).mockImplementation((params) =>
      params.product === 1 ? firstProduct.promise : Promise.resolve(emptyAggregates(9)),
    )
    const { app, container, vm } = mountView()
    await flush(20)

    vm.selectedProduct = 2
    await vm.changeProduct()
    firstProduct.resolve(emptyAggregates(1))
    await flush(20)

    expect(container.textContent).toContain('明确问题/观点9')
    expect(container.textContent).not.toContain('明确问题/观点1')
    app.unmount()
  })

  it('只创建一组刷新定时器且卸载时全部清理', async () => {
    const setIntervalSpy = vi.spyOn(globalThis, 'setInterval')
    const clearIntervalSpy = vi.spyOn(globalThis, 'clearInterval')
    const { app, vm } = mountView()
    await flush(20)
    await vm.changeProduct()

    const intervals = setIntervalSpy.mock.calls.map((call) => call[1])
    expect(intervals.filter((delay) => delay === 5000)).toHaveLength(1)
    expect(intervals.filter((delay) => delay === 60_000)).toHaveLength(1)

    app.unmount()
    expect(clearIntervalSpy).toHaveBeenCalledTimes(2)
  })

  it('页面卸载后停止进度刷新', async () => {
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
    vi.mocked(getProducts).mockResolvedValue(products as never)
    const { app } = mountView()
    await flush(20)
    expect(getStructuredCorpusProgress).toHaveBeenCalledTimes(1)

    app.unmount()
    await vi.advanceTimersByTimeAsync(15_000)

    expect(getStructuredCorpusProgress).toHaveBeenCalledTimes(1)
  })
})
