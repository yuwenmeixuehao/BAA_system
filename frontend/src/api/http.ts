import axios from 'axios'

export interface ApiResponse<T> {
  code: string
  message: string
  data: T
  trace_id: string
}

export const http = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api',
  timeout: 15_000,
  withCredentials: true,
})

http.interceptors.response.use(
  (response) => response,
  (error: unknown) => Promise.reject(error),
)
