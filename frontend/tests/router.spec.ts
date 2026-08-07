import { describe, expect, it } from 'vitest'

import router from '@/router'

describe('router', () => {
  it('包含第一阶段全部基础路由', () => {
    const names = router.getRoutes().map((route) => route.name)
    expect(names).toEqual(
      expect.arrayContaining([
        'dashboard',
        'products',
        'collection-tasks',
        'reviews',
        'analysis',
        'system',
      ]),
    )
  })
})
