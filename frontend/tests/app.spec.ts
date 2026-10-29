import { setActivePinia } from 'pinia'
import ElementPlus from 'element-plus'
import { createApp, nextTick } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import App from '@/App.vue'
import router from '@/router'
import { useAuthStore } from '@/stores/auth'
import { pinia } from '@/stores/pinia'

vi.mock('@/api', () => ({
  getHealth: vi.fn().mockResolvedValue({
    status: 'ok',
    service: 'phone-voice-insight-backend',
    database: 'ok',
    redis: 'ok',
  }),
  getProducts: vi.fn().mockResolvedValue({ count: 1, results: [] }),
  getSources: vi.fn().mockResolvedValue({ count: 2, results: [] }),
  getDashboardOverview: vi.fn().mockResolvedValue({
    raw_feedback: 0,
    valid_feedback: 0,
    ai_analyzed: 0,
    explicit_issue_feedback: 0,
    watch_issue_count: 0,
    latest_data_at: null,
    published_time_fallback_count: 0,
    disclaimer: '',
    watchlist: [],
  }),
  getDashboardTrends: vi.fn().mockResolvedValue([]),
  getDashboardCategories: vi.fn().mockResolvedValue([]),
  getDashboardProducts: vi.fn().mockResolvedValue([]),
  getReviews: vi.fn().mockResolvedValue({ count: 0, results: [] }),
  getReviewFacets: vi.fn().mockResolvedValue({ variants: [], regions: [], ratings: [] }),
  getReviewMetadataCompleteness: vi.fn().mockResolvedValue({
    summary: {
      total: 100,
      published_at_count: 98,
      published_at_rate: 0.98,
      ip_location_count: 75,
      ip_location_rate: 0.75,
      profile_region_count: 0,
      profile_region_rate: 0,
    },
    by_product: [],
    by_record_type: [],
    failure_reasons: {
      published_at: { source_time_missing: 2 },
      ip_location: { source_ip_location_missing: 25 },
      profile_region: { profile_region_not_publicly_labeled: 100 },
    },
  }),
  getThreadTrees: vi.fn().mockResolvedValue({
    count: 0,
    next: null,
    previous: null,
    total_threads: 0,
    matched_reply_count: 0,
    results: [],
  }),
  getCollectionTasks: vi.fn().mockResolvedValue({ count: 0, results: [] }),
  getAnalysisSummary: vi.fn().mockResolvedValue({
    eligible_corpus: 98,
    analyzed_reviews: 20,
    success: 18,
    failed: 2,
    pending: 0,
    average_confidence: 0.9,
    schema_failures: 0,
    evidence_failures: 0,
    evaluated: 0,
    evaluation_accuracy: {
      aspect: null,
      sentiment: null,
      issue: null,
      scenario: null,
      evidence: null,
      context: null,
    },
  }),
  getAIConfiguration: vi.fn().mockResolvedValue({
    provider: 'openai_compatible',
    model: 'deepseek-chat',
    prompt_version: 'review_analysis_v3',
    configured: true,
    concurrency: 2,
  }),
  getAnalysisBatches: vi.fn().mockResolvedValue([]),
  getAnalysisResults: vi.fn().mockResolvedValue({ count: 0, results: [] }),
  getSamplePreview: vi.fn().mockResolvedValue({
    sample_version: 'phase5-poc-v2',
    count: 20,
    ai_status: 'NOT_RUN',
    items: [],
  }),
  getDataQualitySummary: vi.fn().mockResolvedValue({
    total: 0,
    eligible: 0,
    excluded: 0,
    eligibility_rate: 0,
    categories: {
      official: 0,
      low_information: 0,
      promotional: 0,
      noise: 0,
      duplicate: 0,
      product_not_matched: 0,
      empty: 0,
    },
    exclusion_reasons: {},
  }),
  getCurrentUser: vi.fn(),
  login: vi.fn(),
  logout: vi.fn(),
  changePassword: vi.fn(),
}))

const expectedNavigationLabels = [
  '智能驾驶舱',
  '产品对比中心',
  '用户问题洞察',
  'AI洞察报告',
  '数据运行监控',
  '手机产品',
  '帖子视图',
  '原始数据',
  '数据质量',
  'AI结构化分析',
]
const advancedNavigationLabels = [
  ...expectedNavigationLabels,
  'AI质量中心',
  'AI任务中心',
  '历史AI分析',
  'AI配置',
  '系统状态',
]

async function mountApp(path = '/dashboard', role: 'ADMIN' | 'ANALYST' | 'VIEWER' = 'VIEWER') {
  const container = document.createElement('div')
  document.body.appendChild(container)
  const app = createApp(App)
  app.use(pinia)
  app.use(router)
  app.use(ElementPlus)
  const auth = useAuthStore(pinia)
  auth.token = 'test-token'
  auth.user = {
    id: 1,
    username: 'test-user',
    email: '',
    first_name: '',
    last_name: '',
    role,
    is_active: true,
    last_login: null,
    date_joined: '2026-01-01T00:00:00Z',
  }
  auth.initialized = true
  await router.push(path)
  await router.isReady()
  app.mount(container)
  await new Promise((resolve) => setTimeout(resolve, 0))
  await nextTick()
  return { app, container }
}

describe('App', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
    window.localStorage.clear()
    Object.defineProperty(window, 'innerWidth', { configurable: true, value: 1440 })
    setActivePinia(pinia)
  })

  it('桌面默认展开且只显示一组菜单', async () => {
    const { app, container } = await mountApp()

    expect(container.textContent).toContain('Phone Voice Insight')
    expect(container.textContent).toContain('智能驾驶舱')
    expect(container.textContent).toContain('数据状态正常')
    const navigationLabels = Array.from(container.querySelectorAll('.nav-menu .el-menu-item')).map(
      (item) => item.textContent?.trim(),
    )
    expect(navigationLabels).toEqual(expectedNavigationLabels)
    expect(new Set(navigationLabels).size).toBe(10)
    expect(container.querySelector('.el-menu--collapse')).toBeNull()
    expect(container.querySelector('.brand-copy')).not.toBeNull()

    app.unmount()
  })

  it('折叠后启用 ElMenu collapse、只保留图标并持久化', async () => {
    const { app, container } = await mountApp()

    const collapseButton = container.querySelector<HTMLButtonElement>('.collapse-button')
    expect(collapseButton?.getAttribute('aria-label')).toBe('收起菜单')
    collapseButton?.click()
    await nextTick()
    await new Promise((resolve) => setTimeout(resolve, 350))

    expect(container.querySelector('.sidebar')?.classList.contains('collapsed')).toBe(true)
    expect(container.querySelector('.nav-menu')?.classList.contains('el-menu--collapse')).toBe(true)
    expect(container.querySelector('.brand-copy')).toBeNull()
    expect(container.querySelectorAll('.nav-menu .el-menu-item')).toHaveLength(10)
    expect(container.querySelectorAll('.nav-menu .el-menu-item .el-icon')).toHaveLength(10)
    expect(collapseButton?.getAttribute('aria-label')).toBe('展开菜单')
    expect(collapseButton?.textContent?.trim()).toBe('')
    expect(window.localStorage.getItem('pvi.sidebar.collapsed')).toBe('true')

    app.unmount()
  })

  it('刷新挂载时恢复折叠状态并可再次展开', async () => {
    window.localStorage.setItem('pvi.sidebar.collapsed', 'true')
    const { app, container } = await mountApp()

    expect(container.querySelector('.sidebar')?.classList.contains('collapsed')).toBe(true)
    expect(container.querySelector('.brand-copy')).toBeNull()

    container.querySelector<HTMLButtonElement>('.collapse-button')?.click()
    await nextTick()
    expect(container.querySelector('.sidebar')?.classList.contains('collapsed')).toBe(false)
    expect(container.querySelector('.brand-copy')?.textContent).toContain('Phone Voice Insight')
    expect(window.localStorage.getItem('pvi.sidebar.collapsed')).toBe('false')

    app.unmount()
  })

  it('历史分析路由刷新后只高亮历史 AI 分析', async () => {
    const { app, container } = await mountApp('/analysis', 'ANALYST')
    await new Promise((resolve) => setTimeout(resolve, 0))
    await nextTick()

    const activeItems = Array.from(container.querySelectorAll('.nav-menu .el-menu-item.is-active'))
    expect(activeItems).toHaveLength(1)
    expect(activeItems[0]?.textContent?.trim()).toBe('历史AI分析')

    const navigationLabels = Array.from(container.querySelectorAll('.nav-menu .el-menu-item')).map(
      (item) => item.textContent?.trim(),
    )
    expect(navigationLabels).toEqual(advancedNavigationLabels)

    app.unmount()
  })

  it.each(['/dashboard', '/analysis', '/data-quality'])(
    '%s 的全局 Header 不再显示开发阶段',
    async (path) => {
      const { app, container } = await mountApp(path)

      expect(container.querySelector('.phase-label')).toBeNull()

      app.unmount()
    },
  )

  it('原始数据页面区分发布时间、IP 属地和用户填写地区完整率', async () => {
    const { app, container } = await mountApp('/reviews')
    await new Promise((resolve) => setTimeout(resolve, 0))
    await nextTick()

    expect(container.textContent).toContain('发布时间完整率')
    expect(container.textContent).toContain('98.00%')
    expect(container.textContent).toContain('公开 IP 属地完整率')
    expect(container.textContent).toContain('用户填写地区完整率')

    app.unmount()
  })
})
