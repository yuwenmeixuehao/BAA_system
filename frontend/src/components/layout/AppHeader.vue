<script setup lang="ts">
import { useRouter } from 'vue-router'

import { useAuthStore } from '@/stores/auth'

const authStore = useAuthStore()
const router = useRouter()

async function handleLogout(): Promise<void> {
  await authStore.logout()
  await router.replace({ name: 'login' })
}
</script>

<template>
  <header class="app-header">
    <div class="brand-mark">IA</div>
    <div class="brand-copy">
      <strong>经营归因分析系统</strong>
      <span>Insight Agent</span>
    </div>
    <div class="header-user">
      <button
        v-if="authStore.user?.role === 'admin'"
        class="text-button"
        type="button"
        @click="router.push({ name: 'admin-logs' })"
      >
        运行日志
      </button>
      <span class="user-avatar">{{ authStore.user?.display_name.slice(0, 1) }}</span>
      <div>
        <strong>{{ authStore.user?.display_name }}</strong>
        <small>{{ authStore.user?.role === 'admin' ? '系统管理员' : '分析用户' }}</small>
      </div>
      <button class="text-button" type="button" @click="handleLogout">退出登录</button>
    </div>
  </header>
</template>

<style scoped>
.app-header {
  display: flex;
  gap: 12px;
  align-items: center;
  min-height: 64px;
  padding: 10px 20px;
  color: #fff;
  background: #18243c;
  border-bottom: 1px solid #2c3850;
}

.brand-mark,
.user-avatar {
  display: grid;
  flex: 0 0 auto;
  place-items: center;
  width: 36px;
  height: 36px;
  font-weight: 800;
  background: #4870f5;
  border-radius: 10px;
}

.brand-copy {
  display: grid;
  gap: 2px;
}

.brand-copy span,
.header-user small {
  color: #9facbf;
  font-size: 12px;
}

.header-user {
  display: flex;
  gap: 10px;
  align-items: center;
  margin-left: auto;
}

.header-user > div:nth-child(2) {
  display: grid;
}

.user-avatar {
  width: 34px;
  height: 34px;
  background: #293a59;
  border-radius: 50%;
}

.text-button {
  padding: 7px 10px;
  color: #dce5f6;
  background: transparent;
  border: 1px solid #42506a;
}

@media (max-width: 680px) {
  .brand-copy span,
  .header-user > div,
  .user-avatar {
    display: none;
  }
}
</style>
