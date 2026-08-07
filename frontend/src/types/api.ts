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
  products: number
  sources: number
  reviews: number
  collectionTasks: number
}
