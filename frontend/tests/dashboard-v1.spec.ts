import ElementPlus from 'element-plus'
import { createApp, nextTick, ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  getDashboardCategories,
  getDashboardComparison,
  getDashboardIssue,
  getDashboardIssues,
  getDashboardOverview,
  getDashboardProducts,
  getDashboardTrends,
  getInsightReport,
  getInsightReports,
  getOperationsStatus,
} from '@/api'
import DashboardFilters from '@/components/DashboardFilters.vue'
import ComparisonView from '@/views/ComparisonView.vue'
import DashboardView from '@/views/DashboardView.vue'
import InsightReportsView from '@/views/InsightReportsView.vue'
import IssuesView from '@/views/IssuesView.vue'
import OperationsView from '@/views/OperationsView.vue'

const push = vi.fn()
const replace = vi.fn()
vi.mock('vue-router', () => ({
  useRoute: () => ({ query: {} }),
  useRouter: () => ({ push, replace }),
}))
vi.mock('@/components/TechChart.vue', () => ({
  default: { template: '<div class="chart-stub" />' },
}))
vi.mock('@/api', () => ({
  getProducts: vi.fn(),
  getSources: vi.fn(),
  getTaxonomy: vi.fn(),
  getDashboardOverview: vi.fn(),
  getDashboardTrends: vi.fn(),
  getDashboardCategories: vi.fn(),
  getDashboardProducts: vi.fn(),
  getDashboardComparison: vi.fn(),
  getDashboardIssues: vi.fn(),
  getDashboardIssue: vi.fn(),
  getInsightReports: vi.fn(),
  getInsightReport: vi.fn(),
  getOperationsStatus: vi.fn(),
}))

const issue = {
  id: '1:NET.CELLULAR',
  product_id: 1,
  product_name: '荣耀 Power2',
  category: 'NET',
  topic_code: 'NET.CELLULAR',
  name: '蜂窝信号',
  feedback_count: 8,
  recent_count: 5,
  previous_count: 2,
  growth_rate: 150,
  is_new: false,
  severity: 'HIGH',
  first_seen: '2026-10-01T00:00:00Z',
  last_seen: '2026-10-28T00:00:00Z',
}
const overview = {
  filters: { start_date: '2026-10-01', end_date: '2026-10-29' },
  raw_feedback: 100,
  valid_feedback: 80,
  ai_analyzed: 50,
  explicit_issue_feedback: 20,
  watch_issue_count: 1,
  latest_data_at: '2026-10-29T01:00:00Z',
  published_time_fallback_count: 3,
  disclaimer: '不等于故障率',
  watchlist: [issue],
}
const product = {
  id: 1,
  brand: { id: 1, name: '荣耀', code: 'HONOR', is_active: true },
  name: '荣耀 Power2',
  normalized_name: 'HONOR_POWER2',
  series: 'Power',
  model_code: '',
  release_date: null,
  description: '',
  is_active: true,
  variants: [],
}

async function flush(): Promise<void> {
  await new Promise((resolve) => setTimeout(resolve, 0))
  await nextTick()
  await new Promise((resolve) => setTimeout(resolve, 0))
}
function mount(component: Parameters<typeof createApp>[0]): {
  app: ReturnType<typeof createApp>
  container: HTMLDivElement
} {
  const container = document.createElement('div')
  document.body.appendChild(container)
  const app = createApp(component)
  app.use(ElementPlus)
  app.mount(container)
  return { app, container }
}

describe('V1 Dashboard pages', () => {
  beforeEach(async () => {
    document.body.innerHTML = ''
    push.mockReset()
    replace.mockReset()
    const api = await import('@/api')
    vi.mocked(api.getProducts).mockResolvedValue({
      count: 2,
      next: null,
      previous: null,
      results: [product, { ...product, id: 2, name: '荣耀 Power' }],
    })
    vi.mocked(api.getSources).mockResolvedValue({
      count: 0,
      next: null,
      previous: null,
      results: [],
    })
    vi.mocked(api.getTaxonomy).mockResolvedValue({
      taxonomy_version: '1.0.0',
      name: 'V1',
      domains: [],
    })
    vi.mocked(getDashboardOverview).mockResolvedValue(overview)
    vi.mocked(getDashboardTrends).mockResolvedValue([
      { date: '2026-10-29', valid_feedback: 5, explicit_issues: 2 },
    ])
    vi.mocked(getDashboardCategories).mockResolvedValue([
      { code: 'NET', name: '通信连接', feedback_count: 8, analyzed_denominator: 50, ratio: 0.16 },
    ])
    vi.mocked(getDashboardProducts).mockResolvedValue([
      {
        product_id: 1,
        product_name: '荣耀 Power2',
        valid_feedback: 80,
        ai_analyzed: 50,
        explicit_issue_feedback: 20,
        top_issue: '蜂窝信号',
        latest_data_at: '2026-10-29T01:00:00Z',
      },
    ])
    vi.mocked(getDashboardIssues).mockResolvedValue({
      count: 1,
      next: null,
      previous: null,
      results: [issue],
    })
    vi.mocked(getDashboardIssue).mockResolvedValue({
      ...issue,
      summary: '信号问题',
      trend: [],
      evidence: [
        {
          id: 1,
          analysis__content_id: 9,
          analysis__content__title: '体验',
          analysis__content__content: '地下车库信号不稳定',
          analysis__content__source_url: 'https://example.com',
          analysis__content__published_at: '2026-10-28T00:00:00Z',
          analysis__content__collected_at: '2026-10-28T00:00:00Z',
          analysis__summary: '信号问题',
          evidence_text: '信号不稳定',
          confidence: '0.95',
          severity: 'HIGH',
        },
      ],
    })
    const comparison = {
      left: {
        ...overview,
        product_id: 1,
        product_name: '荣耀 Power2',
        negative_ratio: 0.4,
        ratio_denominator: 50,
        sample_sufficient: true,
        top_issues: [issue],
      },
      right: {
        ...overview,
        product_id: 2,
        product_name: '荣耀 Power',
        negative_ratio: 0.2,
        ratio_denominator: 50,
        sample_sufficient: true,
        top_issues: [],
      },
      minimum_sample: 30,
      reliable: true,
      reliability_message: null,
      categories: [],
    }
    vi.mocked(getDashboardComparison).mockResolvedValue(comparison)
    const report = {
      id: 1,
      report_type: 'DAILY' as const,
      title: '每日摘要',
      product_id: 1,
      product_name: '荣耀 Power2',
      source_id: null,
      source_name: '全部来源',
      period_start: '2026-10-28T00:00:00Z',
      period_end: '2026-10-29T00:00:00Z',
      generated_at: '2026-10-29T01:00:00Z',
      data_cutoff: '2026-10-29T00:00:00Z',
      status: 'READY' as const,
      error_message: '',
      snapshot: {
        overview,
        top_issues: [issue],
        watchlist: [issue],
        coverage: {},
        data_insufficient: false,
        disclaimer: '不等于故障率',
      },
    }
    vi.mocked(getInsightReports).mockResolvedValue({
      count: 1,
      next: null,
      previous: null,
      results: [report],
    })
    vi.mocked(getInsightReport).mockResolvedValue(report)
    vi.mocked(getOperationsStatus).mockResolvedValue({
      role_scope: 'full',
      business_status: {
        collection: 'idle',
        data_update: 'normal',
        ai_automation: 'disabled',
        ai_message: '自动分析未启用',
      },
      system: {
        backend: 'online',
        database: 'online',
        redis: 'online',
        celery_worker: 'online',
        celery_beat: 'online',
      },
      latest: { collection_at: null, analysis_at: null },
      ai: { today_tokens: 100, daily_budget: 1000, budget_ratio: 0.1, budget_exhausted: false },
      collection: { running: 0 },
      governance: { uncertain: 2 },
      analysis: { successful: 1 },
    })
  })

  it('驾驶舱加载真实指标并提供下钻与全屏入口', async () => {
    const { app, container } = mount(DashboardView)
    await flush()
    expect(container.textContent).toContain('手机用户声音智能驾驶舱')
    expect(container.textContent).toContain('100')
    expect(getDashboardOverview).toHaveBeenCalled()
    expect(container.textContent).toContain('全屏投屏')
    app.unmount()
  })
  it('驾驶舱 API 失败显示错误而不伪装成功', async () => {
    vi.mocked(getDashboardOverview).mockRejectedValue(new Error('network'))
    const { app, container } = mount(DashboardView)
    await flush()
    expect(container.textContent).toContain('network')
    app.unmount()
  })
  it('产品对比使用统一 API 与分析分母', async () => {
    const { app, container } = mount(ComparisonView)
    await flush()
    expect(getDashboardComparison).toHaveBeenCalled()
    expect(container.textContent).toContain('分母 50')
    expect(
      container.querySelectorAll('.compare-filters .dashboard-filters .el-select'),
    ).toHaveLength(2)
    expect(replace).toHaveBeenCalledWith(
      expect.objectContaining({
        query: expect.objectContaining({ left_product_id: 2, right_product_id: 1 }),
      }),
    )
    app.unmount()
  })
  it('URL 自定义日期在筛选器中显示为自定义而非最近 30 天', async () => {
    const wrapper = {
      components: { DashboardFilters },
      setup: () => ({
        filters: ref({ start_date: '2026-01-01', end_date: '2026-10-29' }),
      }),
      template: '<DashboardFilters v-model="filters" />',
    }
    const { app, container } = mount(wrapper)
    await flush()
    expect(container.textContent).toContain('自定义')
    expect(container.querySelector('.el-date-editor')).not.toBeNull()
    app.unmount()
  })
  it('问题列表加载且按需请求证据详情', async () => {
    const { app, container } = mount(IssuesView)
    await flush()
    expect(container.textContent).toContain('蜂窝信号')
    const button = Array.from(container.querySelectorAll('button')).find((item) =>
      item.textContent?.includes('查看证据'),
    )
    button?.click()
    await flush()
    expect(getDashboardIssue).toHaveBeenCalledWith(issue.id, expect.any(Object))
    expect(container.textContent).toContain('信号不稳定')
    app.unmount()
  })
  it('报告列表与确定性报告详情可读取', async () => {
    const { app, container } = mount(InsightReportsView)
    await flush()
    expect(getInsightReports).toHaveBeenCalled()
    expect(getInsightReport).toHaveBeenCalledWith(1)
    expect(container.textContent).toContain('TOP 3 问题')
    app.unmount()
  })
  it('运行监控明确显示自动分析未启用且不含密钥', async () => {
    const { app, container } = mount(OperationsView)
    await flush()
    expect(container.textContent).toContain('自动分析未启用')
    expect(container.textContent).toContain('结构化成功')
    expect(container.textContent).not.toContain('running_batches')
    expect(container.textContent?.toLowerCase()).not.toContain('api_key')
    app.unmount()
  })
})
