<script setup lang="ts">
import { computed } from 'vue'

import { useChatStore } from '@/stores/chat'
import { useTaskStore } from '@/stores/task'

const chatStore = useChatStore()
const taskStore = useTaskStore()
const taskStatusText = computed(() => {
  const labels: Record<string, string> = {
    queued: '排队中',
    running: '执行中',
    waiting_input: '等待补充',
    success: '已完成',
    failed: '失败',
    cancelled: '已取消',
  }
  return taskStore.status ? labels[taskStore.status] : '未启动'
})
const nodeLabels: Record<string, string> = {
  load_context: '加载会话上下文',
  define_problem: '定义分析问题',
  ask_clarification: '生成澄清问题',
  build_analysis_plan: '生成分析计划',
  query_data: '获取分析数据',
  validate_data: '校验数据质量',
  analyze_with_pandas: '执行 Pandas 分析',
}
const toolLabels: Record<string, string> = {
  db_query: '受控数据库查询',
  file_read: '读取附件',
  pandas_analyze: 'Pandas 计算',
}
const statusLabels: Record<string, string> = {
  started: '执行中',
  finished: '已完成',
  failed: '失败',
}

function timelineLabel(kind: 'node' | 'tool', name: string): string {
  return kind === 'node' ? (nodeLabels[name] ?? name) : (toolLabels[name] ?? name)
}
</script>

<template>
  <aside class="report-panel">
    <header>
      <strong>分析上下文</strong>
      <span>阶段四</span>
    </header>
    <section>
      <h2>报告与证据</h2>
      <p v-if="taskStore.resultId">
        数据分析产物已生成（阶段 {{ taskStore.resultStage ?? 4 }}）。证据链、归因结论和正式报告在阶段五生成。
      </p>
      <p v-else>本阶段展示问题定义、数据校验和计算进度；正式归因报告在阶段五生成。</p>
    </section>
    <section>
      <h2>Agent 执行时间线</h2>
      <ol v-if="taskStore.timeline.length" class="timeline">
        <li
          v-for="item in taskStore.timeline"
          :key="item.id"
          :class="item.status"
        >
          <div>
            <strong>{{ timelineLabel(item.kind, item.name) }}</strong>
            <span>{{ item.kind === 'tool' ? '工具' : '节点' }} · {{ statusLabels[item.status] }}</span>
          </div>
          <small v-if="item.summary">{{ item.summary }}</small>
          <small v-if="item.durationMs !== null">{{ item.durationMs }} ms</small>
        </li>
      </ol>
      <div v-else class="placeholder-box">任务启动后显示节点与工具事件</div>
    </section>
    <section>
      <h2>附件</h2>
      <div class="placeholder-box">尚未上传数据文件</div>
    </section>
    <section>
      <h2>任务状态</h2>
      <dl>
        <div><dt>实时连接</dt><dd :class="{ ready: chatStore.connected }">{{ chatStore.connected ? '已连接' : '未连接' }}</dd></div>
        <div><dt>分析任务</dt><dd>{{ taskStatusText }}</dd></div>
        <div v-if="taskStore.step"><dt>当前步骤</dt><dd>{{ taskStore.step }}</dd></div>
        <div v-if="taskStore.activeTaskId"><dt>任务 ID</dt><dd class="task-id">{{ taskStore.activeTaskId }}</dd></div>
      </dl>
      <p v-if="taskStore.error" class="task-error">{{ taskStore.error }}</p>
    </section>
  </aside>
</template>

<style scoped>
.report-panel {
  padding: 18px;
  overflow: auto;
  background: #fff;
  border-left: 1px solid #e2e8f0;
}

.report-panel > header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-bottom: 14px;
  border-bottom: 1px solid #edf0f4;
}

.report-panel > header span {
  color: #5d73bd;
  font-size: 11px;
}

section {
  margin-top: 24px;
}

h2 {
  margin: 0 0 8px;
  color: #354057;
  font-size: 13px;
}

p,
.placeholder-box,
dl {
  color: #7b8799;
  font-size: 12px;
  line-height: 1.7;
}

.placeholder-box {
  padding: 18px 10px;
  text-align: center;
  background: #f8fafc;
  border: 1px dashed #ccd5e1;
  border-radius: 9px;
}

dl > div {
  display: flex;
  justify-content: space-between;
  padding: 7px 0;
}

dt,
dd {
  margin: 0;
}

.ready {
  color: #158464;
}

.task-id {
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.task-error {
  color: #b44545;
}

.timeline {
  display: grid;
  gap: 10px;
  padding: 0;
  margin: 12px 0 0;
  list-style: none;
}

.timeline li {
  padding: 9px 10px;
  background: #f8fafc;
  border-left: 3px solid #8ca3ef;
  border-radius: 7px;
}

.timeline li.finished {
  border-left-color: #27a278;
}

.timeline li.failed {
  border-left-color: #c24949;
}

.timeline li > div {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  color: #354057;
  font-size: 11px;
}

.timeline li span,
.timeline li small {
  color: #7b8799;
  font-size: 10px;
}

.timeline li small {
  display: block;
  margin-top: 5px;
  line-height: 1.5;
}
</style>
