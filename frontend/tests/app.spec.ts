import { createPinia, setActivePinia } from 'pinia'
import ElementPlus from 'element-plus'
import { createApp, nextTick } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import App from '@/App.vue'
import router from '@/router'

vi.mock('@/api', () => ({
  getHealth: vi.fn().mockResolvedValue({
    status: 'ok',
    service: 'phone-voice-insight-backend',
    database: 'ok',
    redis: 'ok',
  }),
  getProducts: vi.fn().mockResolvedValue({ count: 1, results: [] }),
  getSources: vi.fn().mockResolvedValue({ count: 2, results: [] }),
  getReviews: vi.fn().mockResolvedValue({ count: 0, results: [] }),
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
}))

const expectedNavigationLabels = [
  '数据总览',
  '手机产品',
  '采集任务',
  '原始反馈',
  '数据质量',
  'AI分析',
  '系统状态',
]

async function mountApp(path = '/dashboard') {
  await router.push(path)
  await router.isReady()
  const container = document.createElement('div')
  document.body.appendChild(container)
  const app = createApp(App)
  app.use(createPinia())
  app.use(router)
  app.use(ElementPlus)
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
    setActivePinia(createPinia())
  })

  it('桌面默认展开且只显示一组七项菜单', async () => {
    const { app, container } = await mountApp()

    expect(container.textContent).toContain('Phone Voice Insight')
    expect(container.textContent).toContain('数据总览')
    expect(container.textContent).toContain('已连接')
    const navigationLabels = Array.from(container.querySelectorAll('.nav-menu .el-menu-item')).map(
      (item) => item.textContent?.trim(),
    )
    expect(navigationLabels).toEqual(expectedNavigationLabels)
    expect(new Set(navigationLabels).size).toBe(7)
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
    expect(container.querySelectorAll('.nav-menu .el-menu-item')).toHaveLength(7)
    expect(container.querySelectorAll('.nav-menu .el-menu-item .el-icon')).toHaveLength(7)
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

  it('分析路由刷新后只高亮 AI分析', async () => {
    const { app, container } = await mountApp('/analysis')
    await new Promise((resolve) => setTimeout(resolve, 0))
    await nextTick()

    const activeItems = Array.from(container.querySelectorAll('.nav-menu .el-menu-item.is-active'))
    expect(activeItems).toHaveLength(1)
    expect(activeItems[0]?.textContent?.trim()).toBe('AI分析')

    const navigationLabels = Array.from(container.querySelectorAll('.nav-menu .el-menu-item')).map(
      (item) => item.textContent?.trim(),
    )
    expect(navigationLabels).toEqual(expectedNavigationLabels)

    app.unmount()
  })
})
