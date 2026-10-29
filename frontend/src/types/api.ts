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
  validation_status: 'UNVERIFIED' | 'VALID' | 'INVALID'
  validated_at: string | null
  validation_error_code: string
  validation_error_message: string
  validation_report: Record<string, unknown>
}

export interface DataSource {
  id: number
  code: string
  name: string
  source_type: 'ECOMMERCE' | 'COMMUNITY'
  is_active: boolean
  targets: SourceTarget[]
}

export interface SourceTargetCleanupPreview {
  source_target_id: number
  product_id: number
  product_name: string
  source_name: string
  target_name: string
  target_url: string
  thread_count: number
  reply_count: number
  other_record_count: number
  review_quality_count: number
  review_quality_run_count: number
  corpus_item_count: number
  analysis_result_count: number
  analysis_run_count: number
  structured_analysis_count: number
  collection_task_count: number
  collection_run_count: number
  active_collection_count: number
  active_analysis_count: number
}

export type CollectionStatus =
  'PENDING' | 'RUNNING' | 'PAUSED' | 'SUCCESS' | 'FAILED' | 'CANCELLED' | 'STOPPING'

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
  requested_pages: number | null
  waiting_reason: string
  dispatched_at: string | null
  heartbeat_at: string | null
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
  status:
    'NOT_INITIALIZED' | 'WAITING' | 'FULL_RUNNING' | 'INCREMENTAL_RUNNING' | 'READY' | 'DEGRADED'
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
  validation_status: 'UNVERIFIED' | 'VALID' | 'INVALID'
  validated_at: string | null
  validation_error_message: string
  last_task_type: 'FULL' | 'INCREMENTAL' | null
  last_task_status: CollectionStatus | null
  last_new_threads: number
  last_new_replies: number
  last_failure_count: number
  progress_stage: string
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
  ip_location: string
  profile_region: string
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

export interface ReviewMetadataCounts {
  total: number
  published_at_count: number
  published_at_rate: number
  ip_location_count: number
  ip_location_rate: number
  profile_region_count: number
  profile_region_rate: number
}

export interface ReviewMetadataCompleteness {
  summary: ReviewMetadataCounts
  by_product: (ReviewMetadataCounts & { product: number; product_name: string })[]
  by_record_type: (ReviewMetadataCounts & { record_type: string })[]
  failure_reasons: {
    published_at: Record<string, number>
    ip_location: Record<string, number>
    profile_region: Record<string, number>
  }
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
  ip_location: string
  profile_region: string
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
  ip_location: string
  profile_region: string
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
  provider: 'openai_compatible' | 'ollama'
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

export interface TaxonomyTag {
  tag_id: string
  parent_id: string | null
  name: string
  description: string
  positive_examples: string[]
  negative_examples: string[]
  confused_with: string[]
  enabled: boolean
  taxonomy_version: string
  children: TaxonomyTag[]
}

export interface TaxonomyDefinition {
  taxonomy_version: string
  name: string
  domains: TaxonomyTag[]
}

export interface StructuredOpinion {
  id: number
  business_domains: string[]
  aspect_code: string
  topic_code: string
  sentiment: string
  intent: string
  issue_type: string
  severity: string
  scenario: string | null
  trigger: string | null
  phenomenon: string | null
  target_product: string | null
  compared_products: string[]
  relation_type: string
  evidence_text: string
  evidence_start: number
  evidence_end: number
  confidence: string
  review_required: boolean
}

export interface StructuredAnalysisV1 {
  id: number
  content: number
  run: number
  original_title: string
  original_content: string
  product_name: string
  source_name: string
  run_status: string
  provider: string
  model: string
  prompt_version: string
  taxonomy_version: string
  schema_version: string
  overall_sentiment: string
  language: string
  content_type: string
  relevance: string
  summary: string
  model_mentions: string[]
  schema_valid: boolean
  review_required: boolean
  aspects: StructuredOpinion[]
  review_history: Array<{
    id: number
    reviewer_name: string
    review_reason: string
    reviewed_at: string
  }>
  created_at: string
}

export interface StructuredQuality {
  total_runs: number
  successful_runs: number
  success_rate: number | null
  schema_valid_rate: number | null
  review_required: number
  human_evaluation_status: 'NOT_EVALUATED'
  accuracy_metrics: null
  error_distribution?: { error_code: string; count: number }[]
}

export interface StructuredAggregateItem {
  aspect_code?: string
  topic_code?: string
  sentiment?: string
  severity?: string
  count: number
}

export interface StructuredAggregates {
  disclaimer: string
  content_count: number
  opinion_count: number
  domain_distribution: StructuredAggregateItem[]
  topic_distribution: StructuredAggregateItem[]
  sentiment_distribution: StructuredAggregateItem[]
  severity_distribution: StructuredAggregateItem[]
  high_frequency_clusters: StructuredAggregateItem[]
}

export interface StructuredBatch extends AnalysisBatch {
  dry_run: boolean
  max_concurrency: number
  requests_per_minute: number
  token_limit: number | null
  cost_budget: string | null
  estimated_cost: string
  actual_cost: string
  review_required_count: number
}

export interface DashboardFilters {
  product_id?: number
  source_id?: number
  start_date?: string
  end_date?: string
}

export interface DashboardIssue {
  id: string
  product_id: number
  product_name: string
  category: string
  topic_code: string
  name: string
  feedback_count: number
  recent_count: number
  previous_count: number
  growth_rate: number | null
  is_new: boolean
  severity: string
  first_seen: string | null
  last_seen: string | null
}

export interface DashboardOverview {
  filters: { start_date: string; end_date: string }
  raw_feedback: number
  valid_feedback: number
  ai_analyzed: number
  explicit_issue_feedback: number
  watch_issue_count: number
  latest_data_at: string | null
  published_time_fallback_count: number
  disclaimer: string
  watchlist: DashboardIssue[]
}

export interface DashboardTrend {
  date: string
  valid_feedback: number
  explicit_issues: number
}

export interface DashboardCategory {
  code: string
  name: string
  feedback_count: number
  analyzed_denominator: number
  ratio: number | null
}

export interface DashboardProductSummary {
  product_id: number
  product_name: string
  valid_feedback: number
  ai_analyzed: number
  explicit_issue_feedback: number
  top_issue: string | null
  latest_data_at: string | null
}

export interface DashboardComparisonSide extends DashboardOverview {
  product_id: number
  product_name: string
  negative_ratio: number | null
  ratio_denominator: number
  sample_sufficient: boolean
  top_issues: DashboardIssue[]
}

export interface DashboardComparison {
  left: DashboardComparisonSide
  right: DashboardComparisonSide
  minimum_sample: number
  reliable: boolean
  reliability_message: string | null
  categories: Array<{
    code: string
    name: string
    left: DashboardCategory
    right: DashboardCategory
  }>
}

export interface DashboardEvidence {
  id: number
  analysis__content_id: number
  analysis__content__title: string
  analysis__content__content: string
  analysis__content__source_url: string
  analysis__content__published_at: string | null
  analysis__content__collected_at: string
  analysis__summary: string
  evidence_text: string
  confidence: string
  severity: string
}

export interface DashboardIssueDetail extends DashboardIssue {
  summary: string
  trend: DashboardTrend[]
  evidence: DashboardEvidence[]
}

export interface InsightReport {
  id: number
  report_type: 'DAILY' | 'WEEKLY'
  title: string
  product_id: number | null
  product_name: string
  source_id: number | null
  source_name: string
  period_start: string
  period_end: string
  generated_at: string | null
  data_cutoff: string | null
  status: 'PENDING' | 'READY' | 'FAILED'
  error_message: string
  snapshot?: {
    overview: DashboardOverview
    top_issues: DashboardIssue[]
    watchlist: DashboardIssue[]
    coverage: Record<string, string | number | null>
    data_insufficient: boolean
    disclaimer: string
  }
}

export interface OperationsStatus {
  role_scope: 'full' | 'summary'
  business_status: {
    collection: string
    data_update: string
    ai_automation: 'enabled' | 'disabled'
    ai_message: string
  }
  system: Record<string, string>
  latest: { collection_at: string | null; analysis_at: string | null }
  ai: {
    today_tokens: number
    daily_budget: number
    budget_ratio: number | null
    budget_exhausted: boolean
  }
  collection?: Record<string, number>
  governance?: Record<string, number>
  analysis?: Record<string, number>
}

export type AssistantProvider = 'openai_compatible' | 'ollama' | 'fake'

export interface AssistantModelProfile {
  id: number
  name: string
  provider: AssistantProvider
  base_url: string
  model: string
  api_key_configured: boolean
  api_key_masked: string
  thinking_mode: '' | 'enabled' | 'disabled'
  temperature: string
  timeout_seconds: number
  max_output_tokens: number
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface AssistantModelProfilePayload {
  name: string
  provider: AssistantProvider
  base_url: string
  model: string
  api_key?: string
  thinking_mode: '' | 'enabled' | 'disabled'
  temperature: number
  timeout_seconds: number
  max_output_tokens: number
  is_active: boolean
}

export interface AssistantModelList {
  default_model: {
    id: null
    name: string
    model: string
    provider: string
    configured: boolean
  }
  results: AssistantModelProfile[]
}

export type AssistantConversationStatus = 'IDLE' | 'RUNNING' | 'CANCELLED' | 'FAILED'

export interface AssistantConversation {
  id: string
  title: string
  model_profile: number | null
  use_default_model: boolean
  model_display: string
  status: AssistantConversationStatus
  context: Record<string, unknown>
  last_message_at: string | null
  message_count: number
  created_at: string
  updated_at: string
}

export interface AssistantEvidenceItem {
  review_id: number
  title: string
  content: string
  source_url: string
  published_at: string | null
}

export interface AssistantMessage {
  id: string
  role: 'USER' | 'ASSISTANT' | 'SYSTEM'
  content: string
  request_id: string | null
  status: 'PENDING' | 'RUNNING' | 'COMPLETED' | 'CANCELLED' | 'FAILED'
  model_name_snapshot: string
  provider_snapshot: string
  evidence: AssistantEvidenceItem[]
  prompt_tokens: number | null
  completion_tokens: number | null
  total_tokens: number | null
  latency_ms: number | null
  error_code: string
  error_message: string
  created_at: string
}

export interface AssistantStreamEvent {
  type: 'start' | 'tool' | 'delta' | 'done' | 'cancelled' | 'error'
  message_id?: string
  content?: string
  message?: string
  code?: string
  tool?: string
  evidence?: AssistantEvidenceItem[]
  model?: string
}
