<script setup lang="ts">
import { computed } from 'vue'

import ReportChart from '@/components/report/ReportChart.vue'
import { useChatStore } from '@/stores/chat'
import { useTaskStore } from '@/stores/task'
import type { KeyMetric } from '@/types/report'

const chatStore = useChatStore()
const taskStore = useTaskStore()
const report = computed(() => taskStore.result)
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
  build_evidence: '构建证据链',
  determine_attribution: '形成归因结论',
  build_report_ir: '生成 Report IR',
  validate_report: '校验报告结构',
  render_report: '渲染正式报告',
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
const conclusionLabels: Record<string, string> = {
  confirmed: '已证实',
  probable: '可能原因',
  to_verify: '待验证',
}

function timelineLabel(kind: 'node' | 'tool', name: string): string {
  return kind === 'node' ? (nodeLabels[name] ?? name) : (toolLabels[name] ?? name)
}

function metricValue(metric: KeyMetric): string {
  const value = new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 4 }).format(metric.value)
  const units: Record<string, string> = { currency: ' 元', day: ' 天', item: ' 个' }
  return `${value}${units[metric.unit ?? ''] ?? ''}`
}

function fileSize(value: number): string {
  return value < 1024 ? `${value} B` : `${(value / 1024).toFixed(1)} KB`
}
</script>

<template>
  <aside class="report-panel">
    <header>
      <div>
        <strong>分析报告</strong>
        <small v-if="report">Report IR {{ report.schema_version }}</small>
      </div>
      <span :class="{ valid: report?.validation_status === 'valid' }">
        {{ report ? '校验通过' : '阶段五' }}
      </span>
    </header>

    <div v-if="taskStore.resultLoading" class="placeholder-box">正在加载正式报告…</div>
    <template v-else-if="report">
      <section>
        <h2>1. 问题定义</h2>
        <p class="question">{{ report.problem_definition.question }}</p>
        <dl class="definition-list">
          <div><dt>范围</dt><dd>{{ report.problem_definition.scope }}</dd></div>
          <div><dt>指标</dt><dd>{{ report.problem_definition.metric }}</dd></div>
          <div><dt>基线</dt><dd>{{ report.problem_definition.baseline }}</dd></div>
          <div><dt>场景</dt><dd>{{ report.problem_definition.scenario }}</dd></div>
        </dl>
      </section>

      <section>
        <h2>2. 关键指标</h2>
        <div class="metric-grid">
          <article v-for="metric in report.key_metrics" :key="metric.metric_id">
            <span>{{ metric.label }}</span>
            <strong>{{ metricValue(metric) }}</strong>
            <small v-if="metric.change_rate !== null">
              较基线 {{ (metric.change_rate * 100).toFixed(2) }}%
            </small>
            <small v-else>{{ metric.scope }}</small>
          </article>
        </div>
      </section>

      <section>
        <h2>3. 证据列表</h2>
        <ol class="card-list">
          <li v-for="evidence in report.evidence_list" :key="evidence.evidence_id">
            <div>
              <code>{{ evidence.evidence_id }}</code>
              <span :class="evidence.quality_status">{{ evidence.quality_status }}</span>
            </div>
            <strong>{{ evidence.title }}</strong>
            <p>{{ evidence.description }}</p>
            <small>公式：{{ evidence.formula }}</small>
          </li>
        </ol>
      </section>

      <section>
        <h2>4. 归因结论</h2>
        <ol class="card-list">
          <li
            v-for="conclusion in report.attribution_conclusions"
            :key="conclusion.conclusion_id"
          >
            <div>
              <strong>{{ conclusion.title }}</strong>
              <span :class="conclusion.status">{{ conclusionLabels[conclusion.status] }}</span>
            </div>
            <p>{{ conclusion.description }}</p>
            <small>
              置信度 {{ Math.round(conclusion.confidence * 100) }}% · 证据
              {{ conclusion.evidence_ids.join('、') || '无' }}
            </small>
          </li>
        </ol>
      </section>

      <section>
        <h2>5. 待补充数据</h2>
        <ul v-if="report.report_ir.missing_data.length" class="plain-list">
          <li v-for="item in report.report_ir.missing_data" :key="item.field">
            <strong>{{ item.reason }}</strong>
            <span>{{ item.impact }}</span>
            <small>{{ item.required_action }}</small>
          </li>
        </ul>
        <p v-else class="empty-text">无已识别的数据缺口</p>
      </section>

      <section>
        <h2>6. 下一步建议</h2>
        <ol class="plain-list">
          <li v-for="action in report.next_actions" :key="action.action_id">
            <strong>{{ action.title }}</strong>
            <span>{{ action.description }}</span>
            <small>
              {{ action.priority }}<template v-if="action.owner_hint"> · {{ action.owner_hint }}</template>
            </small>
          </li>
        </ol>
      </section>

      <section v-if="report.report_ir.visualizations.length">
        <h2>可视化</h2>
        <article
          v-for="visualization in report.report_ir.visualizations"
          :key="visualization.chart_id"
          class="visualization"
        >
          <h3>{{ visualization.title }}</h3>
          <div v-if="visualization.type === 'table'" class="table-scroll">
            <table>
              <thead>
                <tr><th v-for="column in visualization.columns" :key="column">{{ column }}</th></tr>
              </thead>
              <tbody>
                <tr v-for="(row, index) in visualization.rows" :key="index">
                  <td v-for="column in visualization.columns" :key="column">{{ row[column] }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <ReportChart v-else :visualization="visualization" />
        </article>
      </section>

      <section>
        <h2>报告下载</h2>
        <div class="download-list">
          <button
            v-for="file in report.generated_files"
            :key="file.file_id"
            type="button"
            @click="taskStore.download(file.file_type)"
          >
            {{ file.file_type.toUpperCase() }} · {{ fileSize(file.file_size) }}
          </button>
        </div>
      </section>
    </template>
    <section v-else>
      <h2>报告与证据</h2>
      <div class="placeholder-box">任务完成后显示六部分正式归因报告</div>
    </section>

    <section>
      <h2>Agent 执行时间线</h2>
      <ol v-if="taskStore.timeline.length" class="timeline">
        <li v-for="item in taskStore.timeline" :key="item.id" :class="item.status">
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
      <h2>任务状态</h2>
      <dl class="task-status">
        <div><dt>实时连接</dt><dd :class="{ ready: chatStore.connected }">{{ chatStore.connected ? '已连接' : '未连接' }}</dd></div>
        <div><dt>分析任务</dt><dd>{{ taskStatusText }}</dd></div>
        <div v-if="taskStore.step"><dt>当前步骤</dt><dd>{{ taskStore.step }}</dd></div>
        <div v-if="taskStore.activeTaskId"><dt>任务 ID</dt><dd class="task-id">{{ taskStore.activeTaskId }}</dd></div>
      </dl>
      <p v-if="taskStore.error" class="task-error">{{ taskStore.error }}</p>
      <button v-if="taskStore.status === 'failed'" type="button" @click="taskStore.retry">
        重试任务
      </button>
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

.report-panel > header,
.report-panel > header > div,
.card-list li > div {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.report-panel > header {
  padding-bottom: 14px;
  border-bottom: 1px solid #edf0f4;
}

.report-panel > header > div {
  align-items: flex-start;
  flex-direction: column;
  gap: 2px;
}

.report-panel > header span,
.report-panel > header small,
.card-list small,
.plain-list small {
  color: #768399;
  font-size: 10px;
}

.report-panel > header span.valid {
  color: #158464;
}

section,
.placeholder-box {
  margin-top: 22px;
}

h2,
h3,
p {
  margin: 0;
}

h2 {
  margin-bottom: 10px;
  color: #354057;
  font-size: 13px;
}

h3 {
  color: #354057;
  font-size: 12px;
}

.question,
.card-list p,
.empty-text,
.task-error {
  color: #66758b;
  font-size: 12px;
  line-height: 1.65;
}

.definition-list,
.task-status {
  margin: 8px 0 0;
  color: #7b8799;
  font-size: 11px;
}

.definition-list > div,
.task-status > div {
  display: grid;
  grid-template-columns: 48px minmax(0, 1fr);
  gap: 8px;
  padding: 4px 0;
}

dt,
dd {
  margin: 0;
}

.metric-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.metric-grid article {
  min-width: 0;
  padding: 10px;
  background: #f5f7ff;
  border-radius: 8px;
}

.metric-grid span,
.metric-grid small {
  display: block;
  overflow: hidden;
  color: #748096;
  font-size: 10px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.metric-grid strong {
  display: block;
  margin: 5px 0;
  color: #263755;
  font-size: 16px;
}

.card-list,
.plain-list,
.timeline {
  display: grid;
  gap: 8px;
  padding: 0;
  margin: 0;
  list-style: none;
}

.card-list li,
.plain-list li,
.visualization {
  padding: 10px;
  background: #f8fafc;
  border: 1px solid #edf0f4;
  border-radius: 8px;
}

.card-list li > strong,
.plain-list strong,
.plain-list span,
.plain-list small {
  display: block;
  margin-top: 5px;
}

.card-list span,
.card-list code {
  padding: 2px 5px;
  color: #596b8c;
  font-size: 9px;
  background: #edf1f7;
  border-radius: 4px;
}

.card-list span.confirmed,
.card-list span.verified {
  color: #14745a;
  background: #e1f4ed;
}

.card-list span.to_verify,
.card-list span.limited {
  color: #916120;
  background: #fff2d8;
}

.plain-list span {
  color: #657389;
  font-size: 11px;
  line-height: 1.5;
}

.visualization {
  margin-top: 8px;
  background: #fff;
}

.table-scroll {
  margin-top: 8px;
  overflow: auto;
}

table {
  width: 100%;
  border-collapse: collapse;
  font-size: 10px;
}

th,
td {
  padding: 6px;
  border-bottom: 1px solid #edf0f4;
  text-align: left;
  white-space: nowrap;
}

.download-list {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
}

.download-list button {
  padding: 7px 9px;
  font-size: 10px;
}

.placeholder-box {
  padding: 18px 10px;
  color: #7b8799;
  font-size: 12px;
  text-align: center;
  background: #f8fafc;
  border: 1px dashed #ccd5e1;
  border-radius: 9px;
}

.ready {
  color: #158464;
}

.task-id {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.task-error {
  margin: 8px 0;
  color: #b44545;
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
  font-size: 10px;
}

.timeline li span,
.timeline li small {
  display: block;
  margin-top: 4px;
  color: #7b8799;
  font-size: 9px;
}
</style>
