export interface PaginatedResponse<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

export type UserRole = 'ADMIN' | 'ANALYST' | 'VIEWER'

export interface UserAccount {
  id: number
  username: string
  email: string
  first_name: string
  last_name: string
  role: UserRole
  is_active: boolean
  last_login: string | null
  date_joined: string
}

export interface LoginPayload {
  username: string
  password: string
}

export interface LoginResponse {
  token: string
  user: UserAccount
}

export interface UserPayload {
  username: string
  email?: string
  first_name?: string
  last_name?: string
  role: UserRole
  is_active: boolean
  password?: string
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
  completion_verified: boolean
  verification_report: Record<string, unknown>
}

export interface CollectionTask {
  id: number
  source_target: number
  source_name: string
  product_name: string
  target_name: string
  task_type: 'FULL' | 'INCREMENTAL'
  trigger_type: 'MANUAL' | 'SCHEDULED' | 'RETRY' | 'RECOVERY'
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
  completion_verified: boolean
  verification_report: Record<string, unknown>
  started_at: string | null
  finished_at: string | null
  last_checkpoint: Record<string, unknown>
  runs: CollectionRun[]
  created_at: string
  updated_at: string
}

export interface CollectionTargetState {
  id: number
  source_target: number
  source_id: number
  source_code: string
  source_name: string
  product_id: number
  product_name: string
  target_name: string
  target_url: string
  status: 'NOT_INITIALIZED' | 'FULL_RUNNING' | 'INCREMENTAL_RUNNING' | 'READY' | 'DEGRADED'
  full_verified: boolean
  full_verified_at: string | null
  active_task: number | null
  active_task_status: CollectionStatus | null
  last_full_task: number | null
  last_incremental_task: number | null
  last_success_at: string | null
  last_failure_at: string | null
  last_discovered_thread_count: number
  last_verified_thread_count: number
  last_error: string
  schedule_id: number | null
  schedule_enabled: boolean
  schedule_interval_hours: number | null
  has_historical_data: boolean
}

export interface CollectionTaskRunResponse {
  task_id: number
  status: 'PENDING'
  celery_task_id: string
}

export interface CollectionSchedule {
  id: number
  source_target: number
  source_name: string
  product_name: string
  target_name: string
  enabled: boolean
  interval_hours: number
  created_at: string
  updated_at: string
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
  source_region: string
  region_evidence: string
  software_version: string
  author_role: string
  is_official: boolean
  external_id: string | null
  parent_external_id: string
  source_url: string
  raw_data: Record<string, unknown>
  collected_at: string
  status: string
}

export interface ThreadSummary {
  id: number
  external_id: string | null
  product: number
  product_name: string
  source: number
  source_name: string
  title: string
  content: string
  published_at: string | null
  latest_reply_at: string | null
  activity_at: string | null
  reply_count: number | null
  collected_reply_count: number
  view_count: number | null
  like_count: number | null
  source_url: string
  thread_match: boolean
  reply_match_count: number
}

export interface ThreadReply {
  id: number
  external_id: string | null
  parent_external_id: string
  record_type: 'REPLY' | 'OFFICIAL_REPLY'
  content: string
  published_at: string | null
  author_role: string
  is_official: boolean
  source_url: string
  unresolved_parent: boolean
  children: ThreadReply[]
}

export interface ThreadDetail {
  thread: ThreadSummary
  replies: ThreadReply[]
}

export interface ThreadPage extends PaginatedResponse<ThreadSummary> {
  total_threads: number
  matched_reply_count: number
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
  | 'NO_PRODUCT_EXPERIENCE_SIGNAL'
  | 'SOCIAL_INTERACTION'
  | 'RESOURCE_SHARE'
  | 'PHOTO_SHARE'
  | 'METADATA_REPLY'
  | 'OTHER'

export type ContentPurpose =
  | 'PRODUCT_EXPERIENCE'
  | 'QUESTION'
  | 'RESOURCE_SHARE'
  | 'PHOTO_SHARE'
  | 'TUTORIAL'
  | 'SOCIAL_INTERACTION'
  | 'PROMOTIONAL'
  | 'METADATA_REPLY'
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
  has_product_experience_signal: boolean
  context_required: boolean
  content_purpose: ContentPurpose
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

export type AspectName =
  | 'BATTERY'
  | 'CHARGING'
  | 'HEATING'
  | 'SIGNAL'
  | 'PERFORMANCE'
  | 'SYSTEM_FLUENCY'
  | 'SYSTEM_BUG'
  | 'DISPLAY'
  | 'CAMERA'
  | 'WEIGHT_AND_FEEL'
  | 'BUILD_QUALITY'
  | 'AUDIO_AND_CALL'
  | 'DURABILITY'
  | 'VALUE_FOR_MONEY'
  | 'AFTER_SALES'

export type SentimentName = 'POSITIVE' | 'NEUTRAL' | 'NEGATIVE' | 'MIXED'

export interface AspectAnalysisResult {
  id: number
  aspect: AspectName
  sentiment: SentimentName
  sentiment_score: string | null
  issue_category: string
  issue_summary: string
  usage_scenario: string
  evidence_text: string
  context_dependent: boolean
  context_evidence_text: string
  context_evidence_review_id: string
  confidence: string
}

export interface AnalysisEvaluation {
  aspect_correct: boolean
  sentiment_correct: boolean
  issue_correct: boolean
  scenario_correct: boolean
  evidence_correct: boolean
  context_correct: boolean
  hallucination: boolean
  reviewer_notes: string
  evaluated_at: string
}

export interface AnalysisResult {
  id: number
  review_id: number
  record_type: ReviewRecord['record_type']
  original_title: string
  original_content: string
  normalized_text: string
  published_at: string | null
  context_text: string
  batch: number | null
  status: 'PENDING' | 'SUCCESS' | 'FAILED'
  provider: string
  model_name: string
  model_version: string
  prompt_version: string
  input_hash: string
  content_purpose: ContentPurpose
  is_valid_content: boolean
  confidence: string | null
  summary: string
  error_code: string
  error_message: string
  attempt_count: number
  retry_count: number
  latency_ms: number | null
  prompt_tokens: number | null
  completion_tokens: number | null
  total_tokens: number | null
  analyzed_at: string | null
  aspects: AspectAnalysisResult[]
  evaluation: AnalysisEvaluation | null
  created_at: string
  updated_at: string
}

export interface AnalysisBatch {
  id: number
  product: number
  product_name: string
  source: number
  source_name: string
  corpus_version: string
  provider: string
  model_name: string
  prompt_version: string
  status: 'PENDING' | 'RUNNING' | 'SUCCESS' | 'PARTIAL' | 'FAILED' | 'CANCELLED'
  requested_count: number
  success_count: number
  failed_count: number
  skipped_count: number
  retry_count: number
  prompt_tokens: number | null
  completion_tokens: number | null
  total_tokens: number | null
  started_at: string | null
  finished_at: string | null
  error_message: string
  created_at: string
  updated_at: string
}

export interface AnalysisSummary {
  eligible_corpus: number
  analyzed_reviews: number
  success: number
  failed: number
  pending: number
  average_confidence: number | null
  schema_failures: number
  evidence_failures: number
  evaluated: number
  evaluation_accuracy: Record<
    'aspect' | 'sentiment' | 'issue' | 'scenario' | 'evidence' | 'context',
    number | null
  >
}

export interface SamplePreviewItem {
  review_id: number
  record_type: ReviewRecord['record_type']
  current_content: string
  necessary_context: string
  experience_signal_reason: string
  candidate_aspects: AspectName[]
  content_purpose: ContentPurpose
  context_required: boolean
}

export interface SamplePreview {
  sample_version: string
  count: number
  ai_status: 'NOT_RUN' | 'HISTORICAL'
  items: SamplePreviewItem[]
}

export interface PersonalAIConfiguration {
  provider: string
  base_url: string
  api_key_configured: boolean
  api_key_masked: string
  model: string
  thinking_mode: '' | 'enabled' | 'disabled'
  timeout_seconds: number
  temperature: string
  max_output_tokens: number
  is_active: boolean
  configured: boolean
  updated_at: string | null
}

export interface AIConfiguration extends PersonalAIConfiguration {
  prompt_version: string
  concurrency: number
}

export interface AIConfigurationPayload {
  provider: 'openai_compatible'
  base_url: string
  api_key?: string
  model: string
  thinking_mode: '' | 'enabled' | 'disabled'
  timeout_seconds: number
  temperature: number
  max_output_tokens: number
  is_active: boolean
}

export interface AIConnectivityResult {
  status: 'ok'
  provider: string
  model: string
  latency_ms: number
}
