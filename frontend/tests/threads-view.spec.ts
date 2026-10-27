import ElementPlus from 'element-plus'
import { createApp, nextTick } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { getThreadTree, getThreadTrees } from '@/api'
import ThreadsView from '@/views/ThreadsView.vue'
import { buildThreadQuery } from '@/views/thread-query'

vi.mock('@/api', () => ({
  getProducts: vi.fn().mockResolvedValue({ count: 0, results: [] }),
  getSources: vi.fn().mockResolvedValue({ count: 0, results: [] }),
  getThreadTrees: vi.fn(),
  getThreadTree: vi.fn(),
}))

const thread = {
  id: 7,
  external_id: 'thread:7',
  product: 1,
  product_name: '荣耀 Power2',
  source: 1,
  source_name: '荣耀俱乐部',
  title: '真实使用体验',
  content: '整体不错',
  published_at: '2026-10-27T08:00:00Z',
  latest_reply_at: '2026-10-27T09:00:00Z',
  activity_at: '2026-10-27T09:00:00Z',
  reply_count: 2,
  collected_reply_count: 1,
  view_count: 100,
  like_count: 3,
  source_url: 'https://example.com/thread/7',
  thread_match: false,
  reply_match_count: 1,
}

async function flush(): Promise<void> {
  await new Promise((resolve) => setTimeout(resolve, 0))
  await nextTick()
}

describe('ThreadsView', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
    vi.mocked(getThreadTrees)
      .mockReset()
      .mockResolvedValue({
        count: 1,
        next: null,
        previous: null,
        total_threads: 4,
        matched_reply_count: 1,
        results: [thread],
      })
    vi.mocked(getThreadTree).mockReset().mockResolvedValue({ thread, replies: [] })
  })

  it('加载页面、提交回复搜索并按需请求帖子详情', async () => {
    const container = document.createElement('div')
    document.body.appendChild(container)
    const app = createApp(ThreadsView)
    app.use(ElementPlus)
    app.mount(container)
    await flush()
    await flush()

    expect(container.textContent).toContain('真实使用体验')
    const input = container.querySelector<HTMLInputElement>('.thread-search input')!
    input.value = '信号'
    input.dispatchEvent(new Event('input', { bubbles: true }))
    container
      .querySelector<HTMLButtonElement>('.thread-search .el-input-group__append button')!
      .click()
    await flush()

    expect(getThreadTrees).toHaveBeenLastCalledWith(expect.objectContaining({ search: '信号' }))
    const detailButton = Array.from(container.querySelectorAll('button')).find((button) =>
      button.textContent?.includes('展开 1 条回复'),
    )
    detailButton?.click()
    await flush()
    expect(getThreadTree).toHaveBeenCalledWith(7)
    app.unmount()
  })

  it('组合产品、来源、时间语义和排序参数', () => {
    const query = buildThreadQuery(
      {
        page: 2,
        page_size: 20,
        product: 8,
        source: 3,
        search: '',
        timePreset: '7d',
        timeBasis: 'activity',
        ordering: 'view_count',
      },
      null,
      new Date('2026-10-27T12:00:00.000Z'),
    )
    expect(query).toMatchObject({
      page: 2,
      page_size: 20,
      product: 8,
      source: 3,
      ordering: 'view_count',
      activity_at_after: '2026-10-20T12:00:00.000Z',
      activity_at_before: '2026-10-27T12:00:00.000Z',
    })
    expect(query).not.toHaveProperty('published_at_after')
  })
})
