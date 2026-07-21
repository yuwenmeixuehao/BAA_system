export interface AdminTaskLogItem {
  log_id: string
  task_id: string
  log_level: string
  log_type: string
  log_content: string
  trace_id: string | null
  duration_ms: number | null
  created_at: string
}
