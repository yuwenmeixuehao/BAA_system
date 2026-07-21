import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { http, type ApiResponse } from '@/api/http'

interface LiveHealth {
  status: string
  service: string
  version: string
}

export const useAppStore = defineStore('app', () => {
  const checking = ref(false)
  const health = ref<LiveHealth | null>(null)
  const error = ref('')

  const backendAvailable = computed(() => health.value?.status === 'ok')

  async function checkBackend(): Promise<void> {
    checking.value = true
    error.value = ''
    try {
      const response = await http.get<ApiResponse<LiveHealth>>('/health/live')
      health.value = response.data.data
    } catch {
      health.value = null
      error.value = '后端尚未启动或暂时不可用'
    } finally {
      checking.value = false
    }
  }

  return { backendAvailable, checkBackend, checking, error, health }
})
