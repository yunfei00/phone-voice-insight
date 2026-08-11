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

describe('App', () => {
  beforeEach(async () => {
    setActivePinia(createPinia())
    await router.push('/dashboard')
    await router.isReady()
  })

  it('可以挂载并读取健康检查数据', async () => {
    const container = document.createElement('div')
    document.body.appendChild(container)
    const app = createApp(App)
    app.use(createPinia())
    app.use(router)
    app.use(ElementPlus)
    app.mount(container)
    await new Promise((resolve) => setTimeout(resolve, 0))
    await nextTick()

    expect(container.textContent).toContain('Phone Voice Insight')
    expect(container.textContent).toContain('数据总览')
    expect(container.textContent).toContain('已连接')
    const navigationLabels = Array.from(container.querySelectorAll('.nav-menu .el-menu-item')).map(
      (item) => item.textContent?.trim(),
    )
    expect(navigationLabels).toEqual([
      '数据总览',
      '手机产品',
      '采集任务',
      '原始反馈',
      '数据质量',
      'AI分析',
      '系统状态',
    ])

    const collapseButton = container.querySelector<HTMLButtonElement>('.collapse-button')
    expect(collapseButton?.getAttribute('aria-label')).toBe('折叠左侧菜单')
    collapseButton?.click()
    await nextTick()
    expect(container.querySelector('.sidebar')?.classList.contains('collapsed')).toBe(true)
    expect(container.querySelector('.main')?.classList.contains('expanded')).toBe(true)
    expect(collapseButton?.getAttribute('aria-label')).toBe('展开左侧菜单')

    await router.push('/system')
    await new Promise((resolve) => setTimeout(resolve, 0))
    await nextTick()
    expect(container.textContent).toContain('0.1.0')

    app.unmount()
    container.remove()
  })
})
