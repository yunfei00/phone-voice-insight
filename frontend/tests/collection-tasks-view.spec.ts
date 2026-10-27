import ElementPlus from 'element-plus'
import { createApp, nextTick } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  getCollectionTargets,
  getCollectionTasks,
  saveCollectionSchedule,
  startIncrementalCollection,
} from '@/api'
import CollectionTasksView from '@/views/CollectionTasksView.vue'

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({ canWrite: true }),
}))

vi.mock('@/api', () => ({
  getCollectionTargets: vi.fn(),
  getCollectionTasks: vi.fn(),
  saveCollectionSchedule: vi.fn(),
  startFullCollection: vi.fn(),
  startIncrementalCollection: vi.fn(),
}))

const target = {
  id: 4,
  source_target: 9,
  source_id: 2,
  source_code: 'HONOR_CLUB',
  source_name: '荣耀俱乐部',
  product_id: 1,
  product_name: '荣耀 Power2',
  target_name: 'Power2 官方话题',
  target_url: 'https://club.honor.com/cn/threadtopic-595-1.html',
  status: 'READY' as const,
  full_verified: true,
  full_verified_at: '2026-10-27T08:00:00Z',
  active_task: null,
  active_task_status: null,
  last_full_task: 7,
  last_incremental_task: 8,
  last_success_at: '2026-10-27T09:00:00Z',
  last_failure_at: null,
  last_discovered_thread_count: 99,
  last_verified_thread_count: 99,
  last_error: '',
  schedule_id: 3,
  schedule_enabled: true,
  schedule_interval_hours: 6,
  has_historical_data: true,
}

async function flush(): Promise<void> {
  await new Promise((resolve) => setTimeout(resolve, 0))
  await nextTick()
}

describe('CollectionTasksView', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
    vi.mocked(getCollectionTargets)
      .mockReset()
      .mockResolvedValue({
        count: 1,
        next: null,
        previous: null,
        results: [target],
      })
    vi.mocked(getCollectionTasks).mockReset().mockResolvedValue({
      count: 0,
      next: null,
      previous: null,
      results: [],
    })
    vi.mocked(startIncrementalCollection).mockReset().mockResolvedValue({
      task_id: 10,
      status: 'PENDING',
      celery_task_id: 'celery-10',
    })
    vi.mocked(saveCollectionSchedule).mockReset().mockResolvedValue({
      id: 3,
      source_target: 9,
      source_name: '荣耀俱乐部',
      product_name: '荣耀 Power2',
      target_name: 'Power2 官方话题',
      enabled: true,
      interval_hours: 6,
      created_at: '2026-10-27T08:00:00Z',
      updated_at: '2026-10-27T08:00:00Z',
    })
  })

  it('按采集入口加载控制卡、启动增量并分页请求历史', async () => {
    const container = document.createElement('div')
    document.body.appendChild(container)
    const app = createApp(CollectionTasksView)
    app.use(ElementPlus)
    app.mount(container)
    await flush()
    await flush()

    expect(container.textContent).toContain('全量完整性验证通过')
    const buttons = Array.from(container.querySelectorAll('button'))
    buttons.find((button) => button.textContent?.includes('立即增量'))?.click()
    await flush()
    expect(startIncrementalCollection).toHaveBeenCalledWith(4)

    buttons.find((button) => button.textContent?.includes('运行历史'))?.click()
    await flush()
    expect(getCollectionTasks).toHaveBeenCalledWith({
      source_target: 9,
      page: 1,
      page_size: 10,
      ordering: '-created_at',
    })
    app.unmount()
  })
})
