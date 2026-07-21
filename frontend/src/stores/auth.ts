import axios from 'axios'
import { defineStore } from 'pinia'
import { ref } from 'vue'

import { getCurrentUser, logout as requestLogout, startLogin } from '@/api/auth'
import type { CurrentUser } from '@/types/auth'

export const useAuthStore = defineStore('auth', () => {
  const user = ref<CurrentUser | null>(null)
  const initialized = ref(false)
  const loading = ref(false)

  async function loadCurrentUser(force = false): Promise<CurrentUser | null> {
    if (initialized.value && !force) return user.value
    loading.value = true
    try {
      user.value = await getCurrentUser()
    } catch (error) {
      if (!axios.isAxiosError(error) || error.response?.status !== 401) throw error
      user.value = null
    } finally {
      initialized.value = true
      loading.value = false
    }
    return user.value
  }

  function login(next?: string): void {
    startLogin(next)
  }

  async function logout(): Promise<void> {
    await requestLogout()
    user.value = null
    initialized.value = true
  }

  return { initialized, loading, user, loadCurrentUser, login, logout }
})
