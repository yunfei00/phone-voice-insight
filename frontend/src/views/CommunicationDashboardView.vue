<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import type { EChartsOption } from 'echarts'
import { getCommunicationDashboard, getProducts } from '@/api'
import TechChart from '@/components/TechChart.vue'

const loading = ref(false)
const error = ref('')
const data = ref<Awaited<ReturnType<typeof getCommunicationDashboard>> | null>(null)
const selected = ref('')
const storageKey = 'phone-voice.communication.product'
const productId = ref<number | undefined>()
const products = ref<Array<{ id: number; name: string }>>([])
const evidencePanel = ref<HTMLElement | null>(null)
let requestVersion = 0
function selectCategory(code: string) {
  selected.value = code
  void load()
  void nextTick(() => evidencePanel.value?.scrollIntoView({ behavior: 'smooth', block: 'start' }))
}
async function changeProduct(value: number | undefined) {
  productId.value = value || undefined
  selected.value = ''
  try {
    if (productId.value) localStorage.setItem(storageKey, String(productId.value))
    else localStorage.removeItem(storageKey)
  } catch { /* optional storage */ }
  await load()
}
const names: Record<string, string> = {
  'NET.CELLULAR': '蜂窝信号',
  'NET.WIFI_BLUETOOTH': 'Wi-Fi与蓝牙',
  'NET.LOCATION': '定位导航',
  'NET.CALL': '通话连接',
  'NET.ELEVATOR': '电梯场景',
  'NET.BASEMENT': '地下停车场',
  'NET.METRO': '地铁隧道',
  'NET.WEAK_SIGNAL': '弱信号与无服务',
  'NET.DATA_INTERRUPTION': '移动数据断流',
  'NET.HANDOVER': '网络切换',
  'NET.NAVIGATION': '导航体验',
  'NET.CALL_DROP': '掉话与呼叫失败',
  'NET.VOLTE': 'VoLTE与VoWiFi',
  'NET.WIFI': 'Wi-Fi连接',
  'NET.BLUETOOTH': '蓝牙连接',
  'NET.DUAL_SIM': '双卡与运营商',
}
const label = (code: string) => names[code] || code
const categories = computed(() => data.value?.categories ?? [])
const evidence = computed(() =>
  (data.value?.evidence ?? []).filter(
    (item) => !selected.value || item.topic_code === selected.value,
  ),
)
const chart = computed<EChartsOption>(() => ({
  tooltip: { trigger: 'axis' },
  grid: { left: 115, right: 32, top: 20, bottom: 30 },
  xAxis: { type: 'value', minInterval: 1, axisLabel: { color: '#96adc6' } },
  yAxis: {
    type: 'category',
    inverse: true,
    data: categories.value.slice(0, 10).map((item) => label(item.topic_code)),
    axisLabel: { color: '#edf5ff' },
  },
  series: [
    {
      type: 'bar',
      barMaxWidth: 18,
      itemStyle: { color: '#35b9f0', borderRadius: [0, 8, 8, 0] },
      data: categories.value.slice(0, 10).map((item) => item.count),
    },
  ],
}))
async function load() {
  const version = ++requestVersion
  loading.value = true
  error.value = ''
  try {
    const response = await getCommunicationDashboard(productId.value, selected.value)
    if (version === requestVersion) data.value = response
  } catch (reason) {
    if (version === requestVersion) {
      error.value = reason instanceof Error ? reason.message : '通信数据加载失败'
      data.value = null
    }
  } finally {
    if (version === requestVersion) loading.value = false
  }
}
onMounted(async () => {
  try {
    const stored = localStorage.getItem(storageKey)
    const parsed = stored ? Number(stored) : undefined
    if (parsed && Number.isSafeInteger(parsed) && parsed > 0) productId.value = parsed
  } catch { /* optional storage */ }
  try {
    const response = await getProducts({ page_size: 100 })
    products.value = response.results.map((item) => ({ id: item.id, name: item.name }))
    if (productId.value && !products.value.some((item) => item.id === productId.value)) {
      productId.value = undefined
      try { localStorage.removeItem(storageKey) } catch { /* optional storage */ }
    }
  } catch { /* dashboard remains usable */ }
  await load()
})
</script>

<template>
  <div class="communication-dashboard">
    <header class="communication-hero">
      <div>
        <p>PHONE VOICE INTELLIGENCE · COMMUNICATION</p>
        <h1>通信智能看板</h1>
        <span>通信场景 · 网络质量 · 用户问题洞察</span>
      </div>
      <div class="communication-actions">
        <el-select :model-value="productId" placeholder="全部产品" clearable filterable style="width: 220px" aria-label="选择手机产品" @change="changeProduct">
          <el-option label="全部产品" :value="0" />
          <el-option v-for="item in products" :key="item.id" :label="item.name" :value="item.id" />
        </el-select>
        <el-button type="primary" :loading="loading" @click="load">刷新数据</el-button>
      </div>
    </header>
    <el-alert v-if="error" type="error" :title="error" show-icon :closable="false" />
    <el-alert
      type="info"
      :closable="false"
      :title="
        data?.disclaimer || '仅统计已完成并审核通过的通信结构化分析；新标签需重新分析历史数据。'
      "
    />
    <section class="communication-metrics">
      <article>
        <span>通信相关反馈</span><strong>{{ data?.content_count ?? 0 }}</strong>
      </article>
      <article>
        <span>通信负面反馈</span><strong>{{ data?.negative_content_count ?? 0 }}</strong>
      </article>
      <article>
        <span>负面反馈占比</span
        ><strong>{{
          data?.content_count
            ? ((data.negative_content_count / data.content_count) * 100).toFixed(1) + '%'
            : '—'
        }}</strong>
      </article>
      <article>
        <span>当前最多问题</span
        ><button v-if="categories.length" class="communication-link" @click="selectCategory(categories[0].topic_code)">{{ label(categories[0].topic_code) }}</button><strong v-else>暂无数据</strong>
      </article>
    </section>
    <section class="communication-panel">
      <h2>全量通信 TOP 问题子类</h2>
      <p>按独立原始反馈去重统计，非分页抽样</p>
      <TechChart :option="chart" :loading="loading" :empty="!categories.length" />
      <div class="communication-tags">
        <el-button :type="!selected ? 'primary' : 'default'" @click="selected = ''"
          >全部通信问题</el-button
        >
        <el-button
          v-for="item in categories"
          :key="item.topic_code"
          :type="selected === item.topic_code ? 'primary' : 'default'"
          @click="selectCategory(item.topic_code)"
          >{{ label(item.topic_code) }} · {{ item.count }}</el-button
        >
      </div>
    </section>
    <section ref="evidencePanel" class="communication-panel">
      <h2>近期通信问题证据{{ selected ? ' · ' + label(selected) : '' }}</h2>
      <el-empty v-if="!evidence.length" description="当前范围暂无通信问题证据" />
      <div v-for="(item, index) in evidence" :key="index" class="communication-evidence">
        <div>
          <strong>{{ item.analysis__content__product__name }} · {{ label(item.topic_code) }}</strong
          ><span>{{ item.severity }}</span>
        </div>
        <p>{{ item.evidence_text }}</p>
        <a
          v-if="item.analysis__content__source_url"
          :href="item.analysis__content__source_url"
          target="_blank"
          rel="noopener noreferrer"
          >查看原帖</a
        >
      </div>
    </section>
  </div>
</template>

<style scoped>
.communication-actions { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.communication-link { border: 0; background: none; padding: 0; color: #35b9f0; font: inherit; font-size: 22px; font-weight: 700; cursor: pointer; text-align: left; }
.communication-link:hover { text-decoration: underline; }
.communication-panel { scroll-margin-top: 24px; }
.communication-dashboard {
  color: #edf5ff;
  display: grid;
  gap: 20px;
}
.communication-hero {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 28px;
  border: 1px solid #29435c;
  border-radius: 16px;
  background: linear-gradient(110deg, #12283f, #0a192a);
}
.communication-hero p {
  color: #35b9f0;
  letter-spacing: 2px;
  font-size: 12px;
}
.communication-hero h1 {
  font-size: 30px;
  margin: 10px 0;
}
.communication-hero span,
.communication-panel > p {
  color: #96adc6;
}
.communication-metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
}
.communication-metrics article,
.communication-panel {
  background: #12283f;
  border: 1px solid #29435c;
  border-radius: 14px;
  padding: 22px;
}
.communication-metrics article {
  display: grid;
  gap: 16px;
}
.communication-metrics span {
  color: #96adc6;
}
.communication-metrics strong {
  color: #35b9f0;
  font-size: 28px;
}
.communication-panel h2 {
  font-size: 19px;
  margin: 0 0 10px;
}
.communication-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.communication-tags :deep(.el-button) {
  margin: 0;
}
.communication-evidence {
  padding: 15px 0;
  border-top: 1px solid #29435c;
}
.communication-evidence > div {
  display: flex;
  justify-content: space-between;
  gap: 12px;
}
.communication-evidence p {
  color: #c7d9e9;
}
.communication-evidence a {
  color: #35b9f0;
}
.communication-pagination {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
}
@media (max-width: 850px) {
  .communication-metrics {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .communication-hero {
    flex-wrap: wrap;
    gap: 16px;
  }
}
</style>
