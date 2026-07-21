import { createWebsocketToken } from '@/api/conversations'
import { cancelTask as cancelTaskRequest } from '@/api/tasks'
import { useChatStore } from '@/stores/chat'
import { useTaskStore } from '@/stores/task'
import type { ServerEvent } from '@/types/websocket'

export function useWebSocket() {
  const chatStore = useChatStore()
  const taskStore = useTaskStore()
  let socket: WebSocket | null = null
  let heartbeatTimer: number | null = null
  let reconnectTimer: number | null = null
  let reconnectAttempts = 0
  let generation = 0
  let manuallyClosed = true

  function websocketUrl(conversationId: string, token: string): string {
    const base = import.meta.env.VITE_SERVER_BASE_URL || window.location.origin
    const url = new URL('/api/chat/ws/chat', base)
    url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
    url.searchParams.set('websocket_token', token)
    url.searchParams.set('conversation_id', conversationId)
    return url.toString()
  }

  async function connect(conversationId: string): Promise<void> {
    disconnect(false)
    manuallyClosed = false
    const currentGeneration = ++generation
    chatStore.connecting = true
    chatStore.connectionError = null
    try {
      const token = await createWebsocketToken(conversationId)
      if (currentGeneration !== generation || manuallyClosed) return
      socket = new WebSocket(websocketUrl(conversationId, token.websocket_token))
      socket.onopen = () => {
        if (currentGeneration !== generation) return
        reconnectAttempts = 0
        chatStore.connected = true
        chatStore.connecting = false
        heartbeatTimer = window.setInterval(() => sendRaw({ type: 'ping' }), 25_000)
        if (taskStore.activeTaskId) {
          sendRaw({
            type: 'resume_task',
            task_id: taskStore.activeTaskId,
            after_seq: chatStore.lastSeqForTask(taskStore.activeTaskId),
          })
        }
      }
      socket.onmessage = (message) => {
        const event = JSON.parse(String(message.data)) as ServerEvent | { type: 'pong' }
        if (event.type === 'pong') return
        const previousTaskId = taskStore.activeTaskId
        chatStore.applyEvent(event)
        if (event.task_id && event.task_id !== previousTaskId) {
          void taskStore.load(event.task_id)
        } else if (event.type === 'done' && event.task_id) {
          void taskStore.load(event.task_id)
        }
      }
      socket.onerror = () => {
        chatStore.connectionError = '实时连接发生异常'
      }
      socket.onclose = () => {
        clearHeartbeat()
        chatStore.connected = false
        chatStore.connecting = false
        if (!manuallyClosed && currentGeneration === generation) {
          scheduleReconnect(conversationId)
        }
      }
    } catch {
      chatStore.connecting = false
      chatStore.connectionError = '无法建立实时连接，正在重试'
      if (!manuallyClosed && currentGeneration === generation) scheduleReconnect(conversationId)
    }
  }

  function scheduleReconnect(conversationId: string): void {
    if (reconnectTimer !== null) return
    const delay = Math.min(30_000, 1000 * 2 ** reconnectAttempts)
    reconnectAttempts += 1
    reconnectTimer = window.setTimeout(() => {
      reconnectTimer = null
      void connect(conversationId)
    }, delay)
  }

  function sendMessage(content: string): void {
    const normalized = content.trim()
    if (!normalized || !chatStore.activeConversationId) return
    if (taskStore.status === 'waiting_input' && taskStore.activeTaskId) {
      const clientMsgId = crypto.randomUUID()
      const sent = sendRaw({
        type: 'clarification_response',
        task_id: taskStore.activeTaskId,
        content: normalized,
      })
      if (!sent) return
      chatStore.addOptimisticMessage(normalized, clientMsgId, false)
    } else {
      const clientMsgId = crypto.randomUUID()
      const attachments = [...chatStore.composerAttachments]
      const sent = sendRaw({
        type: 'user_message',
        conversation_id: chatStore.activeConversationId,
        client_msg_id: clientMsgId,
        content: normalized,
        attachment_ids: attachments.map((attachment) => attachment.attachment_id),
      })
      if (!sent) return
      chatStore.addOptimisticMessage(normalized, clientMsgId, true, attachments)
      chatStore.composerAttachments = []
    }
    chatStore.draft = ''
  }

  function cancelTask(): void {
    const taskId = taskStore.activeTaskId
    if (!taskId) return
    if (!sendRaw({ type: 'cancel_task', task_id: taskId })) {
      void cancelTaskRequest(taskId).then(() => taskStore.load(taskId))
    }
  }

  function sendRaw(payload: object): boolean {
    if (socket?.readyState !== WebSocket.OPEN) {
      chatStore.connectionError = '实时连接尚未就绪'
      return false
    }
    socket.send(JSON.stringify(payload))
    return true
  }

  function clearHeartbeat(): void {
    if (heartbeatTimer !== null) window.clearInterval(heartbeatTimer)
    heartbeatTimer = null
  }

  function disconnect(markManual = true): void {
    manuallyClosed = markManual
    generation += 1
    clearHeartbeat()
    if (reconnectTimer !== null) window.clearTimeout(reconnectTimer)
    reconnectTimer = null
    if (socket) {
      socket.onclose = null
      socket.close()
    }
    socket = null
    chatStore.connected = false
    chatStore.connecting = false
  }

  return { cancelTask, connect, disconnect, sendMessage }
}
