import axios, { AxiosError } from 'axios'
import { ElMessage } from 'element-plus'

import { AUTH_TOKEN_STORAGE_KEY } from '@/config/auth'

const apiClient = axios.create({
  baseURL: import.meta.env.DEV ? '/api/v1' : import.meta.env.VITE_API_BASE_URL || '/api/v1',
  timeout: 60_000,
  headers: {
    Accept: 'application/json',
  },
})

apiClient.interceptors.request.use((config) => {
  const token = window.localStorage.getItem(AUTH_TOKEN_STORAGE_KEY)
  if (token) config.headers.Authorization = `Token ${token}`
  return config
})

apiClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError<{ detail?: string | Record<string, unknown> }>) => {
    const detail = error.response?.data?.detail
    const nestedDetail = detail && typeof detail === 'object' ? detail.detail : undefined
    const message =
      typeof detail === 'string'
        ? detail
        : typeof nestedDetail === 'string'
          ? nestedDetail
          : 'API 请求失败，请检查后端服务状态'
    ElMessage.error(message)
    if (error.response?.status === 401 && !error.config?.url?.includes('/auth/login/')) {
      window.localStorage.removeItem(AUTH_TOKEN_STORAGE_KEY)
      const base = import.meta.env.BASE_URL || '/'
      window.location.assign(`${base}login`)
    }
    return Promise.reject(error)
  },
)

export default apiClient
