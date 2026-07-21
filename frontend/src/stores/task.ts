import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import * as taskApi from '@/api/tasks'
import * as resultApi from '@/api/results'
import type { AnalysisResult, ReportExportFormat } from '@/types/report'
import type { TaskStatus, TaskSummary } from '@/types/task'
import type { ServerEvent } from '@/types/websocket'

export interface ExecutionTimelineEntry {
  id: string
  eventSeq: number
  kind: 'node' | 'tool'
  name: string
  status: 'started' | 'finished' | 'failed'
  summary: string | null
  durationMs: number | null
}

export const useTaskStore = defineStore('task', () => {
  const current = ref<TaskSummary | null>(null)
  const activeTaskId = ref<string | null>(null)
  const step = ref<string | null>(null)
  const status = ref<TaskStatus | null>(null)
  const error = ref<string | null>(null)
  const resultId = ref<string | null>(null)
  const clarificationQuestion = ref<string | null>(null)
  const resultStage = ref<number | null>(null)
  const result = ref<AnalysisResult | null>(null)
  const resultLoading = ref(false)
  const timeline = ref<ExecutionTimelineEntry[]>([])

  const cancellable = computed(
    () => status.value === 'queued' || status.value === 'running' || status.value === 'waiting_input',
  )
  const busy = computed(() => status.value === 'queued' || status.value === 'running')

  async function load(taskId: string): Promise<void> {
    const task = await taskApi.getTask(taskId)
    current.value = task
    activeTaskId.value = task.task_id
    status.value = task.task_status
    step.value = task.current_step
    error.value = task.error_message
    if (task.task_status === 'success') await loadResult(taskId)
  }

  async function loadResult(taskId: string): Promise<void> {
    resultLoading.value = true
    try {
      result.value = await resultApi.getResult(taskId)
      resultId.value = result.value.result_id
      resultStage.value = 5
    } catch {
      result.value = null
      error.value = '正式报告加载失败，请稍后重试。'
    } finally {
      resultLoading.value = false
    }
  }

  async function download(format: ReportExportFormat): Promise<void> {
    const taskId = activeTaskId.value
    if (!taskId) return
    const matched = result.value?.generated_files.find((item) => item.file_type === format)
    await resultApi.downloadResult(taskId, format, matched?.file_name ?? `report.${format}`)
  }

  async function retry(): Promise<void> {
    const taskId = activeTaskId.value
    if (!taskId || status.value !== 'failed') return
    const task = await taskApi.retryTask(taskId)
    current.value = task
    status.value = task.task_status
    step.value = task.current_step
    error.value = null
    result.value = null
    resultId.value = null
    resultStage.value = null
    timeline.value = []
  }

  function applyEvent(event: ServerEvent): void {
    if (event.task_id && event.task_id !== activeTaskId.value) {
      timeline.value = []
      error.value = null
      resultId.value = null
      resultStage.value = null
      result.value = null
      clarificationQuestion.value = null
    }
    if (event.task_id) activeTaskId.value = event.task_id
    if (event.type === 'task_status') {
      status.value = event.payload.task_status ?? status.value
      step.value = event.payload.current_step ?? null
      if (event.payload.node_name && event.payload.node_status) {
        appendTimeline({
          id: `${event.task_id}:node:${event.event_seq}`,
          eventSeq: event.event_seq,
          kind: 'node',
          name: event.payload.node_name,
          status: event.payload.node_status,
          summary: null,
          durationMs: event.payload.duration_ms ?? null,
        })
      }
      if (status.value !== 'waiting_input') clarificationQuestion.value = null
    } else if (event.type === 'tool_start' || event.type === 'tool_finish') {
      if (event.payload.tool_name && event.payload.tool_status) {
        appendTimeline({
          id: `${event.task_id}:tool:${event.event_seq}`,
          eventSeq: event.event_seq,
          kind: 'tool',
          name: event.payload.tool_name,
          status: event.payload.tool_status,
          summary: event.payload.summary ?? null,
          durationMs: event.payload.duration_ms ?? null,
        })
      }
    } else if (event.type === 'clarification_required') {
      status.value = 'waiting_input'
      clarificationQuestion.value = event.payload.question ?? '请补充分析范围。'
    } else if (event.type === 'result_ready') {
      resultId.value = event.payload.result_id ?? null
      resultStage.value = event.payload.stage ?? null
      if (event.task_id) void loadResult(event.task_id)
    } else if (event.type === 'error') {
      error.value = event.payload.message ?? '任务执行失败'
    } else if (event.type === 'done') {
      status.value = event.payload.task_status ?? status.value
      step.value = null
      clarificationQuestion.value = null
    }
  }

  function appendTimeline(entry: ExecutionTimelineEntry): void {
    if (timeline.value.some((item) => item.id === entry.id)) return
    timeline.value = [...timeline.value, entry].slice(-50)
  }

  function reset(): void {
    current.value = null
    activeTaskId.value = null
    step.value = null
    status.value = null
    error.value = null
    resultId.value = null
    result.value = null
    resultLoading.value = false
    clarificationQuestion.value = null
    resultStage.value = null
    timeline.value = []
  }

  return {
    activeTaskId,
    applyEvent,
    busy,
    cancellable,
    clarificationQuestion,
    current,
    error,
    download,
    load,
    loadResult,
    reset,
    result,
    resultId,
    resultLoading,
    resultStage,
    retry,
    status,
    step,
    timeline,
  }
})
