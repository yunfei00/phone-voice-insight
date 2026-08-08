export interface PaginatedResponse<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

export interface HealthStatus {
  status: 'ok' | 'degraded'
  service: string
  database: 'ok' | 'error'
  redis: 'ok' | 'error'
}

export interface Brand {
  id: number
  name: string
  code: string
  is_active: boolean
}

export interface ProductVariant {
  id: number
  memory: string
  storage: string
  color: string
  sku_name: string
  is_active: boolean
}

export interface Product {
  id: number
  brand: Brand
  name: string
  normalized_name: string
  series: string
  model_code: string
  release_date: string | null
  description: string
  is_active: boolean
  variants: ProductVariant[]
}

export interface SourceTarget {
  id: number
  product: number
  product_name: string
  name: string
  target_type: 'PRODUCT' | 'COMMUNITY'
  target_url: string
  external_id: string
  is_active: boolean
}

export interface DataSource {
  id: number
  code: string
  name: string
  source_type: 'ECOMMERCE' | 'COMMUNITY'
  is_active: boolean
  targets: SourceTarget[]
}

export type CollectionStatus = 'PENDING' | 'RUNNING' | 'PAUSED' | 'SUCCESS' | 'FAILED' | 'CANCELLED'

export interface CollectionRun {
  id: number
  run_number: number
  status: CollectionStatus
  started_at: string | null
  finished_at: string | null
  success_count: number
  skipped_count: number
  failure_count: number
  new_threads: number
  known_threads: number
  new_records: number
  duplicate_records: number
  stopped_at_known_boundary: boolean
  checkpoint_json: Record<string, unknown>
  error_message: string
}

export interface CollectionTask {
  id: number
  source_target: number
  source_name: string
  product_name: string
  target_name: string
  task_type: 'FULL' | 'INCREMENTAL'
  status: CollectionStatus
  requested_limit: number | null
  success_count: number
  skipped_count: number
  failure_count: number
  new_threads: number
  known_threads: number
  new_records: number
  duplicate_records: number
  stopped_at_known_boundary: boolean
  error_message: string
  started_at: string | null
  finished_at: string | null
  last_checkpoint: Record<string, unknown>
  runs: CollectionRun[]
  created_at: string
  updated_at: string
}

export interface CollectionTaskRunResponse {
  task_id: number
  status: 'PENDING'
  celery_task_id: string
}

export interface ReviewRecord {
  id: number
  source: number
  source_name: string
  product: number
  product_name: string
  product_variant: number | null
  variant_name: string | null
  record_type: 'REVIEW' | 'APPEND_REVIEW' | 'THREAD' | 'REPLY' | 'OFFICIAL_REPLY'
  title: string
  content: string
  rating: string | null
  published_at: string | null
  author_role: string
  is_official: boolean
  external_id: string | null
  parent_external_id: string
  source_url: string
  raw_data: Record<string, unknown>
  collected_at: string
  status: string
}

export interface DashboardMetrics {
  threads: number
  replies: number
  rawRecords: number
  eligibleCorpus: number
  excludedRecords: number
  latestCollection: string | null
}

export type ExclusionReason =
  | 'NONE'
  | 'EMPTY_CONTENT'
  | 'OFFICIAL_CONTENT'
  | 'PRODUCT_NOT_MATCHED'
  | 'PAGE_NOISE'
  | 'PROMOTIONAL'
  | 'LOW_INFORMATION'
  | 'DUPLICATE'
  | 'INVALID_ENCODING'
  | 'PARSER_ARTIFACT'
  | 'OTHER'

export interface ReviewQuality {
  id: number
  review_id: number
  source_id: number
  source_name: string
  product_id: number
  product_name: string
  record_type: ReviewRecord['record_type']
  author_role: string
  original_title: string
  original_content: string
  normalized_text: string
  context_text: string
  published_at: string | null
  has_meaningful_text: boolean
  is_product_related: boolean
  is_official_content: boolean
  is_low_information: boolean
  is_navigation_or_page_noise: boolean
  is_promotional: boolean
  is_duplicate: boolean
  duplicate_of: number | null
  eligible_for_ai: boolean
  exclusion_reason: ExclusionReason
  quality_score: number
  flags_json: Record<string, unknown>
  processor_version: string
  processed_at: string
  manual_override: boolean
  manual_eligible: boolean | null
  manual_reason: string
}

export interface DataQualitySummary {
  total: number
  eligible: number
  excluded: number
  eligibility_rate: number
  categories: {
    official: number
    low_information: number
    promotional: number
    noise: number
    duplicate: number
    product_not_matched: number
    empty: number
  }
  exclusion_reasons: Record<ExclusionReason, number>
}
