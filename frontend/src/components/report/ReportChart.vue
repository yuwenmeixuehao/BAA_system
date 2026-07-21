<script setup lang="ts">
import { BarChart, LineChart, PieChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import * as echarts from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

import type { Visualization } from '@/types/report'

echarts.use([
  BarChart,
  LineChart,
  PieChart,
  GridComponent,
  LegendComponent,
  TooltipComponent,
  CanvasRenderer,
])

const props = defineProps<{ visualization: Visualization }>()
const chartElement = ref<HTMLDivElement | null>(null)
let chart: echarts.ECharts | null = null

function buildOption(): echarts.EChartsCoreOption {
  const visualization = props.visualization
  if (visualization.type === 'pie') {
    return {
      tooltip: { trigger: 'item' },
      legend: { bottom: 0 },
      series: [
        {
          type: 'pie',
          radius: ['38%', '68%'],
          data: visualization.categories.map((name, index) => ({
            name,
            value: visualization.series[0]?.data[index] ?? 0,
          })),
        },
      ],
    }
  }
  return {
    tooltip: { trigger: 'axis' },
    legend: { bottom: 0 },
    grid: { top: 22, right: 14, bottom: 52, left: 52 },
    xAxis: { type: 'category', data: visualization.categories },
    yAxis: { type: 'value' },
    series: visualization.series.map((item) => ({
      name: item.name,
      type: visualization.type === 'line' ? 'line' : 'bar',
      stack: visualization.type === 'stackedBar' ? 'total' : undefined,
      smooth: visualization.type === 'line',
      data: item.data,
    })),
  }
}

function render(): void {
  if (!chartElement.value) return
  chart ??= echarts.init(chartElement.value)
  chart.setOption(buildOption(), true)
}

function resize(): void {
  chart?.resize()
}

onMounted(() => {
  render()
  window.addEventListener('resize', resize)
})
watch(() => props.visualization, render, { deep: true })
onBeforeUnmount(() => {
  window.removeEventListener('resize', resize)
  chart?.dispose()
  chart = null
})
</script>

<template>
  <div ref="chartElement" class="report-chart" role="img" :aria-label="visualization.title" />
</template>

<style scoped>
.report-chart {
  width: 100%;
  height: 280px;
}
</style>
