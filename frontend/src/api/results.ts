import { http, type ApiResponse } from '@/api/http'
import type { AnalysisResult, ReportExportFormat } from '@/types/report'

export async function getResult(taskId: string): Promise<AnalysisResult> {
  const response = await http.get<ApiResponse<AnalysisResult>>(`/results/${taskId}`)
  return response.data.data
}

export async function downloadResult(
  taskId: string,
  format: ReportExportFormat,
  fileName: string,
): Promise<void> {
  const response = await http.get<Blob>(`/results/${taskId}/export`, {
    params: { format },
    responseType: 'blob',
  })
  const url = URL.createObjectURL(response.data)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = fileName
  anchor.click()
  URL.revokeObjectURL(url)
}
