import { http, type ApiResponse } from '@/api/http'

export interface UploadedAttachment {
  attachment_id: string
  file_name: string
  file_path: string
  mime_type: string
  file_size: number
  parse_status: string
}

export async function uploadAttachment(
  conversationId: string,
  file: File,
): Promise<UploadedAttachment> {
  const form = new FormData()
  form.append('conversation_id', conversationId)
  form.append('file', file)
  const response = await http.post<ApiResponse<UploadedAttachment>>('/attachment/upload', form, {
    timeout: 60_000,
  })
  return response.data.data
}

export async function deleteAttachment(attachmentId: string): Promise<void> {
  await http.post('/attachment/delete', { attachment_id: attachmentId })
}
