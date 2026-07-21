import { defineStore } from 'pinia'
import { ref } from 'vue'

import { listMessages } from '@/api/conversations'
import {
  deleteAttachment,
  uploadAttachment,
  type UploadedAttachment,
} from '@/api/attachments'
import { useTaskStore } from '@/stores/task'
import type { Message } from '@/types/conversation'
import type { ServerEvent } from '@/types/websocket'

export const useChatStore = defineStore('chat', () => {
  const messages = ref<Message[]>([])
  const streamingMessageId = ref<string | null>(null)
  const draft = ref('')
  const connected = ref(false)
  const connecting = ref(false)
  const connectionError = ref<string | null>(null)
  const activeConversationId = ref<string | null>(null)
  const lastEventSeq = ref(0)
  const eventSeqByTask = ref<Record<string, number>>({})
  const loading = ref(false)
  const composerAttachments = ref<UploadedAttachment[]>([])
  const uploadingAttachment = ref(false)

  async function loadHistory(conversationId: string): Promise<void> {
    activeConversationId.value = conversationId
    loading.value = true
    try {
      const page = await listMessages(conversationId)
      if (activeConversationId.value === conversationId) messages.value = page.items
    } finally {
      loading.value = false
    }
  }

  function addOptimisticMessage(
    content: string,
    clientMsgId: string,
    pending = true,
    attachments: UploadedAttachment[] = [],
  ): void {
    messages.value.push({
      message_id: `pending:${clientMsgId}`,
      task_id: null,
      client_msg_id: clientMsgId,
      seq_no: Number.MAX_SAFE_INTEGER,
      role: 'user',
      message_type: 'text',
      content,
      attachments: attachments.map((attachment) => ({
        attachment_id: attachment.attachment_id,
        file_name: attachment.file_name,
        file_type: attachment.mime_type,
        file_size: attachment.file_size,
        parse_status: attachment.parse_status,
      })),
      created_at: new Date().toISOString(),
      pending,
    })
  }

  async function addComposerAttachment(conversationId: string, file: File): Promise<void> {
    uploadingAttachment.value = true
    connectionError.value = null
    try {
      const attachment = await uploadAttachment(conversationId, file)
      composerAttachments.value.push(attachment)
    } catch {
      connectionError.value = `附件 ${file.name} 上传失败`
    } finally {
      uploadingAttachment.value = false
    }
  }

  async function removeComposerAttachment(attachmentId: string): Promise<void> {
    const index = composerAttachments.value.findIndex(
      (attachment) => attachment.attachment_id === attachmentId,
    )
    if (index < 0) return
    try {
      await deleteAttachment(attachmentId)
      composerAttachments.value.splice(index, 1)
    } catch {
      connectionError.value = '附件删除失败'
    }
  }

  function applyEvent(event: ServerEvent): void {
    const taskStore = useTaskStore()
    if (event.event_seq > 0 && event.task_id) {
      const previous = eventSeqByTask.value[event.task_id] ?? 0
      if (event.event_seq <= previous) return
      eventSeqByTask.value[event.task_id] = event.event_seq
      lastEventSeq.value = event.event_seq
    }
    taskStore.applyEvent(event)
    if (event.type === 'message_start') {
      const clientMsgId = event.payload.client_msg_id
      const messageId = event.payload.message_id
      const optimistic = messages.value.find(
        (message) => message.client_msg_id === clientMsgId || message.message_id === messageId,
      )
      if (optimistic) {
        optimistic.message_id = messageId ?? optimistic.message_id
        optimistic.task_id = event.task_id
        if (typeof event.payload.seq_no === 'number') optimistic.seq_no = event.payload.seq_no
        optimistic.pending = false
      }
    } else if (event.type === 'message_delta') {
      const messageId = event.payload.message_id
      if (!messageId) return
      let message = messages.value.find((item) => item.message_id === messageId)
      if (!message) {
        message = {
          message_id: messageId,
          task_id: event.task_id,
          client_msg_id: null,
          seq_no:
            typeof event.payload.seq_no === 'number'
              ? event.payload.seq_no
              : Number.MAX_SAFE_INTEGER,
          role: 'assistant',
          message_type: 'text',
          content: '',
          attachments: [],
          created_at: event.occurred_at ?? new Date().toISOString(),
        }
        messages.value.push(message)
      }
      if (typeof event.payload.seq_no === 'number') message.seq_no = event.payload.seq_no
      message.content = `${message.content ?? ''}${event.payload.delta_text ?? ''}`
      streamingMessageId.value = messageId
    } else if (event.type === 'done') {
      streamingMessageId.value = null
    } else if (event.type === 'error' && event.event_seq === 0) {
      connectionError.value = event.payload.message ?? '消息发送失败'
    }
  }

  function lastSeqForTask(taskId: string): number {
    return eventSeqByTask.value[taskId] ?? 0
  }

  function clear(): void {
    activeConversationId.value = null
    messages.value = []
    draft.value = ''
    connected.value = false
    connecting.value = false
    connectionError.value = null
    lastEventSeq.value = 0
    eventSeqByTask.value = {}
    streamingMessageId.value = null
    composerAttachments.value = []
    uploadingAttachment.value = false
  }

  return {
    activeConversationId,
    addComposerAttachment,
    addOptimisticMessage,
    applyEvent,
    clear,
    connected,
    connecting,
    connectionError,
    composerAttachments,
    draft,
    lastEventSeq,
    lastSeqForTask,
    loadHistory,
    loading,
    messages,
    removeComposerAttachment,
    streamingMessageId,
    uploadingAttachment,
  }
})
