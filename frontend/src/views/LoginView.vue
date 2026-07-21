<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'

import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const authStore = useAuthStore()
const nextPath = computed(() => {
  const value = route.query.next
  return typeof value === 'string' && value.startsWith('/') ? value : '/workbench'
})
</script>

<template>
  <main class="login-page">
    <section class="login-card">
      <div class="login-brand">IA</div>
      <p class="eyebrow">INSIGHT AGENT</p>
      <h1>经营归因分析系统</h1>
      <p class="login-copy">使用组织统一身份登录，进入你的经营分析工作台。</p>
      <p v-if="route.query.unavailable" class="login-warning">后端或会话服务暂不可用，请稍后重试。</p>
      <button type="button" @click="authStore.login(nextPath)">使用 OIDC 登录</button>
      <small>系统不会在浏览器本地存储访问令牌。</small>
    </section>
  </main>
</template>

<style scoped>
.login-page {
  display: grid;
  min-height: 100vh;
  padding: 24px;
  background:
    radial-gradient(circle at 18% 12%, rgb(72 112 245 / 20%), transparent 35%),
    #121b2d;
  place-items: center;
}

.login-card {
  width: min(430px, 100%);
  padding: 42px;
  text-align: center;
  background: #fff;
  border-radius: 20px;
  box-shadow: 0 28px 80px rgb(0 0 0 / 28%);
}

.login-brand {
  display: grid;
  width: 56px;
  height: 56px;
  margin: auto;
  color: #fff;
  font-size: 20px;
  font-weight: 800;
  background: #4870f5;
  border-radius: 16px;
  place-items: center;
}

.eyebrow {
  margin: 20px 0 8px;
  color: #4870f5;
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.18em;
}

h1 {
  margin: 0;
  font-size: 26px;
}

.login-copy {
  margin: 14px 0 26px;
  color: #758196;
  line-height: 1.7;
}

button {
  width: 100%;
  padding: 12px;
  font-weight: 700;
}

small {
  display: block;
  margin-top: 16px;
  color: #97a1b1;
}

.login-warning {
  padding: 9px;
  color: #a53b3b;
  font-size: 13px;
  background: #fff0f0;
  border-radius: 8px;
}
</style>
