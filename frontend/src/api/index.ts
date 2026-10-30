import axios from 'axios'
import { AUTH_TOKEN_STORAGE_KEY } from '@/config/auth'
import apiClient from './client'
import type {
  AIConfiguration,
  AIConfigurationPayload,
  AIConnectivityResult,
  AnalysisBatch,
  AnalysisEvaluation,
  AnalysisResult,
  AnalysisSummary,
  CollectionSchedule,
  CollectionTargetState,
  CollectionTask,
  CollectionTaskRunResponse,
  DataQualitySummary,
  DataSource,
  HealthStatus,
  LoginPayload,
  LoginResponse,
  PaginatedResponse,
  PersonalAIConfiguration,
  Product,
  SamplePreview,
  SourceTargetCleanupPreview,
  ThreadDetail,
  ThreadPage,
  ReviewQuality,
  ReviewMetadataCompleteness,
  ReviewRecord,
  UserAccount,
  UserPayload,
  StructuredAnalysisV1,
  StructuredBatch,
  StructuredQuality,
  StructuredAggregates,
  AssistantConversation,
  AssistantMessage,
  AssistantModelList,
  AssistantModelProfile,
  AssistantModelProfilePayload,
  AssistantStreamEvent,
  TaxonomyDefinition,
  DashboardFilters,
  DashboardOverview,
  DashboardTrend,
  DashboardCategory,
  DashboardProductSummary,
  DashboardComparison,
  DashboardIssue,
  DashboardIssueDetail,
  InsightReport,
  OperationsStatus,
} from '@/types/api'

export const login = async (payload: LoginPayload): Promise<LoginResponse> =>
  (await apiClient.post<LoginResponse>('/auth/login/', payload)).data

export const logout = async (): Promise<void> => {
  await apiClient.post('/auth/logout/')
}

export const getCurrentUser = async (): Promise<UserAccount> =>
  (await apiClient.get<UserAccount>('/auth/me/')).data

export const changePassword = async (payload: {
  old_password: string
  new_password: string
}): Promise<{ token: string }> =>
  (await apiClient.post<{ token: string }>('/auth/change-password/', payload)).data

export const getUsers = async (params: PageParams = {}): Promise<PaginatedResponse<UserAccount>> =>
  (await apiClient.get<PaginatedResponse<UserAccount>>('/users/', { params })).data

export const createUser = async (payload: UserPayload): Promise<UserAccount> =>
  (await apiClient.post<UserAccount>('/users/', payload)).data

export const updateUser = async (id: number, payload: Partial<UserPayload>): Promise<UserAccount> =>
  (await apiClient.patch<UserAccount>(`/users/${id}/`, payload)).data

export const deleteUser = async (id: number): Promise<void> => {
  await apiClient.delete(`/users/${id}/`)
}

export const resetUserPassword = async (id: number, password: string): Promise<void> => {
  await apiClient.post(`/users/${id}/reset-password/`, { password })
}

export interface PageParams {
  page?: number
  page_size?: number
  search?: string
  [key: string]: string | number | boolean | undefined
}

export const getHealth = async (): Promise<HealthStatus> =>
  (await apiClient.get<HealthStatus>('/health/')).data

export const getProducts = async (params: PageParams = {}): Promise<PaginatedResponse<Product>> =>
  (await apiClient.get<PaginatedResponse<Product>>('/products/', { params })).data

export const getBrands = async (): Promise<
  PaginatedResponse<{ id: number; name: string; code: string }>
> => (await apiClient.get('/brands/', { params: { page_size: 100 } })).data

export const createBrand = async (payload: { name: string; code: string }) =>
  (await apiClient.post('/brands/', payload)).data

export const createProduct = async (payload: { brand_id: number; name: string }) =>
  (await apiClient.post<Product>('/products/', payload)).data

export const updateProduct = async (
  id: number,
  payload: Partial<{ name: string; series: string; model_code: string; is_active: boolean }>,
) => (await apiClient.patch<Product>(`/products/${id}/`, payload)).data

export const createSourceTarget = async (payload: {
  source: number
  product: number
  name: string
  target_type: 'COMMUNITY'
  target_url: string
  external_id: string
  is_active: boolean
}) => (await apiClient.post('/source-targets/', payload)).data

export const updateSourceTarget = async (
  id: number,
  payload: { target_url: string; external_id: string },
) => (await apiClient.patch(`/source-targets/${id}/`, payload)).data

export const validateSourceTarget = async (id: number) =>
  (await apiClient.post(`/source-targets/${id}/validate/`)).data

export const getSourceTargetCleanupPreview = async (
  id: number,
): Promise<SourceTargetCleanupPreview> =>
  (await apiClient.get<SourceTargetCleanupPreview>(`/source-targets/${id}/cleanup-preview/`)).data

export const cleanupSourceTarget = async (id: number, confirmation: string) =>
  (await apiClient.post(`/source-targets/${id}/cleanup/`, { confirmation })).data

export const getSources = async (params: PageParams = {}): Promise<PaginatedResponse<DataSource>> =>
  (await apiClient.get<PaginatedResponse<DataSource>>('/sources/', { params })).data

export const getCollectionTasks = async (
  params: PageParams = {},
): Promise<PaginatedResponse<CollectionTask>> =>
  (await apiClient.get<PaginatedResponse<CollectionTask>>('/collection-tasks/', { params })).data

export const stopCollectionTask = async (
  taskId: number,
): Promise<{ task_id: number; status: string }> =>
  (await apiClient.post<{ task_id: number; status: string }>(`/collection-tasks/${taskId}/stop/`))
    .data

export const recoverStaleCollectionTask = async (taskId: number): Promise<CollectionTask> =>
  (await apiClient.post<CollectionTask>(`/collection-tasks/${taskId}/recover-stale/`)).data

export const getCollectionTargets = async (
  params: PageParams = {},
): Promise<PaginatedResponse<CollectionTargetState>> =>
  (
    await apiClient.get<PaginatedResponse<CollectionTargetState>>('/collection-targets/', {
      params,
    })
  ).data

export const startSmartCollection = async (
  stateId: number,
): Promise<{
  task_id: number
  task_type?: 'FULL' | 'INCREMENTAL'
  existing?: boolean
  status: string
}> => (await apiClient.post(`/collection-targets/${stateId}/start-smart/`)).data

export const startFullCollection = async (stateId: number): Promise<CollectionTaskRunResponse> =>
  (await apiClient.post<CollectionTaskRunResponse>(`/collection-targets/${stateId}/start-full/`))
    .data

export const startIncrementalCollection = async (
  stateId: number,
): Promise<CollectionTaskRunResponse> =>
  (
    await apiClient.post<CollectionTaskRunResponse>(
      `/collection-targets/${stateId}/start-incremental/`,
    )
  ).data

export const createCollectionTask = async (payload: {
  source_target: number
  task_type: 'FULL' | 'INCREMENTAL'
  requested_limit?: number
  requested_pages?: number
}): Promise<CollectionTask> =>
  (await apiClient.post<CollectionTask>('/collection-tasks/', payload)).data

export const getCollectionTask = async (taskId: number): Promise<CollectionTask> =>
  (await apiClient.get<CollectionTask>(`/collection-tasks/${taskId}/`)).data

export const runCollectionTask = async (taskId: number): Promise<CollectionTaskRunResponse> =>
  (await apiClient.post<CollectionTaskRunResponse>(`/collection-tasks/${taskId}/run/`)).data

export const getCollectionSchedules = async (): Promise<PaginatedResponse<CollectionSchedule>> =>
  (
    await apiClient.get<PaginatedResponse<CollectionSchedule>>('/collection-schedules/', {
      params: { page_size: 100 },
    })
  ).data

export const saveCollectionSchedule = async (payload: {
  source_target: number
  enabled: boolean
  interval_hours: number
}): Promise<CollectionSchedule> =>
  (await apiClient.post<CollectionSchedule>('/collection-schedules/', payload)).data

export const getReviews = async (
  params: PageParams = {},
): Promise<PaginatedResponse<ReviewRecord>> =>
  (await apiClient.get<PaginatedResponse<ReviewRecord>>('/reviews/', { params })).data

export interface ReviewFacets {
  variants: { product_variant_id: number; product_variant__sku_name: string; count: number }[]
  regions: { source_region: string; count: number }[]
  ratings: { rating: string; count: number }[]
}
export const getReviewFacets = async (): Promise<ReviewFacets> =>
  (await apiClient.get<ReviewFacets>('/reviews/facets/')).data

export const getReviewMetadataCompleteness = async (
  params: PageParams = {},
): Promise<ReviewMetadataCompleteness> =>
  (await apiClient.get<ReviewMetadataCompleteness>('/reviews/metadata-completeness/', { params }))
    .data

export const getThreadTrees = async (params: PageParams = {}): Promise<ThreadPage> =>
  (await apiClient.get<ThreadPage>('/thread-trees/', { params })).data

export const getThreadTree = async (threadId: number): Promise<ThreadDetail> =>
  (await apiClient.get<ThreadDetail>(`/thread-trees/${threadId}/`)).data

export const getReviewQualities = async (
  params: PageParams = {},
): Promise<PaginatedResponse<ReviewQuality>> =>
  (await apiClient.get<PaginatedResponse<ReviewQuality>>('/review-quality/', { params })).data

export const getDataQualitySummary = async (params: PageParams = {}): Promise<DataQualitySummary> =>
  (await apiClient.get<DataQualitySummary>('/review-quality/summary/', { params })).data

export const overrideReviewQuality = async (
  qualityId: number,
  payload: { eligible: boolean; reason: string },
): Promise<ReviewQuality> =>
  (await apiClient.post<ReviewQuality>(`/review-quality/${qualityId}/override/`, payload)).data

export const getAnalysisSummary = async (): Promise<AnalysisSummary> =>
  (await apiClient.get<AnalysisSummary>('/analysis-results/summary/')).data

export const getAIConfiguration = async (): Promise<AIConfiguration> =>
  (await apiClient.get<AIConfiguration>('/analysis-batches/configuration/')).data

export const getOllamaModels = async (): Promise<{ models: string[] }> =>
  (await apiClient.get<{ models: string[] }>('/ai-configuration/ollama-models/')).data

export const getPersonalAIConfiguration = async (): Promise<PersonalAIConfiguration> =>
  (await apiClient.get<PersonalAIConfiguration>('/ai-configuration/')).data

export const savePersonalAIConfiguration = async (
  payload: AIConfigurationPayload,
): Promise<PersonalAIConfiguration> =>
  (await apiClient.put<PersonalAIConfiguration>('/ai-configuration/', payload)).data

export const testPersonalAIConfiguration = async (): Promise<AIConnectivityResult> =>
  (await apiClient.post<AIConnectivityResult>('/ai-configuration/test/')).data

export const getAnalysisResults = async (
  params: PageParams = {},
): Promise<PaginatedResponse<AnalysisResult>> =>
  (await apiClient.get<PaginatedResponse<AnalysisResult>>('/analysis-results/', { params })).data

export const getSamplePreview = async (sampleVersion: string): Promise<SamplePreview> =>
  (
    await apiClient.get<SamplePreview>('/analysis-results/sample-preview/', {
      params: { sample_version: sampleVersion },
    })
  ).data

export const getAnalysisBatches = async (): Promise<AnalysisBatch[]> =>
  (await apiClient.get<AnalysisBatch[]>('/analysis-batches/')).data

export const createAnalysisBatch = async (payload: {
  product_id: number
  source_id: number
  prompt_version: string
  limit: 20 | 100 | 278
  allow_large_run?: boolean
  force?: boolean
  retry_failed?: boolean
}): Promise<{ batch: AnalysisBatch; celery_task_id: string }> =>
  (
    await apiClient.post<{ batch: AnalysisBatch; celery_task_id: string }>(
      '/analysis-batches/',
      payload,
    )
  ).data

export const evaluateAnalysis = async (
  analysisId: number,
  payload: Omit<AnalysisEvaluation, 'evaluated_at'>,
): Promise<AnalysisEvaluation> =>
  (await apiClient.post<AnalysisEvaluation>(`/analysis-results/${analysisId}/evaluate/`, payload))
    .data

export interface StructuredRequestOptions {
  signal?: AbortSignal
  suppressGlobalError?: boolean
}

const structuredRequestConfig = (options: StructuredRequestOptions = {}) => ({
  signal: options.signal,
  skipGlobalError: options.suppressGlobalError ?? false,
})

export const getTaxonomy = async (
  options: StructuredRequestOptions = {},
): Promise<TaxonomyDefinition> =>
  (await apiClient.get<TaxonomyDefinition>('/taxonomies/', structuredRequestConfig(options))).data

export const getStructuredAnalyses = async (
  params: PageParams = {},
  options: StructuredRequestOptions = {},
): Promise<PaginatedResponse<StructuredAnalysisV1>> =>
  (
    await apiClient.get<PaginatedResponse<StructuredAnalysisV1>>('/structured-analyses/', {
      params,
      ...structuredRequestConfig(options),
    })
  ).data

export const reviewStructuredAnalysis = async (
  id: number,
  correctedResult: Record<string, unknown>,
  reviewReason: string,
): Promise<StructuredAnalysisV1> =>
  (
    await apiClient.post<StructuredAnalysisV1>(`/structured-analyses/${id}/review/`, {
      corrected_result: correctedResult,
      review_reason: reviewReason,
    })
  ).data

export const getStructuredQuality = async (
  params: PageParams = {},
  options: StructuredRequestOptions = {},
): Promise<StructuredQuality> =>
  (
    await apiClient.get<StructuredQuality>('/structured-analyses/quality/', {
      params,
      ...structuredRequestConfig(options),
    })
  ).data

export const getStructuredAggregates = async (
  params: PageParams = {},
  options: StructuredRequestOptions = {},
): Promise<StructuredAggregates> =>
  (
    await apiClient.get<StructuredAggregates>('/structured-analyses/aggregates/', {
      params,
      timeout: 60_000,
      ...structuredRequestConfig(options),
    })
  ).data

export const getStructuredBatches = async (
  params: PageParams = {},
  options: StructuredRequestOptions = {},
): Promise<PaginatedResponse<StructuredBatch>> =>
  (
    await apiClient.get<PaginatedResponse<StructuredBatch>>('/structured-batches/', {
      params,
      ...structuredRequestConfig(options),
    })
  ).data

export interface StructuredCorpusProgress {
  total: number
  completed: number
  remaining: number
  active: boolean
  batch: StructuredBatch | null
}

export const getStructuredCorpusProgress = async (
  productId: number,
  options: StructuredRequestOptions = {},
): Promise<StructuredCorpusProgress> =>
  (
    await apiClient.get('/structured-batches/progress/', {
      params: { product_id: productId },
      ...structuredRequestConfig(options),
    })
  ).data

export const runAllStructuredAnalysis = async (
  productId: number,
): Promise<{ queued: number; batch_id?: number; celery_task_id?: string; error_code?: string }> =>
  (await apiClient.post('/structured-batches/run-all/', { product_id: productId })).data

export const retryRemainingStructuredAnalysis = async (
  productId: number,
): Promise<{ queued: number; batch_ids: number[] }> =>
  (await apiClient.post('/structured-batches/retry-remaining/', { product_id: productId })).data

export const createStructuredBatch = async (payload: {
  product_id?: number | null
  source_id?: number | null
  content_ids?: number[]
  max_items: number
  dry_run: boolean
  max_concurrency: number
  requests_per_minute: number
  token_limit?: number
  cost_budget?: number
}): Promise<{
  batch: StructuredBatch
  celery_task_id: string | null
  matched_content_ids: number[]
}> => (await apiClient.post('/structured-batches/', payload)).data

export const cancelStructuredBatch = async (id: number): Promise<StructuredBatch> =>
  (await apiClient.post<StructuredBatch>(`/structured-batches/${id}/cancel/`)).data

export const pauseStructuredBatch = async (id: number): Promise<StructuredBatch> =>
  (await apiClient.post<StructuredBatch>(`/structured-batches/${id}/pause/`)).data

export const resumeStructuredBatch = async (id: number): Promise<{ batch: StructuredBatch }> =>
  (await apiClient.post(`/structured-batches/${id}/resume/`)).data

export const retryStructuredBatch = async (id: number): Promise<{ batch: StructuredBatch }> =>
  (await apiClient.post(`/structured-batches/${id}/retry-failed/`)).data

export const processGovernanceBatch = async (payload: {
  product_id: number
  source_id?: number
  limit: number
  dry_run: boolean
}): Promise<{ total: number; eligible: number; excluded: number; dry_run: boolean }> =>
  (await apiClient.post('/review-quality/process-batch/', payload)).data

export interface GovernanceTaskInfo {
  id: number
  status: 'PENDING' | 'RUNNING' | 'SUCCESS' | 'PARTIAL' | 'FAILED'
  product_id: number
  source_id: number | null
  total: number
  processed: number
  eligible: number
  excluded: number
  reused: number
  failed: number
  failures: { review_id: number; error_type: string }[]
  error_message: string
  created_at: string
  started_at: string | null
  finished_at: string | null
}

export interface GovernancePage<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

export const startAsyncGovernance = async (payload: {
  product_id: number
  source_id?: number
  limit: number
  dry_run: false
}): Promise<{ task: GovernanceTaskInfo }> =>
  (await apiClient.post('/review-quality/start-async/', payload)).data

export const startFullGovernance = async (payload: {
  product_id: number
  source_id?: number | null
}): Promise<{ task?: GovernanceTaskInfo; total?: number; detail?: string }> =>
  (await apiClient.post('/review-quality/start-full/', payload)).data

export const getGovernanceTaskHistory = async (params: {
  product_id?: number
  page?: number
  page_size?: number
}): Promise<GovernancePage<GovernanceTaskInfo>> =>
  (await apiClient.get('/review-quality/task-history/', { params })).data

export const getGovernanceTaskStatus = async (taskId: number): Promise<GovernanceTaskInfo> =>
  (await apiClient.get('/review-quality/async-status/', { params: { task_id: taskId } })).data

export const retryGovernanceTask = async (taskId: number): Promise<{ task: GovernanceTaskInfo }> =>
  (await apiClient.post('/review-quality/retry-failed/', { task_id: taskId })).data

export interface GovernanceAIBatchInfo {
  id: number
  product_id: number
  source_id: number | null
  automatic: boolean
  status: 'PENDING' | 'RUNNING' | 'SUCCESS' | 'PARTIAL' | 'FAILED'
  total: number
  processed: number
  succeeded: number
  accepted: number
  rejected: number
  uncertain: number
  review_required: number
  failed: number
  prompt_tokens: number
  completion_tokens: number
  error_code: string
}

export interface GovernanceAIResultInfo {
  id: number
  review_id: number
  status:
    | 'PENDING'
    | 'ACCEPTED'
    | 'REJECTED'
    | 'UNCERTAIN'
    | 'ERROR'
    | 'SUCCEEDED'
    | 'REVIEW_REQUIRED'
    | 'FAILED'
  rule_eligible: boolean
  ai_eligible: boolean | null
  confidence: number | null
  reason: string
  evidence: string
  model: string
  error_code: string
  attempt_count: number
  prompt_tokens: number
  completion_tokens: number
  human_decision: boolean | null
  human_reviewed_at: string | null
}

export const startGovernanceAIReview = async (payload: {
  product_id: number
  source_id?: number | null
  limit: number
}): Promise<{ id: number; total: number }> =>
  (await apiClient.post('/governance-ai/start/', payload)).data

export const startFullGovernanceAIReview = async (payload: {
  product_id: number
  source_id?: number | null
}): Promise<{ id?: number; total: number; automatic?: boolean; detail?: string }> =>
  (await apiClient.post('/governance-ai/start-full/', payload)).data

export interface AICorpusSummary {
  total: number
  rule_eligible: number
  rule_excluded: number
  ai_accepted: number
  ai_rejected: number
  ai_uncertain: number
  ai_failed: number
  ai_unprocessed: number
  final_eligible: number
}

export const getAICorpusSummary = async (
  product_id: number,
  source_id?: number,
): Promise<AICorpusSummary> =>
  (await apiClient.get('/governance-ai/corpus-summary/', { params: { product_id, source_id } }))
    .data

export interface FullGovernanceAIProgress {
  id: number
  status: 'RUNNING' | 'STOPPING' | 'STOPPED' | 'COMPLETED'
  can_stop: boolean
  total: number
  processed: number
  remaining: number
  failed: number
  accepted: number
  rejected: number
  uncertain: number
  prompt_tokens: number
  completion_tokens: number
}

export const getFullGovernanceAIProgress = async (params: {
  product_id: number
  source_id?: number
}): Promise<FullGovernanceAIProgress | null> => {
  try {
    return (await apiClient.get('/governance-ai/full-progress/', { params })).data
  } catch (error: unknown) {
    if (axios.isAxiosError(error) && error.response?.status === 404) return null
    throw error
  }
}

export const stopFullGovernanceAI = async (id: number): Promise<void> => {
  await apiClient.post('/governance-ai/stop-full/', { id })
}

export const getGovernanceAIHistory = async (params: {
  product_id?: number
  source_id?: number
  page?: number
  page_size?: number
}): Promise<GovernancePage<GovernanceAIBatchInfo>> =>
  (await apiClient.get('/governance-ai/history/', { params })).data

export const getGovernanceAIResults = async (
  productId: number,
  params: { source_id?: number; page?: number; page_size?: number } = {},
): Promise<GovernancePage<GovernanceAIResultInfo>> =>
  (
    await apiClient.get('/governance-ai/results/', {
      params: { ...params, product_id: productId },
    })
  ).data

export const confirmGovernanceAIReview = async (payload: {
  review_id: number
  eligible: boolean
  reason: string
}): Promise<{ confirmed: boolean }> =>
  (await apiClient.post('/governance-ai/confirm/', payload)).data

export const retryGovernanceAIBatch = async (
  batchId: number,
): Promise<{ id: number; total: number }> =>
  (await apiClient.post('/governance-ai/retry-failed/', { batch_id: batchId })).data

export const getDashboardOverview = async (
  params: DashboardFilters = {},
): Promise<DashboardOverview> =>
  (await apiClient.get<DashboardOverview>('/dashboard/overview/', { params })).data

export const getDashboardTrends = async (
  params: DashboardFilters = {},
): Promise<DashboardTrend[]> =>
  (await apiClient.get<{ results: DashboardTrend[] }>('/dashboard/trends/', { params })).data
    .results

export const getDashboardCategories = async (
  params: DashboardFilters = {},
): Promise<DashboardCategory[]> =>
  (await apiClient.get<{ results: DashboardCategory[] }>('/dashboard/categories/', { params })).data
    .results

export const getDashboardProducts = async (
  params: DashboardFilters = {},
): Promise<DashboardProductSummary[]> =>
  (await apiClient.get<{ results: DashboardProductSummary[] }>('/dashboard/products/', { params }))
    .data.results

export const getDashboardComparison = async (
  params: DashboardFilters & { left_product_id?: number; right_product_id?: number },
): Promise<DashboardComparison> =>
  (await apiClient.get<DashboardComparison>('/dashboard/comparison/', { params })).data

export const getDashboardIssues = async (
  params: DashboardFilters & {
    category?: string
    severity?: string
    search?: string
    ordering?: string
    page?: number
    page_size?: number
  } = {},
): Promise<PaginatedResponse<DashboardIssue>> =>
  (await apiClient.get<PaginatedResponse<DashboardIssue>>('/dashboard/issues/', { params })).data

export const getDashboardIssue = async (
  id: string,
  params: DashboardFilters = {},
): Promise<DashboardIssueDetail> =>
  (
    await apiClient.get<DashboardIssueDetail>(`/dashboard/issues/${encodeURIComponent(id)}/`, {
      params,
    })
  ).data

export const getInsightReports = async (
  params: {
    report_type?: 'DAILY' | 'WEEKLY'
    product_id?: number
    page?: number
    page_size?: number
  } = {},
): Promise<PaginatedResponse<InsightReport>> =>
  (await apiClient.get<PaginatedResponse<InsightReport>>('/dashboard/reports/', { params })).data

export const getInsightReport = async (id: number): Promise<InsightReport> =>
  (await apiClient.get<InsightReport>(`/dashboard/reports/${id}/`)).data

export const getOperationsStatus = async (): Promise<OperationsStatus> =>
  (await apiClient.get<OperationsStatus>('/dashboard/operations/')).data

export const getAssistantModels = async (): Promise<AssistantModelList> =>
  (await apiClient.get<AssistantModelList>('/assistant/models/')).data

export const createAssistantModel = async (
  payload: AssistantModelProfilePayload,
): Promise<AssistantModelProfile> =>
  (await apiClient.post<AssistantModelProfile>('/assistant/models/', payload)).data

export const updateAssistantModel = async (
  id: number,
  payload: Partial<AssistantModelProfilePayload>,
): Promise<AssistantModelProfile> =>
  (await apiClient.patch<AssistantModelProfile>(`/assistant/models/${id}/`, payload)).data

export const deleteAssistantModel = async (id: number): Promise<void> => {
  await apiClient.delete(`/assistant/models/${id}/`)
}

export const testAssistantModel = async (
  id: number,
): Promise<{ status: string; model: string; latency_ms: number }> =>
  (
    await apiClient.post<{ status: string; model: string; latency_ms: number }>(
      `/assistant/models/${id}/test/`,
    )
  ).data

export const getAssistantOllamaModels = async (id: number): Promise<string[]> =>
  (await apiClient.get<{ models: string[] }>(`/assistant/models/${id}/ollama-models/`)).data.models

export const getAssistantConversations = async (): Promise<AssistantConversation[]> => {
  const response = await apiClient.get<PaginatedResponse<AssistantConversation>>(
    '/assistant/conversations/',
    { params: { page_size: 100 } },
  )
  return response.data.results
}

export const createAssistantConversation = async (payload: {
  title?: string
  model_profile?: number | null
  use_default_model?: boolean
  context?: Record<string, unknown>
}): Promise<AssistantConversation> =>
  (await apiClient.post<AssistantConversation>('/assistant/conversations/', payload)).data

export const updateAssistantConversation = async (
  id: string,
  payload: Partial<
    Pick<AssistantConversation, 'title' | 'model_profile' | 'use_default_model' | 'context'>
  >,
): Promise<AssistantConversation> =>
  (await apiClient.patch<AssistantConversation>(`/assistant/conversations/${id}/`, payload)).data

export const deleteAssistantConversation = async (id: string): Promise<void> => {
  await apiClient.delete(`/assistant/conversations/${id}/`)
}

export const getAssistantMessages = async (id: string): Promise<AssistantMessage[]> =>
  (await apiClient.get<{ results: AssistantMessage[] }>(`/assistant/conversations/${id}/messages/`))
    .data.results

export const cancelAssistantChat = async (
  id: string,
): Promise<{ status: string; request_id?: string }> =>
  (
    await apiClient.post<{ status: string; request_id?: string }>(
      `/assistant/conversations/${id}/cancel/`,
    )
  ).data

function assistantApiUrl(path: string): string {
  const base = import.meta.env.DEV ? '/api/v1' : import.meta.env.VITE_API_BASE_URL || '/api/v1'
  return `${base}${path}`
}

export async function streamAssistantChat(
  conversationId: string,
  payload: {
    request_id: string
    content: string
    product_id?: number
    source_id?: number
    start_date?: string
    end_date?: string
  },
  onEvent: (event: AssistantStreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const token = window.localStorage.getItem(AUTH_TOKEN_STORAGE_KEY)
  const response = await fetch(
    assistantApiUrl(`/assistant/conversations/${conversationId}/chat/`),
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'text/event-stream',
        ...(token ? { Authorization: `Token ${token}` } : {}),
      },
      body: JSON.stringify(payload),
      signal,
    },
  )
  if (!response.ok) {
    const data = (await response.json().catch(() => ({}))) as { detail?: string }
    throw new Error(data.detail || `助手请求失败（HTTP ${response.status}）`)
  }
  if (!response.body) throw new Error('浏览器未提供流式响应。')
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { value, done } = await reader.read()
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done })
    const blocks = buffer.split('\n\n')
    buffer = blocks.pop() || ''
    for (const block of blocks) {
      const line = block.split('\n').find((item) => item.startsWith('data:'))
      if (!line) continue
      onEvent(JSON.parse(line.slice(5).trim()) as AssistantStreamEvent)
    }
    if (done) break
  }
}
