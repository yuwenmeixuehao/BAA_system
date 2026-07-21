import { http, type ApiResponse } from '@/api/http'
import type { AdminTaskLogItem } from '@/types/admin'

export interface AdminLogFilters {
  task_id?: string
  trace_id?: string
  level?: 'info' | 'warning' | 'error'
  limit?: number
}

export async function listAdminLogs(filters: AdminLogFilters): Promise<AdminTaskLogItem[]> {
  const response = await http.get<ApiResponse<{ items: AdminTaskLogItem[] }>>('/admin/logs', {
    params: filters,
  })
  return response.data.data.items
}
