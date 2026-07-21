export interface Conversation {
  conversation_id: string
  title: string
  status: 'draft' | 'active' | 'archived' | 'deleted'
  last_message_at: string | null
  created_at: string
  updated_at: string
}

export interface AttachmentSummary {
  attachment_id: string
  file_name: string
  file_type: string
  file_size: number
  parse_status: string
}

export interface Message {
  message_id: string
  task_id: string | null
  client_msg_id: string | null
  seq_no: number
  role: string
  message_type: string
  content: string | null
  attachments: AttachmentSummary[]
  created_at: string
  pending?: boolean
}

export interface CursorPage<T> {
  items: T[]
  next_cursor: string | null
}

export interface MessagePage extends CursorPage<Message> {
  conversation_id: string
}
