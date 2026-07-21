export type TaskStatus =
  | 'queued'
  | 'running'
  | 'waiting_input'
  | 'success'
  | 'failed'
  | 'cancelled'

export interface TaskSummary {
  task_id: string
  conversation_id: string
  message_id: string
  client_msg_id: string
  task_status: TaskStatus
  current_step: string | null
  cancel_requested: boolean
  retry_count: number
  started_at: string | null
  finished_at: string | null
  error_code: string | null
  error_message: string | null
  created_at: string
  updated_at: string
}

export interface CancelTaskResult {
  task_id: string
  task_status: TaskStatus
  cancel_requested: boolean
  accepted: boolean
}
