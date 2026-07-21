<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { listAdminLogs } from '@/api/admin'
import AppHeader from '@/components/layout/AppHeader.vue'
import type { AdminTaskLogItem } from '@/types/admin'

const router = useRouter()
const logs = ref<AdminTaskLogItem[]>([])
const taskId = ref('')
const traceId = ref('')
const level = ref<'' | 'info' | 'warning' | 'error'>('')
const loading = ref(false)
const error = ref<string | null>(null)

async function load(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    logs.value = await listAdminLogs({
      task_id: taskId.value.trim() || undefined,
      trace_id: traceId.value.trim() || undefined,
      level: level.value || undefined,
      limit: 200,
    })
  } catch {
    error.value = '日志加载失败，请检查管理员权限或服务状态。'
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="admin-page">
    <AppHeader />
    <main>
      <div class="page-title">
        <div>
          <p>OBSERVABILITY</p>
          <h1>Agent 运行日志</h1>
        </div>
        <button type="button" @click="router.push({ name: 'workbench' })">返回工作台</button>
      </div>
      <form class="filters" @submit.prevent="load">
        <label>任务 ID<input v-model="taskId" placeholder="精确任务 ID" /></label>
        <label>Trace ID<input v-model="traceId" placeholder="精确 Trace ID" /></label>
        <label>
          级别
          <select v-model="level">
            <option value="">全部</option>
            <option value="info">INFO</option>
            <option value="warning">WARNING</option>
            <option value="error">ERROR</option>
          </select>
        </label>
        <button type="submit" :disabled="loading">{{ loading ? '加载中…' : '查询' }}</button>
      </form>
      <p v-if="error" class="error">{{ error }}</p>
      <div class="log-table">
        <table>
          <thead>
            <tr><th>时间</th><th>级别</th><th>类型</th><th>任务</th><th>Trace</th><th>耗时</th><th>内容</th></tr>
          </thead>
          <tbody>
            <tr v-for="log in logs" :key="log.log_id">
              <td>{{ new Date(log.created_at).toLocaleString('zh-CN') }}</td>
              <td><span :class="['level', log.log_level]">{{ log.log_level.toUpperCase() }}</span></td>
              <td>{{ log.log_type }}</td>
              <td><code>{{ log.task_id }}</code></td>
              <td><code>{{ log.trace_id ?? '-' }}</code></td>
              <td>{{ log.duration_ms === null ? '-' : `${log.duration_ms} ms` }}</td>
              <td>{{ log.log_content }}</td>
            </tr>
            <tr v-if="!loading && !logs.length"><td colspan="7" class="empty">暂无匹配日志</td></tr>
          </tbody>
        </table>
      </div>
    </main>
  </div>
</template>

<style scoped>
.admin-page {
  min-height: 100vh;
  background: #f4f7fb;
}

main {
  width: min(1380px, calc(100% - 40px));
  margin: 0 auto;
  padding: 28px 0;
}

.page-title,
.filters {
  display: flex;
  gap: 14px;
  align-items: end;
  justify-content: space-between;
}

.page-title p {
  margin: 0 0 4px;
  color: #3157d5;
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.15em;
}

.page-title h1 {
  font-size: 28px;
}

.filters {
  justify-content: flex-start;
  margin: 22px 0;
  padding: 16px;
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
}

label {
  display: grid;
  gap: 6px;
  color: #647187;
  font-size: 12px;
}

input,
select {
  min-width: 180px;
  padding: 9px 10px;
  border: 1px solid #ccd5e1;
  border-radius: 7px;
}

.log-table {
  overflow: auto;
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
}

table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}

th,
td {
  padding: 11px;
  border-bottom: 1px solid #edf0f4;
  text-align: left;
  white-space: nowrap;
}

td:last-child {
  min-width: 300px;
  white-space: normal;
}

.level {
  padding: 3px 6px;
  color: #356755;
  background: #e8f4ef;
  border-radius: 5px;
}

.level.error {
  color: #a13f3f;
  background: #fbe9e9;
}

.level.warning {
  color: #8c6426;
  background: #fff4da;
}

.error {
  color: #b44545;
}

.empty {
  padding: 30px;
  color: #7d899a;
  text-align: center;
}

@media (max-width: 760px) {
  .filters {
    align-items: stretch;
    flex-direction: column;
  }

  input,
  select {
    width: 100%;
  }
}
</style>
