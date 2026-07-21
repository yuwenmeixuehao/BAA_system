<script setup lang="ts">
import { onMounted } from 'vue'

import { useAppStore } from '@/stores/app'

const appStore = useAppStore()

onMounted(() => {
  void appStore.checkBackend()
})
</script>

<template>
  <main class="shell">
    <section class="hero">
      <p class="eyebrow">INSIGHT-AGENT</p>
      <h1>经营归因分析系统</h1>
      <p class="subtitle">阶段一工程骨架已就绪，登录、会话与分析工作台将在后续阶段接入。</p>

      <div class="status-card" aria-live="polite">
        <span
          class="status-dot"
          :class="{ online: appStore.backendAvailable }"
        />
        <div>
          <strong>{{ appStore.checking ? '正在检查后端' : appStore.backendAvailable ? '后端服务正常' : '后端未连接' }}</strong>
          <p>{{ appStore.error || appStore.health?.service || 'FastAPI health endpoint' }}</p>
        </div>
        <button type="button" :disabled="appStore.checking" @click="appStore.checkBackend">
          重新检查
        </button>
      </div>
    </section>
  </main>
</template>
