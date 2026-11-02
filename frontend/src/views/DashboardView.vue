<script setup lang="ts">
import { ChatDotRound, FullScreen, Refresh, SwitchButton } from '@element-plus/icons-vue'
import type { EChartsOption } from 'echarts'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { useRoute, useRouter } from 'vue-router'

import {
  getDashboardPreference,
  getDashboardMetricEvidence,
  saveDashboardPreference,
  getDashboardCategories,
  getDashboardOverview,
  getDashboardProducts,
  getDashboardTrends,
} from '@/api'
import DashboardFilters from '@/components/DashboardFilters.vue'
import TechChart from '@/components/TechChart.vue'
import type { DashboardMetricEvidence, DashboardMetricKey } from '@/api'
import type {
  DashboardCategory,
  DashboardFilters as FilterValues,
  DashboardOverview,
  DashboardProductSummary,
  DashboardTrend,
} from '@/types/api'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const preferenceKey = `pvi:dashboard:filters:v1:user:${auth.user?.id ?? 'anonymous'}`
type SavedDashboardFilters = FilterValues & { preset?: string }

function rollingDates(days: number): Pick<FilterValues, 'start_date' | 'end_date'> {
  const end = new Date()
  const start = new Date(end)
  start.setDate(end.getDate() - days + 1)
  const iso = (date: Date) =>
    `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
  return { start_date: iso(start), end_date: iso(end) }
}

function readPreference(): SavedDashboardFilters {
  try {
    const raw = window.localStorage.getItem(preferenceKey)
    if (!raw) return {}
    const parsed: unknown = JSON.parse(raw)
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return {}
    const value = parsed as Record<string, unknown>
    const product_id = Number(value.product_id)
    const source_id = Number(value.source_id)
    const preset = ['7', '30', '90', 'custom'].includes(String(value.preset))
      ? String(value.preset)
      : '30'
    const dates =
      preset === 'custom' &&
      /^\d{4}-\d{2}-\d{2}$/.test(String(value.start_date || '')) &&
      /^\d{4}-\d{2}-\d{2}$/.test(String(value.end_date || ''))
        ? { start_date: String(value.start_date), end_date: String(value.end_date) }
        : rollingDates(Number(preset === 'custom' ? '30' : preset))
    return {
      product_id: Number.isSafeInteger(product_id) && product_id > 0 ? product_id : undefined,
      source_id: Number.isSafeInteger(source_id) && source_id > 0 ? source_id : undefined,
      ...dates,
      preset,
    }
  } catch {
    return {}
  }
}

const savedFilters = readPreference()
const queryId = (value: unknown): number | undefined => {
  const id = Number(value)
  return Number.isSafeInteger(id) && id > 0 ? id : undefined
}
const filters = ref<FilterValues>({
  product_id:
    route.query.product_id !== undefined
      ? queryId(route.query.product_id)
      : savedFilters.product_id,
  source_id:
    route.query.source_id !== undefined ? queryId(route.query.source_id) : savedFilters.source_id,
  start_date:
    typeof route.query.start_date === 'string'
      ? route.query.start_date
      : savedFilters.start_date || '',
  end_date:
    typeof route.query.end_date === 'string' ? route.query.end_date : savedFilters.end_date || '',
})
function savePreference(value: FilterValues): void {
  try {
    const saved = readPreference()
    const rolling = [7, 30, 90].find((days) => {
      const range = rollingDates(days)
      return range.start_date === value.start_date && range.end_date === value.end_date
    })
    const preset = rolling
      ? String(rolling)
      : saved.preset !== 'custom' && !value.start_date && !value.end_date
        ? '30'
        : 'custom'
    window.localStorage.setItem(preferenceKey, JSON.stringify({ ...value, preset }))
    void saveDashboardPreference({
      product_id: value.product_id ?? null,
      source_id: value.source_id ?? null,
      preset: preset as '7' | '30' | '90' | 'custom',
      ...(preset === 'custom' ? { start_date: value.start_date, end_date: value.end_date } : {}),
    }).catch(() => {
      /* Keep the local fallback if the network is unavailable. */
    })
  } catch {
    // Storage may be disabled; dashboard still works with in-memory filters.
  }
}
const overview = ref<DashboardOverview>()
const trend = ref<DashboardTrend[]>([])
const categories = ref<DashboardCategory[]>([])
const products = ref<DashboardProductSummary[]>([])
const loading = ref(false)
const error = ref('')
const stale = ref(false)
const lastSuccessAt = ref<Date>()
const isFullscreen = ref(Boolean(route.query.fullscreen))
let refreshTimer: number | undefined

const issueRate = computed(() => {
  const valid = overview.value?.valid_feedback ?? 0
  const issues = overview.value?.explicit_issue_feedback ?? 0
  return valid > 0 ? `${((100 * issues) / valid).toFixed(1)}%` : '暂无数据'
})
function riskTrendLabel(item: DashboardOverview['watchlist'][number]): string {
  if (item.is_new && item.recent_count > 0) return '近期新增'
  if (item.previous_count === 0) return item.recent_count > 0 ? '上期无反馈' : '近期无反馈'
  if (item.recent_count === 0) return '近期已降至0条'
  if (item.growth_rate === null || !Number.isFinite(item.growth_rate)) return '环比暂无数据'
  if (item.growth_rate > 0) return `环比 +${item.growth_rate}%`
  if (item.growth_rate < 0) return `环比 ${item.growth_rate}%`
  return '环比持平'
}
const topIssue = computed(() => categories.value[0]?.name || '暂无数据')
const metricCards = computed(() => [
  {
    key: 'explicit_issue_feedback',
    label: '用户问题率',
    value: issueRate.value,
    note: '明确问题反馈 / 有效反馈（非产品故障率）',
  },
  {
    key: 'watch_issue_count',
    label: '重点风险问题',
    value: overview.value?.watch_issue_count ?? 0,
    note: '达到高频、严重或增长规则的问题',
  },
  {
    key: undefined,
    label: '最受关注问题',
    value: topIssue.value,
    note: '当前筛选周期反馈最多的问题类别',
  },
  {
    key: undefined,
    label: '有效样本',
    value: overview.value?.valid_feedback ?? 0,
    note: '仅用于说明统计样本规模',
  },
])
const leaderSummary = computed(() => {
  if (!overview.value?.valid_feedback)
    return '当前筛选范围缺少足够的有效反馈，暂不能形成可靠的用户体验结论。'
  const issueCount = overview.value.explicit_issue_feedback
  const watch = overview.value.watch_issue_count
  return `本期有效反馈 ${overview.value.valid_feedback} 条，其中明确问题反馈 ${issueCount} 条，问题反馈占比 ${issueRate.value}。最受关注的类别为「${topIssue.value}」。${watch ? `有 ${watch} 项问题达到重点观察规则，建议优先核查风险变化与原帖证据。` : '目前没有达到重点观察规则的问题。'}`
})

const evidenceVisible = ref(false)
const evidenceLoading = ref(false)
const evidenceError = ref('')
const evidenceMetric = ref<DashboardMetricKey>('raw_feedback')
const evidencePage = ref(1)
const evidence = ref<DashboardMetricEvidence>()
const evidenceSnapshot = ref<FilterValues>({})
const metricDescriptions: Record<DashboardMetricKey, string> = {
  raw_feedback: '原始反馈记录数，包含帖子和回复；以发布时间为准，缺失时采用采集时间。',
  valid_feedback: '原始记录中治理判定可用于 AI 且排除官方内容的去重记录数。',
  ai_analyzed: '当前有效的结构化分析中，通过校验、不需要人工复核的独立原始记录数。',
  explicit_issue_feedback:
    '结构化分析中有明确负面问题证据的独立原始记录数，同一记录多个问题只计算一次。',
  watch_issue_count:
    '按所选时间范围统计高频、严重、持续或近期增长的问题，最多展示五项；不是全部负面反馈。',
}
async function loadEvidence(): Promise<void> {
  evidenceLoading.value = true
  evidenceError.value = ''
  try {
    evidence.value = await getDashboardMetricEvidence(evidenceMetric.value, {
      ...evidenceSnapshot.value,
      page: evidencePage.value,
      page_size: 20,
    })
  } catch (reason) {
    evidenceError.value = reason instanceof Error ? reason.message : '核对明细加载失败'
  } finally {
    evidenceLoading.value = false
  }
}
function openEvidence(key: DashboardMetricKey | undefined): void {
  if (!key) return
  evidenceMetric.value = key
  evidenceSnapshot.value = { ...filters.value }
  evidencePage.value = 1
  evidence.value = undefined
  evidenceVisible.value = true
  void loadEvidence()
}
function evidencePageChange(page: number): void {
  evidencePage.value = page
  void loadEvidence()
}
function openEvidenceRecord(): void {
  if (evidenceMetric.value === 'watch_issue_count') {
    void router.push({ path: '/issues', query: { ...evidenceSnapshot.value } })
  } else {
    void router.push({ path: '/reviews', query: { product: evidenceSnapshot.value.product_id } })
  }
}

const trendOption = computed<EChartsOption>(() => ({
  tooltip: { trigger: 'axis' },
  legend: { data: ['有效用户反馈', '明确负面问题'], textStyle: { color: '#96adc6' } },
  grid: { left: 42, right: 20, top: 54, bottom: 34 },
  xAxis: {
    type: 'category',
    data: trend.value.map((item) => item.date),
    axisLabel: { color: '#96adc6' },
  },
  yAxis: {
    type: 'value',
    minInterval: 1,
    axisLabel: { color: '#96adc6' },
    splitLine: { lineStyle: { color: '#29435c55' } },
  },
  series: [
    {
      name: '有效用户反馈',
      type: 'line',
      smooth: true,
      data: trend.value.map((item) => item.valid_feedback),
      lineStyle: { color: '#35b9f0' },
      itemStyle: { color: '#35b9f0' },
      areaStyle: { color: '#35b9f022' },
    },
    {
      name: '明确负面问题',
      type: 'line',
      smooth: true,
      data: trend.value.map((item) => item.explicit_issues),
      lineStyle: { color: '#ef8f97' },
      itemStyle: { color: '#ef8f97' },
    },
  ],
}))

const categoryOption = computed<EChartsOption>(() => ({
  tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
  grid: { left: 88, right: 28, top: 20, bottom: 28 },
  xAxis: {
    type: 'value',
    minInterval: 1,
    axisLabel: { color: '#96adc6' },
    splitLine: { lineStyle: { color: '#29435c55' } },
  },
  yAxis: {
    type: 'category',
    inverse: true,
    data: categories.value.map((item) => item.name),
    axisLabel: { color: '#edf5ff' },
  },
  series: [
    {
      type: 'bar',
      data: categories.value.map((item) => item.feedback_count),
      barMaxWidth: 18,
      itemStyle: { color: '#32d6c6', borderRadius: [0, 8, 8, 0] },
    },
  ],
}))

async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    const [overviewData, trendData, categoryData, productData] = await Promise.all([
      getDashboardOverview(filters.value),
      getDashboardTrends(filters.value),
      getDashboardCategories(filters.value),
      getDashboardProducts(filters.value),
    ])
    overview.value = overviewData
    trend.value = trendData
    categories.value = categoryData
    products.value = productData
    stale.value = false
    lastSuccessAt.value = new Date()
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '驾驶舱数据加载失败'
    stale.value = Boolean(overview.value)
  } finally {
    loading.value = false
  }
}

async function applyFilters(value: FilterValues): Promise<void> {
  filters.value = value
  savePreference(value)
  await router.replace({ query: { ...value, ...(isFullscreen.value ? { fullscreen: '1' } : {}) } })
  await load()
}

function trendClick(params: unknown): void {
  const item = params as { name?: string }
  if (item.name)
    router.push({
      path: '/issues',
      query: { ...filters.value, start_date: item.name, end_date: item.name },
    })
}

function categoryClick(params: unknown): void {
  const item = params as { dataIndex?: number }
  const category = item.dataIndex === undefined ? undefined : categories.value[item.dataIndex]
  if (category)
    router.push({ path: '/issues', query: { ...filters.value, category: category.code } })
}

async function toggleFullscreen(): Promise<void> {
  if (!isFullscreen.value) {
    try {
      await document.documentElement.requestFullscreen?.()
    } catch {
      // Browsers can deny native fullscreen; projection layout remains available.
    }
    isFullscreen.value = true
  } else {
    if (document.fullscreenElement) await document.exitFullscreen?.()
    isFullscreen.value = false
  }
  await router.replace({
    query: { ...filters.value, ...(isFullscreen.value ? { fullscreen: '1' } : {}) },
  })
}

function syncFullscreen(): void {
  if (!document.fullscreenElement && isFullscreen.value) {
    isFullscreen.value = false
    router.replace({ query: { ...filters.value } })
  }
}

onMounted(() => {
  void (async () => {
    try {
      const preference = await getDashboardPreference()
      if (preference.preset) {
        const fromServer: FilterValues = {
          product_id: preference.product_id ?? undefined,
          source_id: preference.source_id ?? undefined,
          ...(preference.preset === 'custom'
            ? { start_date: preference.start_date || '', end_date: preference.end_date || '' }
            : rollingDates(Number(preference.preset))),
        }
        // Explicit URL filters take precedence over stored user preferences.
        filters.value = {
          product_id:
            route.query.product_id !== undefined
              ? queryId(route.query.product_id)
              : fromServer.product_id,
          source_id:
            route.query.source_id !== undefined
              ? queryId(route.query.source_id)
              : fromServer.source_id,
          start_date:
            typeof route.query.start_date === 'string'
              ? route.query.start_date
              : fromServer.start_date,
          end_date:
            typeof route.query.end_date === 'string' ? route.query.end_date : fromServer.end_date,
        }
        try {
          window.localStorage.setItem(
            preferenceKey,
            JSON.stringify({ ...filters.value, preset: preference.preset }),
          )
        } catch {
          /* ignore */
        }
      }
    } catch {
      /* Offline: keep the local preference. */
    }
    await load()
  })()
  refreshTimer = window.setInterval(() => {
    if (document.visibilityState === 'visible') load()
  }, 300_000)
  document.addEventListener('fullscreenchange', syncFullscreen)
})
onBeforeUnmount(() => {
  window.clearInterval(refreshTimer)
  document.removeEventListener('fullscreenchange', syncFullscreen)
})
</script>

<template>
  <div class="dashboard-page" :class="{ 'projection-mode': isFullscreen }">
    <header class="dashboard-hero">
      <div>
        <p class="eyebrow">PHONE VOICE INTELLIGENCE · V1.0</p>
        <h1>手机用户声音智能驾驶舱</h1>
        <p>全自动采集 · AI 智能识别 · 用户问题洞察</p>
      </div>
      <div class="hero-actions">
        <el-button
          :icon="ChatDotRound"
          @click="router.push({ path: '/ai-assistant', query: { ...filters } })"
          >向 AI 提问</el-button
        >
        <el-button :icon="Refresh" :loading="loading" @click="load">手动刷新</el-button>
        <el-button
          :icon="isFullscreen ? SwitchButton : FullScreen"
          type="primary"
          @click="toggleFullscreen"
          >{{ isFullscreen ? '退出投屏' : '全屏投屏' }}</el-button
        >
      </div>
    </header>
    <section class="tech-panel filter-panel">
      <DashboardFilters v-model="filters" @change="applyFilters" />
      <div class="data-freshness">
        <span class="status-dot" :class="{ warning: stale }" />{{
          stale ? '数据已过期，显示上次成功结果' : '数据状态正常'
        }}<small v-if="lastSuccessAt"
          >页面更新 {{ lastSuccessAt.toLocaleTimeString('zh-CN') }}</small
        >
      </div>
    </section>
    <el-alert
      v-if="error"
      :title="error"
      type="error"
      show-icon
      :closable="false"
      class="dashboard-alert"
    />
    <section class="metric-grid" v-loading="loading && !overview">
      <el-tooltip
        v-for="card in metricCards"
        :key="card.label"
        :content="card.note"
        placement="top"
      >
        <article
          class="metric-card"
          :class="{ clickable: card.key }"
          :role="card.key ? 'button' : undefined"
          :tabindex="card.key ? 0 : undefined"
          @click="openEvidence(card.key as DashboardMetricKey | undefined)"
          @keydown.enter="openEvidence(card.key as DashboardMetricKey | undefined)"
          @keydown.space.prevent="openEvidence(card.key as DashboardMetricKey | undefined)"
        >
          <span>{{ card.label }} <small v-if="card.key">点击核对明细 ›</small></span
          ><strong>{{ card.value }}</strong
          ><small>{{ card.note }}</small>
        </article>
      </el-tooltip>
    </section>
    <section class="tech-panel leader-summary">
      <div class="panel-heading">
        <div>
          <h2>本期用户声音摘要</h2>
          <p>基于当前筛选条件的真实统计数据生成，不包含模型推测</p>
        </div>
      </div>
      <p>{{ leaderSummary }}</p>
      <small>统计仅代表已收集的用户反馈，不代表全部手机用户或真实故障率。</small>
    </section>
    <section class="dashboard-grid two-columns">
      <article class="tech-panel chart-panel">
        <div class="panel-heading">
          <div>
            <h2>用户体验与问题趋势</h2>
            <p>有效反馈与 AI 确认明确负面问题</p>
          </div>
        </div>
        <TechChart
          :option="trendOption"
          :loading="loading"
          :empty="!trend.length"
          @chart-click="trendClick"
        />
      </article>
      <article class="tech-panel chart-panel">
        <div class="panel-heading">
          <div>
            <h2>TOP 用户问题</h2>
            <p>按独立反馈去重，点击类别下钻</p>
          </div>
        </div>
        <TechChart
          :option="categoryOption"
          :loading="loading"
          :empty="!categories.length"
          @chart-click="categoryClick"
        />
      </article>
    </section>
    <section class="dashboard-grid two-columns lower-grid">
      <article class="tech-panel">
        <div class="panel-heading">
          <div>
            <h2>机型体验对比</h2>
            <p>动态加载当前已启用手机产品</p>
          </div>
          <el-button text @click="router.push('/comparison')">进入对比中心</el-button>
        </div>
        <div v-if="products.length" class="product-cards">
          <button
            v-for="item in products"
            :key="item.product_id"
            type="button"
            class="product-card"
            @click="
              router.push({ path: '/issues', query: { ...filters, product_id: item.product_id } })
            "
          >
            <strong>{{ item.product_name }}</strong>
            <div>
              <span>有效样本 {{ item.valid_feedback }}</span
              ><span
                >问题率
                {{
                  item.valid_feedback
                    ? ((100 * item.explicit_issue_feedback) / item.valid_feedback).toFixed(1) + '%'
                    : '暂无'
                }}</span
              >
            </div>
            <div>
              <span>明确问题 {{ item.explicit_issue_feedback }}</span
              ><span>主要问题 {{ item.top_issue || '暂无' }}</span>
            </div>
          </button>
        </div>
        <el-empty v-else description="当前范围暂无产品反馈" />
      </article>
      <article class="tech-panel">
        <div class="panel-heading">
          <div>
            <h2>风险预警与重点观察</h2>
            <p>按严重度、高频、持续出现或近期增长识别重点问题</p>
          </div>
        </div>
        <div v-if="overview?.watchlist.length" class="watch-list">
          <button
            v-for="item in overview.watchlist"
            :key="item.id"
            type="button"
            @click="router.push({ path: '/issues', query: { ...filters, search: item.name } })"
          >
            <span class="severity">{{ item.severity }}</span
            ><strong>{{ item.name }}</strong
            ><small>{{ item.product_name }}</small
            ><em :title="`近7天 ${item.recent_count} 条，上7天 ${item.previous_count} 条`">{{
              riskTrendLabel(item)
            }}</em>
          </button>
        </div>
        <el-empty v-else description="当前周期没有达到关注规则的问题，可点击上方指标查看规则" />
      </article>
    </section>
    <el-dialog
      v-model="evidenceVisible"
      title="驾驶舱指标核对明细"
      width="min(920px, 96vw)"
      destroy-on-close
    >
      <div class="evidence-summary">
        <h3>{{ metricCards.find((card) => card.key === evidenceMetric)?.label }}</h3>
        <p>{{ metricDescriptions[evidenceMetric] }}</p>
        <p>
          产品 ID：{{ evidenceSnapshot.product_id || '全部' }} · 来源 ID：{{
            evidenceSnapshot.source_id || '全部'
          }}
        </p>
        <p>
          实际统计日期：{{
            evidence?.start_date || evidenceSnapshot.start_date || '默认最近30天'
          }}
          至 {{ evidence?.end_date || evidenceSnapshot.end_date || '今天' }}
        </p>
        <strong>核对总数：{{ evidence?.count ?? '加载中' }}</strong>
        <p v-if="evidenceMetric === 'watch_issue_count' && overview?.watch_diagnostics">
          识别问题类别 {{ overview.watch_diagnostics.total_candidates }} · 符合关注规则
          {{ overview.watch_diagnostics.eligible_count }} · 未入选
          {{ overview.watch_diagnostics.excluded_count }} · 高频门槛
          {{ overview.watch_diagnostics.thresholds.min_feedback }} 条
        </p>
        <div
          v-if="
            evidenceMetric === 'watch_issue_count' && overview?.watch_diagnostics?.excluded?.length
          "
        >
          <strong>未入选示例及原因</strong>
          <p v-for="item in overview.watch_diagnostics.excluded.slice(0, 10)" :key="item.id">
            {{ item.name }}：{{ item.excluded_reason }}
          </p>
        </div>
      </div>
      <el-alert
        v-if="evidenceError"
        type="error"
        :title="evidenceError"
        :closable="false"
        show-icon
      />
      <el-table :data="evidence?.results || []" v-loading="evidenceLoading" height="390" stripe>
        <el-table-column prop="id" label="记录 ID" width="110" />
        <el-table-column prop="product" label="产品" width="125" />
        <el-table-column prop="source" label="来源" width="125" />
        <el-table-column prop="title" label="帖子/问题" min-width="170" show-overflow-tooltip />
        <el-table-column
          prop="description"
          label="原文摘要/判定依据"
          min-width="210"
          show-overflow-tooltip
        />
        <el-table-column prop="published_at" label="时间" width="170" />
        <el-table-column label="核对" width="110">
          <template #default="{ row }">
            <el-link v-if="row.source_url" :href="row.source_url" target="_blank" type="primary"
              >原帖链接</el-link
            >
            <el-button
              v-else-if="evidenceMetric === 'watch_issue_count'"
              link
              type="primary"
              @click="openEvidenceRecord(row.id)"
              >查看问题</el-button
            >
            <span v-else>无原帖链接</span>
          </template>
        </el-table-column>
      </el-table>
      <el-pagination
        class="evidence-pagination"
        background
        layout="total, prev, pager, next"
        :total="evidence?.count || 0"
        :page-size="20"
        :current-page="evidencePage"
        @current-change="evidencePageChange"
      />
      <p class="evidence-note">
        核对明细与驾驶舱使用相同的后端筛选条件；原始帖子链接仅在数据源提供时展示。
      </p>
    </el-dialog>
    <p class="dashboard-disclaimer">{{ overview?.disclaimer }}</p>
  </div>
</template>

<style scoped>
.dashboard-page {
  color: var(--pvi-text);
}
.dashboard-hero {
  display: flex;
  justify-content: space-between;
  gap: 24px;
  margin-bottom: 18px;
}
.dashboard-hero h1 {
  margin: 4px 0 8px;
  font-size: clamp(25px, 2.3vw, 38px);
  letter-spacing: 0.02em;
}
.dashboard-hero p {
  margin: 0;
  color: var(--pvi-muted);
}
.eyebrow {
  color: var(--pvi-blue) !important;
  font-size: 12px;
  letter-spacing: 0.18em;
}
.hero-actions {
  display: flex;
  align-items: flex-start;
  gap: 10px;
}
.filter-panel {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
}
.data-freshness {
  display: flex;
  align-items: center;
  gap: 7px;
  color: var(--pvi-muted);
  font-size: 13px;
  white-space: nowrap;
}
.data-freshness small {
  margin-left: 8px;
}
.status-dot {
  width: 8px;
  height: 8px;
  background: var(--pvi-green);
  border-radius: 50%;
  box-shadow: 0 0 10px var(--pvi-green);
}
.status-dot.warning {
  background: var(--pvi-orange);
  box-shadow: 0 0 10px var(--pvi-orange);
}
.dashboard-alert {
  margin-bottom: 16px;
}
.metric-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}
.metric-card {
  min-height: 142px;
  padding: 19px;
  background: linear-gradient(145deg, #12283f, #0d2136);
  border: 1px solid var(--pvi-border);
  border-radius: 14px;
  box-shadow: 0 14px 34px #020a1333;
}
.metric-card.clickable {
  cursor: pointer;
}
.metric-card.clickable:hover,
.metric-card.clickable:focus-visible {
  border-color: var(--pvi-blue);
  outline: none;
}
.evidence-summary {
  margin-bottom: 16px;
}
.evidence-summary h3 {
  margin: 0 0 8px;
}
.evidence-summary p,
.evidence-note {
  color: var(--pvi-muted);
  font-size: 13px;
}
.evidence-pagination {
  margin-top: 16px;
  justify-content: flex-end;
}
.metric-card span,
.metric-card small {
  display: block;
  color: var(--pvi-muted);
}
.metric-card strong {
  display: block;
  margin: 17px 0 12px;
  color: var(--pvi-text);
  font-size: clamp(25px, 2vw, 34px);
}
.metric-card small {
  font-size: 11px;
  line-height: 1.45;
}
.leader-summary {
  margin-bottom: 16px;
}
.leader-summary > p {
  line-height: 1.8;
}
.leader-summary > small {
  color: var(--pvi-muted);
}
.dashboard-grid {
  display: grid;
  gap: 16px;
}
.two-columns {
  grid-template-columns: minmax(0, 1.35fr) minmax(340px, 0.85fr);
}
.lower-grid {
  margin-top: 16px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}
.tech-panel {
  padding: 18px;
  background: var(--pvi-card);
  border: 1px solid var(--pvi-border);
  border-radius: 14px;
}
.panel-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}
.panel-heading h2 {
  margin: 0 0 5px;
  font-size: 17px;
}
.panel-heading p {
  margin: 0;
  color: var(--pvi-muted);
  font-size: 12px;
}
.product-cards {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin-top: 18px;
}
.product-card {
  padding: 16px;
  color: inherit;
  text-align: left;
  background: #0a192a;
  border: 1px solid #29435c;
  border-radius: 12px;
  cursor: pointer;
}
.product-card:hover {
  border-color: var(--pvi-blue);
  transform: translateY(-1px);
}
.product-card strong {
  display: block;
  margin-bottom: 13px;
  font-size: 16px;
}
.product-card div {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  margin-top: 7px;
  color: var(--pvi-muted);
  font-size: 12px;
}
.watch-list {
  display: grid;
  gap: 9px;
  margin-top: 16px;
}
.watch-list button {
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  gap: 10px;
  padding: 12px;
  color: inherit;
  text-align: left;
  background: #0a192a;
  border: 1px solid #29435c;
  border-radius: 10px;
  cursor: pointer;
}
.watch-list small {
  grid-column: 2;
  color: var(--pvi-muted);
}
.watch-list em {
  grid-row: 1 / span 2;
  grid-column: 3;
  color: var(--pvi-orange);
  font-style: normal;
}
.severity {
  padding: 4px 7px;
  font-size: 10px;
  background: #ef8f9722;
  border: 1px solid #ef8f9755;
  border-radius: 6px;
}
.dashboard-disclaimer {
  color: var(--pvi-muted);
  font-size: 12px;
  text-align: right;
}
.projection-mode {
  min-height: 100vh;
  padding: 22px;
  background: var(--pvi-bg);
}
@media (max-width: 1400px) {
  .metric-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}
@media (max-width: 980px) {
  .two-columns,
  .lower-grid {
    grid-template-columns: 1fr;
  }
  .filter-panel,
  .dashboard-hero {
    align-items: stretch;
    flex-direction: column;
  }
}
@media (max-width: 640px) {
  .metric-grid,
  .product-cards {
    grid-template-columns: 1fr;
  }
  .hero-actions {
    width: 100%;
  }
  .hero-actions .el-button {
    flex: 1;
  }
}
@media (prefers-reduced-motion: no-preference) {
  .metric-card,
  .product-card {
    transition:
      border-color 0.18s ease,
      transform 0.18s ease;
  }
}
</style>
