<script setup lang="ts">
import type { EChartsOption } from 'echarts'
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { getDashboardComparison, getProducts } from '@/api'
import DashboardFilters from '@/components/DashboardFilters.vue'
import TechChart from '@/components/TechChart.vue'
import type { DashboardComparison, DashboardFilters as FilterValues, Product } from '@/types/api'

const router = useRouter()
const route = useRoute()
const filters = ref<FilterValues>({
  source_id: route.query.source_id ? Number(route.query.source_id) : undefined,
  start_date: String(route.query.start_date || ''),
  end_date: String(route.query.end_date || ''),
})
const products = ref<Product[]>([])
const leftId = ref<number>()
const rightId = ref<number>()
const data = ref<DashboardComparison>()
const loading = ref(false)
const error = ref('')
const mode = ref<'count' | 'ratio'>('count')

const chartOption = computed<EChartsOption>(() => ({
  tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
  legend: { textStyle: { color: '#96adc6' } },
  grid: { left: 90, right: 26, top: 54, bottom: 30 },
  xAxis: {
    type: 'value',
    axisLabel: { color: '#96adc6', formatter: mode.value === 'ratio' ? '{value}%' : '{value}' },
    splitLine: { lineStyle: { color: '#29435c55' } },
  },
  yAxis: {
    type: 'category',
    data: data.value?.categories.map((item) => item.name) || [],
    axisLabel: { color: '#edf5ff' },
  },
  series: data.value
    ? [
        {
          name: data.value.left.product_name,
          type: 'bar',
          data: data.value.categories.map((item) =>
            mode.value === 'count'
              ? item.left.feedback_count
              : Number(((item.left.ratio || 0) * 100).toFixed(1)),
          ),
          itemStyle: { color: '#35b9f0' },
        },
        {
          name: data.value.right.product_name,
          type: 'bar',
          data: data.value.categories.map((item) =>
            mode.value === 'count'
              ? item.right.feedback_count
              : Number(((item.right.ratio || 0) * 100).toFixed(1)),
          ),
          itemStyle: { color: '#42d6c6' },
        },
      ]
    : [],
}))

async function load(): Promise<void> {
  if (!leftId.value || !rightId.value || leftId.value === rightId.value) return
  loading.value = true
  error.value = ''
  try {
    data.value = await getDashboardComparison({
      ...filters.value,
      left_product_id: leftId.value,
      right_product_id: rightId.value,
    })
    await router.replace({
      query: {
        left_product_id: leftId.value,
        right_product_id: rightId.value,
        source_id: filters.value.source_id,
        start_date: filters.value.start_date,
        end_date: filters.value.end_date,
      },
    })
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '产品对比加载失败'
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  products.value = (await getProducts({ page_size: 100 })).results
  const requestedLeft = Number(route.query.left_product_id)
  const requestedRight = Number(route.query.right_product_id)
  leftId.value = products.value.some((item) => item.id === requestedLeft)
    ? requestedLeft
    : products.value.find((item) => item.name.replace(/\s/g, '') === '荣耀Power')?.id ||
      products.value[0]?.id
  rightId.value = products.value.some(
    (item) => item.id === requestedRight && item.id !== leftId.value,
  )
    ? requestedRight
    : products.value.find((item) => item.name.replace(/\s/g, '') === '荣耀Power2')?.id ||
      products.value.find((item) => item.id !== leftId.value)?.id
  await load()
})
</script>

<template>
  <div class="dashboard-page">
    <div class="page-header">
      <div>
        <p class="eyebrow">PRODUCT COMPARISON</p>
        <h1 class="page-title">产品对比中心</h1>
        <p class="page-description">使用相同时间和来源口径比较两款手机的真实用户声音</p>
      </div>
    </div>
    <section class="tech-panel compare-filters">
      <div class="product-selectors">
        <el-select v-model="leftId" placeholder="左侧产品" @change="load"
          ><el-option
            v-for="item in products"
            :key="item.id"
            :label="item.name"
            :value="item.id"
            :disabled="item.id === rightId" /></el-select
        ><span>VS</span
        ><el-select v-model="rightId" placeholder="右侧产品" @change="load"
          ><el-option
            v-for="item in products"
            :key="item.id"
            :label="item.name"
            :value="item.id"
            :disabled="item.id === leftId"
        /></el-select>
      </div>
      <DashboardFilters v-model="filters" compact :show-product="false" @change="load" />
    </section>
    <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" />
    <el-alert
      v-if="data?.reliability_message"
      :title="data.reliability_message"
      type="warning"
      show-icon
      :closable="false"
      class="notice"
    />
    <section v-if="data" v-loading="loading" class="side-grid">
      <article
        v-for="side in [data.left, data.right]"
        :key="side.product_id"
        class="tech-panel product-side"
      >
        <h2>{{ side.product_name }}</h2>
        <div class="side-metrics">
          <span
            >原始反馈<strong>{{ side.raw_feedback }}</strong></span
          ><span
            >有效反馈<strong>{{ side.valid_feedback }}</strong></span
          ><span
            >AI 已分析<strong>{{ side.ai_analyzed }}</strong></span
          ><span
            >明确问题<strong>{{ side.explicit_issue_feedback }}</strong></span
          ><span
            >负面占比<strong>{{
              side.negative_ratio === null ? '—' : `${(side.negative_ratio * 100).toFixed(1)}%`
            }}</strong
            ><small>分母 {{ side.ratio_denominator }}</small></span
          >
        </div>
      </article>
    </section>
    <section class="tech-panel chart-section">
      <div class="panel-heading">
        <div>
          <h2>问题类别对比</h2>
          <p>比例分母为各产品已完成分析的有效用户反馈</p>
        </div>
        <el-radio-group v-model="mode" size="small"
          ><el-radio-button value="count">数量</el-radio-button
          ><el-radio-button value="ratio">占比</el-radio-button></el-radio-group
        >
      </div>
      <TechChart
        :option="chartOption"
        :loading="loading"
        :empty="!data?.categories.length"
        height="390px"
      />
    </section>
    <section v-if="data" class="side-grid issue-grid">
      <article v-for="side in [data.left, data.right]" :key="side.product_id" class="tech-panel">
        <h2>{{ side.product_name }} · TOP 5</h2>
        <button
          v-for="issue in side.top_issues"
          :key="issue.id"
          class="issue-row"
          type="button"
          @click="
            router.push({
              path: '/issues',
              query: { product_id: side.product_id, search: issue.name },
            })
          "
        >
          <span>{{ issue.name }}</span
          ><strong>{{ issue.feedback_count }}</strong
          ><small>{{ issue.severity }}</small></button
        ><el-empty v-if="!side.top_issues.length" description="暂无明确问题" />
      </article>
    </section>
  </div>
</template>

<style scoped>
.eyebrow {
  margin: 0 0 6px;
  color: var(--pvi-blue);
  font-size: 12px;
  letter-spacing: 0.18em;
}
.tech-panel {
  padding: 18px;
  background: var(--pvi-card);
  border: 1px solid var(--pvi-border);
  border-radius: 14px;
}
.compare-filters,
.product-selectors,
.panel-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
}
.product-selectors .el-select {
  width: 190px;
}
.product-selectors span {
  color: var(--pvi-blue);
  font-weight: 800;
}
.notice {
  margin: 14px 0;
}
.side-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
  margin: 16px 0;
}
.product-side h2,
.issue-grid h2 {
  margin: 0 0 18px;
}
.side-metrics {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 10px;
}
.side-metrics span {
  color: var(--pvi-muted);
  font-size: 12px;
}
.side-metrics strong {
  display: block;
  margin-top: 8px;
  color: var(--pvi-text);
  font-size: 25px;
}
.side-metrics small {
  display: block;
  margin-top: 4px;
}
.chart-section {
  margin-top: 16px;
}
.panel-heading h2 {
  margin: 0;
}
.panel-heading p {
  margin: 5px 0 0;
  color: var(--pvi-muted);
  font-size: 12px;
}
.issue-row {
  width: 100%;
  display: grid;
  grid-template-columns: 1fr auto auto;
  gap: 12px;
  padding: 12px 4px;
  color: inherit;
  text-align: left;
  background: transparent;
  border: 0;
  border-bottom: 1px solid #29435c;
  cursor: pointer;
}
.issue-row strong {
  color: var(--pvi-blue);
}
.issue-row small {
  color: var(--pvi-muted);
}
@media (max-width: 1050px) {
  .compare-filters {
    align-items: stretch;
    flex-direction: column;
  }
  .side-metrics {
    grid-template-columns: repeat(2, 1fr);
  }
}
@media (max-width: 720px) {
  .side-grid {
    grid-template-columns: 1fr;
  }
  .product-selectors,
  .product-selectors .el-select {
    width: 100%;
  }
}
</style>
