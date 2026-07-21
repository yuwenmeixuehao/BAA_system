import axios from 'axios'

import { http, type ApiResponse } from '@/api/http'
import type { CurrentUser } from '@/types/auth'

const authHttp = axios.create({
  baseURL: import.meta.env.VITE_SERVER_BASE_URL || '',
  timeout: 15_000,
  withCredentials: true,
})

export async function getCurrentUser(): Promise<CurrentUser> {
  const response = await http.get<ApiResponse<CurrentUser>>('/me')
  return response.data.data
}

export function startLogin(next = '/workbench'): void {
  const base = import.meta.env.VITE_SERVER_BASE_URL || ''
  window.location.assign(`${base}/auth/login?next=${encodeURIComponent(next)}`)
}

export async function logout(): Promise<void> {
  await authHttp.post('/auth/logout')
}
