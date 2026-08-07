import axios, { AxiosError } from 'axios'
import { ElMessage } from 'element-plus'

const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api/v1',
  timeout: 10_000,
  headers: {
    Accept: 'application/json',
  },
})

apiClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError<{ detail?: string }>) => {
    const detail = error.response?.data?.detail
    const message = typeof detail === 'string' ? detail : 'API 请求失败，请检查后端服务状态'
    ElMessage.error(message)
    return Promise.reject(error)
  },
)

export default apiClient
