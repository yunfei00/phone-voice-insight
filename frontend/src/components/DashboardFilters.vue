<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'

import { getProducts, getSources } from '@/api'
import type { DashboardFilters, DataSource, Product } from '@/types/api'

const props = withDefaults(
  defineProps<{ modelValue: DashboardFilters; compact?: boolean; showProduct?: boolean }>(),
  { compact: false, showProduct: true },
)
const emit = defineEmits<{
  'update:modelValue': [value: DashboardFilters]
  change: [value: DashboardFilters]
}>()
const products = ref<Product[]>([])
const sources = ref<DataSource[]>([])
const dateRange = ref<[Date, Date] | null>(null)
const preset = ref('30')

function iso(date: Date): string {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function dates(days: number): [Date, Date] {
  const end = new Date()
  const start = new Date()
  start.setDate(end.getDate() - days + 1)
  return [start, end]
}

function inferPreset(start: string, end: string): string {
  for (const days of [7, 30, 90]) {
    const [expectedStart, expectedEnd] = dates(days)
    if (start === iso(expectedStart) && end === iso(expectedEnd)) return String(days)
  }
  return 'custom'
}

function update(values: Partial<DashboardFilters>): void {
  const next = { ...props.modelValue, ...values }
  emit('update:modelValue', next)
  emit('change', next)
}

function applyPreset(value: string): void {
  if (value === 'custom') return
  const [start, end] = dates(Number(value))
  dateRange.value = [start, end]
  update({ start_date: iso(start), end_date: iso(end) })
}

function applyDates(value: [Date, Date] | null): void {
  if (!value) return
  preset.value = 'custom'
  update({ start_date: iso(value[0]), end_date: iso(value[1]) })
}

watch(
  () => [props.modelValue.start_date, props.modelValue.end_date],
  ([start, end]) => {
    if (start && end) {
      dateRange.value = [new Date(`${start}T00:00:00`), new Date(`${end}T00:00:00`)]
      preset.value = inferPreset(start, end)
    }
  },
  { immediate: true },
)

onMounted(async () => {
  const [productPage, sourcePage] = await Promise.all([
    getProducts({ page_size: 100 }),
    getSources({ page_size: 100 }),
  ])
  products.value = productPage.results
  sources.value = sourcePage.results
  if (!dateRange.value) applyPreset('30')
})
</script>

<template>
  <div class="dashboard-filters" :class="{ compact }">
    <el-select
      v-if="showProduct"
      :model-value="modelValue.product_id"
      placeholder="全部产品"
      clearable
      @change="update({ product_id: $event || undefined })"
    >
      <el-option v-for="item in products" :key="item.id" :label="item.name" :value="item.id" />
    </el-select>
    <el-select
      :model-value="modelValue.source_id"
      placeholder="全部来源"
      clearable
      @change="update({ source_id: $event || undefined })"
    >
      <el-option v-for="item in sources" :key="item.id" :label="item.name" :value="item.id" />
    </el-select>
    <el-select v-model="preset" class="range-select" @change="applyPreset">
      <el-option label="最近 7 天" value="7" />
      <el-option label="最近 30 天" value="30" />
      <el-option label="最近 90 天" value="90" />
      <el-option label="自定义" value="custom" />
    </el-select>
    <el-date-picker
      v-if="preset === 'custom'"
      v-model="dateRange"
      type="daterange"
      start-placeholder="开始日期"
      end-placeholder="结束日期"
      :clearable="false"
      @change="applyDates"
    />
  </div>
</template>

<style scoped>
.dashboard-filters {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.dashboard-filters :deep(.el-select) {
  width: 170px;
}

.dashboard-filters.compact :deep(.el-select) {
  width: 145px;
}

@media (max-width: 720px) {
  .dashboard-filters,
  .dashboard-filters :deep(.el-select),
  .dashboard-filters :deep(.el-date-editor) {
    width: 100%;
  }
}
</style>
