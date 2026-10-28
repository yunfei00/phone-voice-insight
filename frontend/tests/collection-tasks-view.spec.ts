import ElementPlus, { ElMessageBox } from 'element-plus'
import { createApp, nextTick } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  getCollectionTargets,
  getCollectionTasks,
  getProducts,
  getSources,
  createCollectionTask,
  runCollectionTask,
  saveCollectionSchedule,
} from '@/api'
import CollectionTasksView from '@/views/CollectionTasksView.vue'

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({ canWrite: true }),
}))

vi.mock('@/api', () => ({
  getCollectionTargets: vi.fn(),
  getCollectionTasks: vi.fn(),
  getProducts: vi.fn(),
  getSources: vi.fn(),
  createCollectionTask: vi.fn(),
  runCollectionTask: vi.fn(),
  createSourceTarget: vi.fn(),
  recoverStaleCollectionTask: vi.fn(),
  stopCollectionTask: vi.fn(),
  saveCollectionSchedule: vi.fn(),
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
    vi.mocked(getProducts)
      .mockReset()
      .mockResolvedValue({ count: 0, next: null, previous: null, results: [] })
    vi.mocked(getSources)
      .mockReset()
      .mockResolvedValue({ count: 0, next: null, previous: null, results: [] })
    vi.mocked(createCollectionTask).mockReset().mockResolvedValue({
      id: 10,
      source_target: 9,
      source_name: '荣耀俱乐部',
      product_name: '荣耀 Power2',
      target_name: 'Power2 官方话题',
      task_type: 'INCREMENTAL',
      trigger_type: 'MANUAL',
      status: 'PENDING',
      requested_limit: null,
      requested_pages: 2,
      waiting_reason: '等待来源调度',
      dispatched_at: null,
      heartbeat_at: null,
      success_count: 0,
      skipped_count: 0,
      failure_count: 0,
      new_threads: 0,
      known_threads: 0,
      new_records: 0,
      duplicate_records: 0,
      stopped_at_known_boundary: false,
      error_message: '',
      completion_verified: false,
      verification_report: {},
      started_at: null,
      finished_at: null,
      last_checkpoint: {},
      runs: [],
      created_at: '2026-10-27T08:00:00Z',
      updated_at: '2026-10-27T08:00:00Z',
    })
    vi.mocked(runCollectionTask).mockReset().mockResolvedValue({
      task_id: 10,
      status: 'PENDING',
      celery_task_id: 'celery-10',
    })
    vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm')
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
    buttons.find((button) => button.textContent?.includes('开始采集'))?.click()
    await flush()
    await flush()
    expect(createCollectionTask).toHaveBeenCalledWith({
      source_target: 9,
      task_type: 'INCREMENTAL',
      requested_pages: 2,
    })
    expect(runCollectionTask).toHaveBeenCalledWith(10)

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
