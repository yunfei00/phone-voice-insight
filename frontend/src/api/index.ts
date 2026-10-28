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
  TaxonomyDefinition,
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

export const stopCollectionTask = async (taskId: number): Promise<{ task_id: number; status: string }> =>
  (await apiClient.post<{ task_id: number; status: string }>(`/collection-tasks/${taskId}/stop/`)).data

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

export const getTaxonomy = async (): Promise<TaxonomyDefinition> =>
  (await apiClient.get<TaxonomyDefinition>('/taxonomies/')).data

export const getStructuredAnalyses = async (
  params: PageParams = {},
): Promise<PaginatedResponse<StructuredAnalysisV1>> =>
  (
    await apiClient.get<PaginatedResponse<StructuredAnalysisV1>>('/structured-analyses/', {
      params,
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

export const getStructuredQuality = async (): Promise<StructuredQuality> =>
  (await apiClient.get<StructuredQuality>('/structured-analyses/quality/')).data

export const getStructuredBatches = async (
  params: PageParams = {},
): Promise<PaginatedResponse<StructuredBatch>> =>
  (await apiClient.get<PaginatedResponse<StructuredBatch>>('/structured-batches/', { params })).data

export const createStructuredBatch = async (payload: {
  product_id?: number
  source_id?: number
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

export const processGovernanceBatch = async (payload: { product_id: number; limit: number; dry_run: boolean }): Promise<{ total: number; eligible: number; excluded: number; dry_run: boolean }> =>
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

export const startAsyncGovernance = async (payload: {
  product_id: number
  limit: number
  dry_run: false
}): Promise<{ task: GovernanceTaskInfo }> =>
  (await apiClient.post('/review-quality/start-async/', payload)).data

export const getGovernanceTaskHistory = async (): Promise<{ results: GovernanceTaskInfo[] }> =>
  (await apiClient.get('/review-quality/task-history/')).data

export const getGovernanceTaskStatus = async (taskId: number): Promise<GovernanceTaskInfo> =>
  (await apiClient.get('/review-quality/async-status/', { params: { task_id: taskId } })).data

export const retryGovernanceTask = async (taskId: number): Promise<{ task: GovernanceTaskInfo }> =>
  (await apiClient.post('/review-quality/retry-failed/', { task_id: taskId })).data


export interface GovernanceAIBatchInfo {
  id: number
  status: 'PENDING' | 'RUNNING' | 'SUCCESS' | 'PARTIAL' | 'FAILED'
  total: number
  processed: number
  succeeded: number
  review_required: number
  failed: number
}

export interface GovernanceAIResultInfo {
  id: number
  review_id: number
  status: 'PENDING' | 'SUCCEEDED' | 'REVIEW_REQUIRED' | 'FAILED'
  rule_eligible: boolean
  ai_eligible: boolean | null
  confidence: number | null
  reason: string
  evidence: string
  model: string
}

export const startGovernanceAIReview = async (payload: { product_id: number; limit: number }): Promise<{ id: number; total: number }> =>
  (await apiClient.post('/governance-ai/start/', payload)).data

export const getGovernanceAIHistory = async (): Promise<{ results: GovernanceAIBatchInfo[] }> =>
  (await apiClient.get('/governance-ai/history/')).data

export const getGovernanceAIResults = async (productId: number): Promise<{ results: GovernanceAIResultInfo[] }> =>
  (await apiClient.get('/governance-ai/results/', { params: { product_id: productId } })).data
