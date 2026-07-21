import type { TaskStatus } from '@/types/task'

export type ServerEventType =
  | 'message_start'
  | 'message_delta'
  | 'tool_start'
  | 'tool_finish'
  | 'task_status'
  | 'clarification_required'
  | 'result_ready'
  | 'error'
  | 'done'

export interface ServerEvent {
  type: ServerEventType
  task_id: string | null
  conversation_id: string | null
  event_seq: number
  occurred_at?: string
  payload: {
    message_id?: string
    client_msg_id?: string
    seq_no?: number
    delta_text?: string
    task_status?: TaskStatus
    current_step?: string | null
    cancel_requested?: boolean
    question?: string
    result_id?: string
    stage?: number
    node_name?: string
    node_status?: 'started' | 'finished' | 'failed'
    tool_name?: string
    tool_status?: 'started' | 'finished' | 'failed'
    summary?: string
    duration_ms?: number
    error_code?: string
    message?: string
    [key: string]: unknown
  }
}

export interface WebsocketToken {
  websocket_token: string
  expires_in: number
}
