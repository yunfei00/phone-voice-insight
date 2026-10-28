import ElementPlus from 'element-plus'
import { createApp, nextTick } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { getStructuredAnalyses, getTaxonomy } from '@/api'
import StructuredAnalysisView from '@/views/StructuredAnalysisView.vue'

vi.mock('@/api', () => ({
  getStructuredAnalyses: vi.fn(),
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
  })

  it('加载空状态且不会触发模型调用', async () => {
    const container = document.createElement('div')
    document.body.appendChild(container)
    const app = createApp(StructuredAnalysisView)
    app.use(ElementPlus)
    app.mount(container)
    await flush()
    await flush()
    expect(getStructuredAnalyses).toHaveBeenCalledWith(expect.objectContaining({ page_size: 30 }))
    expect(container.textContent).toContain('系统不会自动调用收费模型')
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
