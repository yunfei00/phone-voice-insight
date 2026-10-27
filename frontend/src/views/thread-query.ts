export type TimePreset = 'all' | 'today' | '3d' | '7d' | '30d' | 'custom'
export type TimeBasis = 'published' | 'activity'

export interface ThreadFilters {
  page: number
  page_size: number
  product?: number
  source?: number
  search: string
  timePreset: TimePreset
  timeBasis: TimeBasis
  ordering: string
}

export function buildThreadQuery(
  filters: ThreadFilters,
  customRange: [Date, Date] | null,
  now = new Date(),
): Record<string, string | number | undefined> {
  const bounds = dateBounds(filters.timePreset, customRange, now)
  const prefix = filters.timeBasis === 'published' ? 'published_at' : 'activity_at'
  return {
    page: filters.page,
    page_size: filters.page_size,
    product: filters.product,
    source: filters.source,
    search: filters.search.trim() || undefined,
    ordering: filters.ordering,
    [`${prefix}_after`]: bounds.after,
    [`${prefix}_before`]: bounds.before,
  }
}

function dateBounds(
  preset: TimePreset,
  customRange: [Date, Date] | null,
  now: Date,
): { after?: string; before?: string } {
  if (preset === 'all') return {}
  let after: Date
  let before = new Date(now)
  if (preset === 'custom') {
    if (!customRange) return {}
    after = new Date(customRange[0])
    before = new Date(customRange[1])
    before.setHours(23, 59, 59, 999)
  } else {
    after = new Date(now)
    if (preset === 'today') after.setHours(0, 0, 0, 0)
    else after.setDate(after.getDate() - Number.parseInt(preset, 10))
  }
  return { after: after.toISOString(), before: before.toISOString() }
}
