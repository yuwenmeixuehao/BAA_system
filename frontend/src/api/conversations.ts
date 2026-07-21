import { http, type ApiResponse } from '@/api/http'
import type { Conversation, CursorPage, MessagePage } from '@/types/conversation'
import type { WebsocketToken } from '@/types/websocket'

export async function listConversations(cursor?: string): Promise<CursorPage<Conversation>> {
  const response = await http.get<ApiResponse<CursorPage<Conversation>>>('/chat/ls', {
    params: { cursor, limit: 30 },
  })
  return response.data.data
}

export async function createConversation(title?: string): Promise<Conversation> {
  const response = await http.post<ApiResponse<Conversation>>('/chat/create', { title })
  return response.data.data
}

export async function updateConversation(
  conversationId: string,
  changes: { title?: string; status?: 'active' | 'archived' },
): Promise<Conversation> {
  const response = await http.post<ApiResponse<Conversation>>('/chat/update', {
    conversation_id: conversationId,
    ...changes,
  })
  return response.data.data
}

export async function deleteConversations(conversationIds: string[]): Promise<void> {
  await http.post('/chat/delete', { conversation_ids: conversationIds })
}

export async function listMessages(conversationId: string, cursor?: string): Promise<MessagePage> {
  const response = await http.get<ApiResponse<MessagePage>>(`/chat/ls/${conversationId}`, {
    params: { cursor, limit: 50 },
  })
  return response.data.data
}

export async function createWebsocketToken(conversationId: string): Promise<WebsocketToken> {
  const response = await http.post<ApiResponse<WebsocketToken>>('/chat/ws-token', {
    conversation_id: conversationId,
  })
  return response.data.data
}
