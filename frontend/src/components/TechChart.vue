<script setup lang="ts">
import { BarChart, LineChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import { type ECharts, type EChartsOption, init, use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = withDefaults(
  defineProps<{
    option: EChartsOption
    loading?: boolean
    empty?: boolean
    error?: string
    height?: string
  }>(),
  { loading: false, empty: false, error: '', height: '320px' },
)
const emit = defineEmits<{ chartClick: [params: unknown] }>()
const element = ref<HTMLDivElement>()
let chart: ECharts | undefined
let observer: ResizeObserver | undefined

use([BarChart, LineChart, GridComponent, LegendComponent, TooltipComponent, CanvasRenderer])

function render(): void {
  if (!element.value || props.empty || props.error) return
  chart ||= init(element.value, undefined, { renderer: 'canvas' })
  const reduced = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  chart.setOption({ animation: !reduced, ...props.option }, true)
  chart.off('click')
  chart.on('click', (params) => emit('chartClick', params))
}

watch(
  () => props.option,
  () => nextTick(render),
  { deep: true },
)
watch(
  () => [props.empty, props.error],
  () => nextTick(render),
)

onMounted(() => {
  render()
  if (element.value) {
    observer = new ResizeObserver(() => chart?.resize())
    observer.observe(element.value)
  }
})

onBeforeUnmount(() => {
  observer?.disconnect()
  chart?.dispose()
})
</script>

<template>
  <div v-loading="loading" class="tech-chart-wrap" :style="{ height }">
    <el-result v-if="error" icon="error" title="图表加载失败" :sub-title="error" />
    <el-empty v-else-if="empty" description="当前筛选范围暂无可展示数据" />
    <div v-show="!error && !empty" ref="element" class="tech-chart" />
  </div>
</template>

<style scoped>
.tech-chart-wrap,
.tech-chart {
  width: 100%;
  min-height: 220px;
}

.tech-chart-wrap {
  overflow: hidden;
}
</style>
