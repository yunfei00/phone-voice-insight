import { describe, expect, it } from 'vitest'

import router from '@/router'

describe('router', () => {
  it('包含第一阶段全部基础路由', () => {
    const names = router.getRoutes().map((route) => route.name)
    expect(names).toEqual(
      expect.arrayContaining([
        'dashboard',
        'comparison',
        'issues',
        'insight-reports',
        'ai-assistant',
        'products',
        'collection-tasks',
        'threads',
        'reviews',
        'data-quality',
        'structured-analysis',
        'ai-tasks',
        'ai-settings',
        'system',
        'users',
        'login',
      ]),
    )
  })
})
