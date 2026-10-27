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
  ThreadDetail,
  ThreadPage,
  ReviewQuality,
  ReviewRecord,
  UserAccount,
  UserPayload,
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

export const getSources = async (params: PageParams = {}): Promise<PaginatedResponse<DataSource>> =>
  (await apiClient.get<PaginatedResponse<DataSource>>('/sources/', { params })).data

export const getCollectionTasks = async (
  params: PageParams = {},
): Promise<PaginatedResponse<CollectionTask>> =>
  (await apiClient.get<PaginatedResponse<CollectionTask>>('/collection-tasks/', { params })).data

export const createCollectionTask = async (payload: {
  source_target: number
  task_type: 'FULL' | 'INCREMENTAL'
  requested_limit?: number
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
