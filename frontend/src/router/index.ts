import { createRouter, createWebHistory } from 'vue-router'

import { pinia } from '@/stores'
import { useAuthStore } from '@/stores/auth'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      redirect: '/workbench',
    },
    {
      path: '/login',
      name: 'login',
      component: () => import('@/views/LoginView.vue'),
    },
    {
      path: '/workbench/:conversationId?',
      name: 'workbench',
      component: () => import('@/views/WorkbenchView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/admin/logs',
      name: 'admin-logs',
      component: () => import('@/views/AdminLogsView.vue'),
      meta: { requiresAuth: true, requiresAdmin: true },
    },
  ],
})

router.beforeEach(async (to) => {
  const authStore = useAuthStore(pinia)
  if (!authStore.initialized) {
    try {
      await authStore.loadCurrentUser()
    } catch {
      if (to.meta.requiresAuth) return { name: 'login', query: { unavailable: '1' } }
    }
  }
  if (to.meta.requiresAuth && !authStore.user) {
    return { name: 'login', query: { next: to.fullPath } }
  }
  if (to.meta.requiresAdmin && authStore.user?.role !== 'admin') {
    return { name: 'workbench' }
  }
  if (to.name === 'login' && authStore.user) return { name: 'workbench' }
  return true
})

export default router
