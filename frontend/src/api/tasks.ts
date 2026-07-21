import { http, type ApiResponse } from '@/api/http'
import type { CancelTaskResult, TaskSummary } from '@/types/task'
import type { ServerEvent } from '@/types/websocket'

export async function getTask(taskId: string): Promise<TaskSummary> {
  const response = await http.get<ApiResponse<TaskSummary>>(`/tasks/${taskId}`)
  return response.data.data
}

export async function cancelTask(taskId: string): Promise<CancelTaskResult> {
  const response = await http.post<ApiResponse<CancelTaskResult>>(`/tasks/${taskId}/cancel`)
  return response.data.data
}

export async function retryTask(taskId: string): Promise<TaskSummary> {
  const response = await http.post<ApiResponse<TaskSummary>>(`/tasks/${taskId}/retry`)
  return response.data.data
}

export async function listTaskEvents(taskId: string, afterSeq = 0): Promise<ServerEvent[]> {
  const response = await http.get<
    ApiResponse<{ items: ServerEvent[]; last_event_seq: number }>
  >(`/tasks/${taskId}/events`, { params: { after_seq: afterSeq } })
  return response.data.data.items
}
