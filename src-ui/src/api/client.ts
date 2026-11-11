import axios, { AxiosInstance, AxiosRequestConfig } from 'axios'
import { getApiBaseUrl, resolveApiBaseUrl, getSessionToken } from './baseUrl'

class ApiClient {
  private client: AxiosInstance

  constructor() {
    this.client = axios.create({
      baseURL: getApiBaseUrl(),
      timeout: 30000,
      headers: {
        'Content-Type': 'application/json',
      },
    })

    // 请求拦截器：每次请求都从 baseUrl 模块取最新值，
    // 避免 ApiClient 在 baseURL 解析完成前实例化导致使用空串/旧值
    this.client.interceptors.request.use(
      async (config) => {
        await resolveApiBaseUrl()
        config.headers.Authorization = `Bearer ${getSessionToken()}`
        config.baseURL = getApiBaseUrl()
        return config
      },
      (error) => {
        return Promise.reject(error)
      }
    )

    // 响应拦截器
    this.client.interceptors.response.use(
      (response) => response.data,
      async (error) => {
        if (error.config && !error.config._retried && (!error.response || error.response.status === 401)) {
          error.config._retried = true
          await resolveApiBaseUrl(true)
          return this.client.request(error.config)
        }
        console.error('API Error:', error)
        return Promise.reject(error)
      }
    )
  }

  async get<T>(url: string, config?: AxiosRequestConfig): Promise<T> {
    return this.client.get(url, config)
  }

  async post<T>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T> {
    return this.client.post(url, data, config)
  }

  async put<T>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T> {
    return this.client.put(url, data, config)
  }

  async delete<T>(url: string, config?: AxiosRequestConfig): Promise<T> {
    return this.client.delete(url, config)
  }
}

export const apiClient = new ApiClient()
