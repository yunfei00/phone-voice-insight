<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import type { EChartsOption } from 'echarts'
import { getStructuredAnalyses } from '@/api'
import TechChart from '@/components/TechChart.vue'
import type { StructuredAnalysisV1 } from '@/types/api'

const loading = ref(false)
const error = ref('')
const records = ref<StructuredAnalysisV1[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 100
const selected = ref('')
const negative = (value: string) => ['NEGATIVE', 'negative', '负面'].includes(value)
const communications = computed(() => records.value.flatMap(record =>
  record.aspects.filter(opinion =>
    opinion.aspect_code === 'NET' || opinion.aspect_code.startsWith('NET.') ||
    opinion.topic_code === 'NET' || opinion.topic_code.startsWith('NET.') ||
    opinion.business_domains.includes('NET')
  ).map(opinion => ({ record, opinion }))
))
const issues = computed(() => communications.value.filter(item => negative(item.opinion.sentiment)))
const categoryCounts = computed(() => {
  const counts = new Map<string, Set<number>>()
  for (const { record, opinion } of issues.value) {
    const key = opinion.topic_code.startsWith('NET.') ? opinion.topic_code : opinion.aspect_code
    if (!counts.has(key)) counts.set(key, new Set())
    counts.get(key)!.add(record.content)
  }
  return [...counts].map(([code, ids]) => ({ code, count: ids.size })).sort((a, b) => b.count - a.count)
})
const names: Record<string, string> = {
  'NET.CELLULAR': '蜂窝信号', 'NET.WIFI_BLUETOOTH': 'Wi-Fi与蓝牙',
  'NET.LOCATION': '定位导航', 'NET.CALL': '通话连接',
  'NET.ELEVATOR': '电梯场景', 'NET.BASEMENT': '地下停车场',
  'NET.METRO': '地铁隧道', 'NET.WEAK_SIGNAL': '弱信号与无服务',
  'NET.DATA_INTERRUPTION': '移动数据断流', 'NET.HANDOVER': '网络切换',
  'NET.NAVIGATION': '导航体验', 'NET.CALL_DROP': '掉话与呼叫失败',
  'NET.VOLTE': 'VoLTE与VoWiFi', 'NET.WIFI': 'Wi-Fi连接',
  'NET.BLUETOOTH': '蓝牙连接', 'NET.DUAL_SIM': '双卡与运营商'
}
const label = (code: string) => names[code] || code
const chart = computed<EChartsOption>(() => ({
  tooltip: { trigger: 'axis' },
  grid: { left: 115, right: 32, top: 20, bottom: 30 },
  xAxis: { type: 'value', minInterval: 1, axisLabel: { color: '#96adc6' } },
  yAxis: { type: 'category', inverse: true, data: categoryCounts.value.slice(0, 10).map(item => label(item.code)), axisLabel: { color: '#edf5ff' } },
  series: [{ type: 'bar', barMaxWidth: 18, itemStyle: { color: '#35b9f0', borderRadius: [0, 8, 8, 0] }, data: categoryCounts.value.slice(0, 10).map(item => item.count) }]
}))
const visible = computed(() => issues.value.filter(item => !selected.value || item.opinion.topic_code === selected.value || item.opinion.aspect_code === selected.value).slice(0, 30))
async function load() {
  loading.value = true
  error.value = ''
  try {
    const result = await getStructuredAnalyses({ page: page.value, page_size: pageSize })
    records.value = result.results
    total.value = result.count
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '通信数据加载失败'
  } finally {
    loading.value = false
  }
}
onMounted(() => { void load() })
</script>

<template>
  <div class="communication-dashboard">
    <header class="communication-hero">
      <div><p>PHONE VOICE INTELLIGENCE · COMMUNICATION</p><h1>通信智能看板</h1><span>通信场景 · 网络质量 · 用户问题洞察</span></div>
      <el-button type="primary" :loading="loading" @click="load">刷新数据</el-button>
    </header>
    <el-alert v-if="error" type="error" :title="error" show-icon :closable="false" />
    <el-alert type="info" :closable="false" title="当前为结构化分析分页视图：以下指标仅统计当前加载的分析记录，不代表全量通信问题。新增标签需要后续 AI 分析或重分析才会产生数据。" />
    <section class="communication-metrics">
      <article><span>当前页分析记录</span><strong>{{ records.length }}</strong></article>
      <article><span>涉及通信的独立反馈</span><strong>{{ new Set(communications.map(item => item.record.content)).size }}</strong></article>
      <article><span>通信负面反馈</span><strong>{{ new Set(issues.map(item => item.record.content)).size }}</strong></article>
      <article><span>当前最多问题</span><strong>{{ categoryCounts.length ? label(categoryCounts[0].code) : '暂无数据' }}</strong></article>
    </section>
    <section class="communication-panel">
      <h2>通信 TOP 问题子类</h2>
      <p>按独立原始反馈去重统计，点击分类查看证据</p>
      <TechChart :option="chart" :loading="loading" :empty="!categoryCounts.length" />
      <div class="communication-tags">
        <el-button :type="!selected ? 'primary' : 'default'" @click="selected = ''">全部通信问题</el-button>
        <el-button v-for="item in categoryCounts" :key="item.code" :type="selected === item.code ? 'primary' : 'default'" @click="selected = item.code">{{ label(item.code) }} · {{ item.count }}</el-button>
      </div>
    </section>
    <section class="communication-panel">
      <h2>用户反馈证据</h2>
      <el-empty v-if="!visible.length" description="当前范围暂无通信问题证据" />
      <div v-for="item in visible" :key="`${item.record.id}-${item.opinion.id}`" class="communication-evidence">
        <div><strong>{{ item.record.product_name }} · {{ label(item.opinion.topic_code) }}</strong><span>{{ item.opinion.severity }}</span></div>
        <p>{{ item.opinion.evidence_text || item.record.summary }}</p>
        <a v-if="item.record.source_url" :href="item.record.source_url" target="_blank" rel="noopener noreferrer">查看原帖</a>
      </div>
    </section>
    <footer class="communication-pagination">
      <span>结构化分析总记录 {{ total }} 条；每页 {{ pageSize }} 条</span>
      <el-pagination v-model:current-page="page" :page-size="pageSize" :total="total" layout="prev, pager, next" @current-change="load" />
    </footer>
  </div>
</template>

<style scoped>
.communication-dashboard { color: #edf5ff; display: grid; gap: 20px; }
.communication-hero { display: flex; align-items: center; justify-content: space-between; padding: 28px; border: 1px solid #29435c; border-radius: 16px; background: linear-gradient(110deg,#12283f,#0a192a); }
.communication-hero p { color: #35b9f0; letter-spacing: 2px; font-size: 12px; }
.communication-hero h1 { font-size: 30px; margin: 10px 0; }
.communication-hero span,.communication-panel>p { color: #96adc6; }
.communication-metrics { display: grid; grid-template-columns: repeat(4,minmax(0,1fr)); gap: 16px; }
.communication-metrics article,.communication-panel { background: #12283f; border: 1px solid #29435c; border-radius: 14px; padding: 22px; }
.communication-metrics article { display: grid; gap: 16px; }
.communication-metrics span { color: #96adc6; }
.communication-metrics strong { color: #35b9f0; font-size: 28px; }
.communication-panel h2 { font-size: 19px; margin: 0 0 10px; }
.communication-tags { display: flex; flex-wrap: wrap; gap: 8px; }
.communication-tags :deep(.el-button) { margin: 0; }
.communication-evidence { padding: 15px 0; border-top: 1px solid #29435c; }
.communication-evidence>div { display: flex; justify-content: space-between; gap: 12px; }
.communication-evidence p { color: #c7d9e9; }
.communication-evidence a { color: #35b9f0; }
.communication-pagination { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px; }
@media(max-width:850px) { .communication-metrics { grid-template-columns: repeat(2,minmax(0,1fr)); } .communication-hero { flex-wrap: wrap; gap: 16px; } }
</style>
