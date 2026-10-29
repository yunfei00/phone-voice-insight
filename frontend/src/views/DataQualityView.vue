<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'

import {
  getDataQualitySummary,
  getReviewQualities,
  getProducts,
  getSources,
  processGovernanceBatch,
  startAsyncGovernance,
  startFullGovernance,
  getGovernanceTaskHistory,
  getGovernanceTaskStatus,
  retryGovernanceTask,
  startGovernanceAIReview,
  startFullGovernanceAIReview,
  getFullGovernanceAIProgress,
  stopFullGovernanceAI,
  getGovernanceAIHistory,
  getGovernanceAIResults,
  getAICorpusSummary,
  retryGovernanceAIBatch,
} from '@/api'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import type {
  Product,
  DataSource,
  DataQualitySummary,
  ExclusionReason,
  ReviewQuality,
} from '@/types/api'
import type {
  GovernanceTaskInfo,
  GovernanceAIBatchInfo,
  GovernanceAIResultInfo,
  FullGovernanceAIProgress,
  AICorpusSummary,
} from '@/api'

const emptySummary = (): DataQualitySummary => ({
  total: 0,
  eligible: 0,
  excluded: 0,
  eligibility_rate: 0,
  categories: {
    official: 0,
    low_information: 0,
    promotional: 0,
    noise: 0,
    duplicate: 0,
    product_not_matched: 0,
    empty: 0,
  },
  exclusion_reasons: {
    NONE: 0,
    EMPTY_CONTENT: 0,
    OFFICIAL_CONTENT: 0,
    PRODUCT_NOT_MATCHED: 0,
    PAGE_NOISE: 0,
    PROMOTIONAL: 0,
    LOW_INFORMATION: 0,
    DUPLICATE: 0,
    INVALID_ENCODING: 0,
    PARSER_ARTIFACT: 0,
    OTHER: 0,
  },
})

const auth = useAuthStore()
const products = ref<Product[]>([])
const sources = ref<DataSource[]>([])
const selectedProduct = ref<number | undefined>(undefined)
const selectedSource = ref<number | undefined>(undefined)
const governanceLimit = ref(20)
const governanceBusy = ref(false)
const governanceTasks = ref<GovernanceTaskInfo[]>([])
const taskLoading = ref(false)
const aiBusy = ref(false)
const fullAIProgress = ref<FullGovernanceAIProgress | null>(null)
const corpusSummary = ref<AICorpusSummary | null>(null)
const fullAIId = ref<number | null>(null)
const stoppingFullAI = ref(false)
const aiBatches = ref<GovernanceAIBatchInfo[]>([])
const aiResults = ref<GovernanceAIResultInfo[]>([])
const governanceTaskPage = ref(1)
const governanceTaskTotal = ref(0)
const aiBatchPage = ref(1)
const aiBatchTotal = ref(0)
const aiResultPage = ref(1)
const aiResultTotal = ref(0)
let aiPollTimer: ReturnType<typeof setInterval> | undefined
let taskPollTimer: ReturnType<typeof setInterval> | undefined
let taskPollInFlight = false
const preview = ref<{ total: number; eligible: number; excluded: number } | null>(null)
const rows = ref<ReviewQuality[]>([])
const summary = ref<DataQualitySummary>(emptySummary())
const loading = ref(false)
const error = ref('')
const total = ref(0)
const page = ref(1)
const selected = ref<ReviewQuality | null>(null)
const filters = reactive({
  eligible: '',
  exclusion_reason: '',
  record_type: '',
  author_role: '',
  quality_score_min: undefined as number | undefined,
  quality_score_max: undefined as number | undefined,
})

const recordTypeLabels: Record<string, string> = {
  REVIEW: '评价',
  APPEND_REVIEW: '追评',
  THREAD: '帖子',
  REPLY: '回复',
  OFFICIAL_REPLY: '官方回复',
}

const authorRoleLabels: Record<string, string> = {
  USER: '普通用户',
  OFFICIAL: '官方',
  MODERATOR: '版主',
  EXPERT: '达人',
  UNKNOWN: '未知',
}

function formatPublishedAt(value: string | null): string {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hourCycle: 'h23',
  }).formatToParts(date)
  const part = (type: string) => parts.find((item) => item.type === type)?.value || ''
  return `${part('year')}-${part('month')}-${part('day')} ${part('hour')}:${part('minute')}:${part('second')}`
}

const reasonLabels: Record<ExclusionReason, string> = {
  NONE: '不排除',
  EMPTY_CONTENT: '空文本',
  OFFICIAL_CONTENT: '官方内容',
  PRODUCT_NOT_MATCHED: '产品不相关',
  PAGE_NOISE: '页面噪声',
  PROMOTIONAL: '宣传内容',
  LOW_INFORMATION: '低信息',
  DUPLICATE: '重复',
  INVALID_ENCODING: '编码异常',
  PARSER_ARTIFACT: '解析残留',
  NO_PRODUCT_EXPERIENCE_SIGNAL: '无产品体验信号',
  SOCIAL_INTERACTION: '纯社交互动',
  RESOURCE_SHARE: '资源分享',
  PHOTO_SHARE: '图片作品分享',
  METADATA_REPLY: '纯元数据回复',
  OTHER: '其他',
}

const breakdown = computed(
  () =>
    [
      ['官方回复', summary.value.categories.official],
      ['低信息', summary.value.categories.low_information],
      ['宣传内容', summary.value.categories.promotional],
      ['页面噪声', summary.value.categories.noise],
      ['重复', summary.value.categories.duplicate],
      ['不相关', summary.value.categories.product_not_matched],
      ['空文本', summary.value.categories.empty],
    ] as const,
)

function queryParams(): Record<string, string | number | boolean | undefined> {
  return {
    page: page.value,
    page_size: 10,
    product: selectedProduct.value,
    source: selectedSource.value,
    eligible: filters.eligible || undefined,
    exclusion_reason: filters.exclusion_reason || undefined,
    record_type: filters.record_type || undefined,
    author_role: filters.author_role || undefined,
    quality_score_min: filters.quality_score_min,
    quality_score_max: filters.quality_score_max,
    ordering: '-processed_at',
  }
}

async function loadData(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    const [qualityPage, qualitySummary] = await Promise.all([
      getReviewQualities(queryParams()),
      getDataQualitySummary({ product: selectedProduct.value, source: selectedSource.value }),
    ])
    rows.value = qualityPage.results
    total.value = qualityPage.count
    summary.value = qualitySummary
  } catch {
    error.value = '数据质量结果加载失败，请先运行治理 Pipeline。'
  } finally {
    loading.value = false
  }
}

function applyFilters(): void {
  page.value = 1
  void loadData()
}

function ratio(value: number): string {
  return summary.value.total ? `${((value / summary.value.total) * 100).toFixed(1)}%` : '0.0%'
}

async function runGovernance(dryRun: boolean): Promise<void> {
  if (!selectedProduct.value) return
  governanceBusy.value = true
  try {
    const result = await processGovernanceBatch({
      product_id: selectedProduct.value,
      source_id: selectedSource.value,
      limit: governanceLimit.value,
      dry_run: dryRun,
    })
    preview.value = result
    ElMessage.success(
      result.total === 0
        ? '该产品没有待治理的数据'
        : dryRun
          ? '预览完成，未写入治理结果'
          : '批量治理完成',
    )
    if (!dryRun) await loadData()
  } catch {
    ElMessage.error('治理执行失败，请检查管理员权限或后端日志')
  } finally {
    governanceBusy.value = false
  }
}

async function loadGovernanceTasks(): Promise<void> {
  if (!auth.isAdmin) return
  taskLoading.value = true
  try {
    const history = await getGovernanceTaskHistory({
      product_id: selectedProduct.value,
      page: governanceTaskPage.value,
      page_size: 10,
    })
    governanceTaskTotal.value = history.count
    governanceTasks.value = await Promise.all(
      history.results.map(async (task) => {
        if (task.status !== 'RUNNING' && task.status !== 'PENDING') return task
        try {
          return await getGovernanceTaskStatus(task.id)
        } catch {
          return task
        }
      }),
    )
    if (
      !governanceTasks.value.some((task) => task.status === 'RUNNING' || task.status === 'PENDING')
    )
      stopTaskPolling()
  } catch {
    ElMessage.error('治理任务列表加载失败')
  } finally {
    taskLoading.value = false
  }
}

function aiBatchStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    PENDING: '等待执行',
    RUNNING: '正在执行',
    SUCCESS: '已完成',
    PARTIAL: '部分失败',
    FAILED: '失败',
  }
  return labels[status] || status
}

async function loadAIReviews(): Promise<void> {
  if (!auth.isAdmin) return
  try {
    const history = await getGovernanceAIHistory({
      product_id: selectedProduct.value,
      source_id: selectedSource.value,
      page: aiBatchPage.value,
      page_size: 10,
    })
    aiBatchTotal.value = history.count
    aiBatches.value = history.results
    if (selectedProduct.value) {
      corpusSummary.value = await getAICorpusSummary(selectedProduct.value, selectedSource.value)
      const results = await getGovernanceAIResults(selectedProduct.value, {
        page: aiResultPage.value,
        page_size: 10,
        source_id: selectedSource.value,
      })
      aiResultTotal.value = results.count
      aiResults.value = results.results
    } else {
      aiResultTotal.value = 0
      aiResults.value = []
      corpusSummary.value = null
    }
    if (selectedProduct.value) {
      fullAIProgress.value = await getFullGovernanceAIProgress({
        product_id: selectedProduct.value,
        source_id: selectedSource.value,
      })
      fullAIId.value = fullAIProgress.value?.id ?? null
    } else {
      fullAIProgress.value = null
      fullAIId.value = null
    }
    if (
      !aiBatches.value.some((b) => b.status === 'PENDING' || b.status === 'RUNNING') &&
      fullAIProgress.value?.status !== 'RUNNING'
    )
      stopAIPolling()
  } catch {
    ElMessage.error('AI 判断状态加载失败')
  }
}

function stopAIPolling(): void {
  if (aiPollTimer !== undefined) clearInterval(aiPollTimer)
  aiPollTimer = undefined
}

function startAIPolling(): void {
  if (aiPollTimer !== undefined) return
  aiPollTimer = setInterval(() => {
    void loadAIReviews()
  }, 3000)
}

async function retryAIReview(batchId: number): Promise<void> {
  aiBusy.value = true
  try {
    await retryGovernanceAIBatch(batchId)
    ElMessage.success('失败数据已重新提交')
    await loadAIReviews()
    startAIPolling()
  } catch {
    ElMessage.error('重试失败，请检查后台任务状态')
  } finally {
    aiBusy.value = false
  }
}

async function startAIReview(): Promise<void> {
  if (!selectedProduct.value) return
  aiBusy.value = true
  try {
    const batch = await startGovernanceAIReview({
      product_id: selectedProduct.value,
      source_id: selectedSource.value ?? null,
      limit: governanceLimit.value,
    })
    ElMessage.success(`已提交 ${batch.total} 条 AI 判断数据`)
    await loadAIReviews()
    startAIPolling()
  } catch {
    ElMessage.error('AI 判断任务提交失败，请检查模型配置及后台服务')
  } finally {
    aiBusy.value = false
  }
}

async function startFullAIReview(): Promise<void> {
  if (!selectedProduct.value) return
  try {
    await ElMessageBox.confirm(
      '将按每批 100 条自动调用 AI，直到全部待处理记录完成。此操作会产生模型费用，确定继续？',
      '一键 AI 判断全部',
      { type: 'warning', confirmButtonText: '确认执行', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  aiBusy.value = true
  try {
    const result = await startFullGovernanceAIReview({
      product_id: selectedProduct.value,
      source_id: selectedSource.value ?? null,
    })
    if (result.id) fullAIId.value = result.id
    ElMessage.success(
      result.total ? `全量 AI 判断已启动，共 ${result.total} 条` : '没有待 AI 判断的数据',
    )
    await loadAIReviews()
    startAIPolling()
  } catch {
    ElMessage.error('全量 AI 判断启动失败，请检查后台任务与模型配置')
  } finally {
    aiBusy.value = false
  }
}

function formatTokenCount(value: number): string {
  if (value >= 1_000_000) return (value / 1_000_000).toFixed(2) + 'M tokens'
  if (value >= 1_000) return (value / 1_000).toFixed(1) + 'K tokens'
  return value.toLocaleString() + ' tokens'
}

async function stopFullAIReview(): Promise<void> {
  if (!fullAIId.value) return
  try {
    await ElMessageBox.confirm(
      '停止后不再提交后续批次，已完成的 AI 结果将保留。确定停止？',
      '停止全量任务',
      { type: 'warning' },
    )
  } catch {
    return
  }
  stoppingFullAI.value = true
  try {
    await stopFullGovernanceAI(fullAIId.value)
    ElMessage.success('已请求停止，当前正在处理的记录完成后退出')
    await loadAIReviews()
  } catch {
    ElMessage.error('停止请求失败，请稍后重试')
  } finally {
    stoppingFullAI.value = false
  }
}

function stopTaskPolling(): void {
  if (taskPollTimer !== undefined) {
    clearInterval(taskPollTimer)
    taskPollTimer = undefined
  }
}

function startTaskPolling(): void {
  if (taskPollTimer !== undefined) return
  taskPollTimer = setInterval(async () => {
    if (taskPollInFlight) return
    taskPollInFlight = true
    try {
      await loadGovernanceTasks()
      await loadData()
    } finally {
      taskPollInFlight = false
    }
  }, 3000)
}

async function startBackgroundGovernance(): Promise<void> {
  if (!selectedProduct.value) return
  governanceBusy.value = true
  try {
    await startAsyncGovernance({
      product_id: selectedProduct.value,
      source_id: selectedSource.value,
      limit: governanceLimit.value,
      dry_run: false,
    })
    ElMessage.success('下一批未治理数据已提交后台处理')
    await loadGovernanceTasks()
    startTaskPolling()
  } catch {
    ElMessage.error('后台任务提交失败')
  } finally {
    governanceBusy.value = false
  }
}

async function startAllGovernance(): Promise<void> {
  if (!selectedProduct.value) return
  governanceBusy.value = true
  try {
    const result = await startFullGovernance({
      product_id: selectedProduct.value,
      source_id: selectedSource.value ?? null,
    })
    ElMessage.success(
      result.task ? `已提交全部 ${result.task.total} 条待治理数据` : '当前范围没有待治理数据',
    )
    await loadGovernanceTasks()
    await loadData()
    if (result.task) startTaskPolling()
  } catch {
    ElMessage.error('全量治理启动失败，请检查是否已有进行中的任务')
  } finally {
    governanceBusy.value = false
  }
}

async function retryBackgroundGovernance(taskId: number): Promise<void> {
  try {
    await retryGovernanceTask(taskId)
    ElMessage.success('失败记录重试任务已提交')
    await loadGovernanceTasks()
    startTaskPolling()
  } catch {
    ElMessage.error('重试失败')
  }
}

onMounted(async () => {
  try {
    const [productPage, sourcePage] = await Promise.all([
      getProducts({ page_size: 100 }),
      getSources({ page_size: 100 }),
    ])
    products.value = productPage.results
    sources.value = sourcePage.results
    selectedProduct.value = products.value[0]?.id
  } catch {
    ElMessage.warning('产品或来源列表加载失败')
  }
  await loadData()
  if (auth.isAdmin) {
    await loadGovernanceTasks()
    await loadAIReviews()
    if (
      aiBatches.value.some((b) => b.status === 'PENDING' || b.status === 'RUNNING') ||
      fullAIProgress.value?.status === 'RUNNING'
    )
      startAIPolling()
    if (
      governanceTasks.value.some((task) => task.status === 'RUNNING' || task.status === 'PENDING')
    )
      startTaskPolling()
  }
})

async function changeScope(): Promise<void> {
  page.value = 1
  governanceTaskPage.value = 1
  aiBatchPage.value = 1
  aiResultPage.value = 1
  await Promise.all([loadData(), loadGovernanceTasks(), loadAIReviews()])
  if (
    aiBatches.value.some((b) => b.status === 'PENDING' || b.status === 'RUNNING') ||
    fullAIProgress.value?.status === 'RUNNING'
  )
    startAIPolling()
}
onUnmounted(() => {
  stopTaskPolling()
  stopAIPolling()
})
</script>

<template>
  <div>
    <div class="page-header">
      <div>
        <h1 class="page-title">数据质量</h1>
        <p class="page-description">治理结果独立于原始反馈；质量分表示语料适用性，不是手机评分。</p>
      </div>
      <el-button :loading="loading" @click="loadData">刷新</el-button>
    </div>

    <el-alert v-if="error" :title="error" type="error" :closable="false" class="notice" />

    <section class="panel governance-actions">
      <h3>产品与处理范围</h3>
      <p>以下产品和来源范围统一作用于质量统计、规则治理、AI 自动决策、任务历史和治理结果。</p>
      <div class="filters">
        <el-select
          v-model="selectedProduct"
          placeholder="选择手机产品"
          style="width: 230px"
          @change="changeScope"
        >
          <el-option
            v-for="product in products"
            :key="product.id"
            :label="product.name"
            :value="product.id"
          />
        </el-select>
        <el-select
          v-model="selectedSource"
          placeholder="全部数据来源"
          clearable
          style="width: 210px"
          @change="changeScope"
        >
          <el-option
            v-for="source in sources"
            :key="source.id"
            :label="source.name"
            :value="source.id"
          />
        </el-select>
        <span>处理数量</span>
        <el-input-number v-model="governanceLimit" :min="1" :max="100" />
      </div>
    </section>

    <div class="metric-grid">
      <div class="metric-card">
        <span>原始反馈总数</span><strong>{{ summary.total }}</strong>
      </div>
      <div class="metric-card">
        <span>AI 可用语料数</span><strong>{{ summary.eligible }}</strong>
      </div>
      <div class="metric-card">
        <span>排除数量</span><strong>{{ summary.excluded }}</strong>
      </div>
      <div class="metric-card">
        <span>可用率</span><strong>{{ (summary.eligibility_rate * 100).toFixed(1) }}%</strong>
      </div>
    </div>

    <section v-if="auth.isAdmin" class="panel governance-actions">
      <h3>AI 自动判断与自动决策</h3>
      <div v-if="corpusSummary" class="panel" style="margin-bottom: 16px">
        <h4>最终有效语料统计（当前产品及来源）</h4>
        <el-row :gutter="12">
          <el-col
            v-for="metric in [
              { label: '已治理总量', value: corpusSummary.total },
              { label: '规则可用', value: corpusSummary.rule_eligible },
              { label: '规则排除', value: corpusSummary.rule_excluded },
              { label: 'AI 确认有效', value: corpusSummary.ai_accepted },
              { label: 'AI 排除', value: corpusSummary.ai_rejected },
              { label: 'AI 无法判断（已跳过）', value: corpusSummary.ai_uncertain },
              { label: 'AI 技术失败', value: corpusSummary.ai_failed },
              { label: '尚未 AI 判断', value: corpusSummary.ai_unprocessed },
              { label: '最终可分析', value: corpusSummary.final_eligible },
            ]"
            :key="metric.label"
            :xs="12"
            :sm="8"
            :md="6"
          >
            <el-statistic :title="metric.label" :value="metric.value" style="padding: 12px 0" />
          </el-col>
        </el-row>
        <p>
          统计按语料去重，取每条语料最新 AI 判断；最终可分析仅包括规则可用且最新 AI
          结论为自动接受的数据。无法判断及技术失败的数据自动跳过，不进入分析；原始记录仍保留。
        </p>
      </div>

      <p>
        系统自动接受明确有效反馈、排除无效内容；证据不足标记为不确定且不进入分析，技术错误仅有限重试。
      </p>
      <div class="filters">
        <el-button
          type="primary"
          :loading="aiBusy"
          :disabled="!selectedProduct"
          @click="startAIReview"
          >立即运行自动判断</el-button
        >
        <el-button
          type="success"
          :loading="aiBusy"
          :disabled="!selectedProduct"
          @click="startFullAIReview"
          >一键 AI 判断全部</el-button
        >
        <el-button
          type="danger"
          :disabled="!fullAIId || !fullAIProgress?.can_stop || stoppingFullAI"
          :loading="stoppingFullAI"
          @click="stopFullAIReview"
          >停止全量任务</el-button
        >
        <el-button @click="loadAIReviews">查看 AI 判断结果</el-button>
        <span v-if="aiBatches.some((b) => b.status === 'RUNNING' || b.status === 'PENDING')"
          >每 3 秒自动更新</span
        >
      </div>
      <div v-if="fullAIProgress" class="panel" style="margin-bottom: 12px">
        <strong>全量进度：{{ fullAIProgress.processed }} / {{ fullAIProgress.total }}</strong>
        <el-progress
          :percentage="
            fullAIProgress.total
              ? Math.min(100, Math.round((fullAIProgress.processed / fullAIProgress.total) * 100))
              : 100
          "
        />
        <p>
          状态：{{ fullAIProgress.status }} · 剩余：{{ fullAIProgress.remaining }} · 自动接受：{{
            fullAIProgress.accepted
          }}
          · 自动排除：{{ fullAIProgress.rejected }} · 自动跳过：{{ fullAIProgress.uncertain }} ·
          失败：{{ fullAIProgress.failed }}
        </p>
        <p>
          Token 消耗（单位：tokens）：输入 {{ formatTokenCount(fullAIProgress.prompt_tokens) }} ·
          输出 {{ formatTokenCount(fullAIProgress.completion_tokens) }} · 累计
          {{ formatTokenCount(fullAIProgress.prompt_tokens + fullAIProgress.completion_tokens) }}
        </p>
        <p v-if="fullAIProgress.processed > 0">
          预计总消耗：{{
            formatTokenCount(
              Math.round(
                ((fullAIProgress.prompt_tokens + fullAIProgress.completion_tokens) /
                  fullAIProgress.processed) *
                  fullAIProgress.total,
              ),
            )
          }}
          · 预计剩余：{{
            formatTokenCount(
              Math.max(
                0,
                Math.round(
                  ((fullAIProgress.prompt_tokens + fullAIProgress.completion_tokens) /
                    fullAIProgress.processed) *
                    fullAIProgress.remaining,
                ),
              ),
            )
          }}
          <span v-if="fullAIProgress.processed < 20">（样本较少，仅供参考）</span>
        </p>
        <p v-else>预计 Token 消耗：等待首批处理数据后估算</p>
      </div>
      <el-table :data="aiBatches" size="small" style="margin-bottom: 12px">
        <el-table-column prop="id" label="任务编号" width="95" />
        <el-table-column label="状态" width="120">
          <template #default="{ row }">{{ aiBatchStatusLabel(row.status) }}</template>
        </el-table-column>
        <el-table-column label="进度">
          <template #default="{ row }">{{ row.processed }} / {{ row.total }}</template>
        </el-table-column>
        <el-table-column prop="accepted" label="自动接受" />
        <el-table-column prop="rejected" label="自动排除" />
        <el-table-column prop="uncertain" label="自动跳过" />
        <el-table-column prop="failed" label="技术错误" />
        <el-table-column
          prop="error_code"
          label="任务错误代码"
          min-width="160"
          show-overflow-tooltip
        />
        <el-table-column label="操作" width="100">
          <template #default="{ row }">
            <el-button
              v-if="row.failed > 0 || row.status === 'FAILED'"
              size="small"
              :disabled="aiBusy"
              @click="retryAIReview(row.id)"
              >重试失败</el-button
            >
          </template>
        </el-table-column>
      </el-table>
      <el-pagination
        v-model:current-page="aiBatchPage"
        :page-size="10"
        :total="aiBatchTotal"
        layout="prev, pager, next, total"
        @current-change="loadAIReviews"
      />
      <el-table :data="aiResults" size="small">
        <el-table-column prop="review_id" label="记录 ID" width="95" />
        <el-table-column label="规则结论" width="105">
          <template #default="{ row }">{{ row.rule_eligible ? '保留' : '排除' }}</template>
        </el-table-column>
        <el-table-column label="AI 结论" width="105">
          <template #default="{ row }">{{
            row.ai_eligible === null ? '未知' : row.ai_eligible ? '保留' : '排除'
          }}</template>
        </el-table-column>
        <el-table-column label="自动决策" width="160">
          <template #default="{ row }">{{
            row.status === 'ACCEPTED'
              ? '自动接受'
              : row.status === 'REJECTED'
                ? '自动排除'
                : row.status === 'UNCERTAIN'
                  ? '无法判断，已自动跳过'
                  : row.status === 'ERROR'
                    ? '技术错误，自动重试后跳过'
                    : row.status === 'SUCCEEDED'
                      ? '历史：已通过'
                      : row.status === 'REVIEW_REQUIRED'
                        ? '历史：无法判断'
                        : row.status === 'FAILED'
                          ? '历史：失败'
                          : '等待执行'
          }}</template>
        </el-table-column>
        <el-table-column label="置信度" width="100">
          <template #default="{ row }">{{
            row.confidence === null ? '—' : (row.confidence * 100).toFixed(0) + '%'
          }}</template>
        </el-table-column>
        <el-table-column prop="reason" label="AI 判断理由" min-width="220" show-overflow-tooltip />
        <el-table-column prop="evidence" label="引用证据" min-width="180" show-overflow-tooltip />
        <el-table-column
          prop="error_code"
          label="失败原因代码"
          min-width="160"
          show-overflow-tooltip
        />
        <el-table-column prop="attempt_count" label="尝试次数" width="95" />
      </el-table>
      <el-pagination
        v-model:current-page="aiResultPage"
        :page-size="10"
        :total="aiResultTotal"
        layout="prev, pager, next, total"
        @current-change="loadAIReviews"
      />
    </section>

    <section v-if="auth.isAdmin" class="panel governance-actions">
      <h3>手动数据治理</h3>
      <p>
        填写的是本批最大处理条数，不是必须处理的数量。系统自动跳过已治理或正在处理的记录；点击「开始治理」后在后台运行并自动刷新进度。
      </p>
      <div class="filters">
        <el-button
          :disabled="!selectedProduct"
          :loading="governanceBusy"
          @click="runGovernance(true)"
          >预览治理</el-button
        >
        <el-popconfirm
          title="确认将下一批未治理数据提交后台处理？原始记录不会修改。"
          @confirm="startBackgroundGovernance"
        >
          <template #reference>
            <el-button
              type="primary"
              :disabled="!selectedProduct || governanceBusy"
              :loading="governanceBusy"
              >开始治理</el-button
            >
          </template>
        </el-popconfirm>
      </div>
      <el-popconfirm
        title="一键治理当前产品全部未处理数据？任务将在后台运行，不调用 AI，也不会修改原始记录。"
        @confirm="startAllGovernance"
      >
        <template #reference>
          <el-button
            type="primary"
            plain
            :disabled="!selectedProduct || governanceBusy"
            :loading="governanceBusy"
            >一键治理全部待处理数据</el-button
          >
        </template>
      </el-popconfirm>
      <p v-if="preview">
        本次请求上限 {{ governanceLimit }} 条，实际选中
        {{ preview.total }} 条（其余已治理、正在处理或不符合筛选条件）；预计可用
        {{ preview.eligible }} 条，排除 {{ preview.excluded }} 条。预览不写入结果。
      </p>
    </section>

    <section v-if="auth.isAdmin" class="panel table-panel">
      <div class="page-header">
        <h3>后台治理任务</h3>
        <span
          v-if="
            governanceTasks.some((task) => task.status === 'RUNNING' || task.status === 'PENDING')
          "
          >每 3 秒自动刷新</span
        >
        <el-button :loading="taskLoading" @click="loadGovernanceTasks">立即刷新</el-button>
      </div>
      <el-table :data="governanceTasks" empty-text="暂无后台治理任务">
        <el-table-column prop="id" label="任务 ID" width="100" />
        <el-table-column prop="status" label="状态" width="120" />
        <el-table-column label="进度" min-width="200">
          <template #default="{ row }: { row: GovernanceTaskInfo }">
            <el-progress
              :percentage="row.total ? Math.round((row.processed / row.total) * 100) : 100"
            />
            <small>{{ row.processed }} / {{ row.total }}</small>
          </template>
        </el-table-column>
        <el-table-column prop="eligible" label="有效" width="85" />
        <el-table-column prop="failed" label="失败" width="85" />
        <el-table-column label="操作" width="100">
          <template #default="{ row }: { row: GovernanceTaskInfo }">
            <el-button
              v-if="row.status === 'FAILED' || row.status === 'PARTIAL'"
              link
              type="primary"
              @click="retryBackgroundGovernance(row.id)"
              >重试</el-button
            >
          </template>
        </el-table-column>
      </el-table>
      <el-pagination
        v-model:current-page="governanceTaskPage"
        :page-size="10"
        :total="governanceTaskTotal"
        layout="prev, pager, next, total"
        @current-change="loadGovernanceTasks"
      />
    </section>

    <section class="panel breakdown">
      <div v-for="item in breakdown" :key="item[0]">
        <span>{{ item[0] }}</span
        ><strong>{{ item[1] }}</strong
        ><small>{{ ratio(item[1]) }}</small>
      </div>
    </section>

    <section class="panel filters">
      <el-select v-model="filters.eligible" placeholder="AI 可用" clearable>
        <el-option label="可用" value="true" />
        <el-option label="排除" value="false" />
      </el-select>
      <el-select v-model="filters.exclusion_reason" placeholder="排除原因" clearable>
        <el-option
          v-for="(label, value) in reasonLabels"
          :key="value"
          :label="label"
          :value="value"
        />
      </el-select>
      <el-select v-model="filters.record_type" placeholder="记录类型" clearable>
        <el-option label="帖子" value="THREAD" />
        <el-option label="回复" value="REPLY" />
        <el-option label="官方回复" value="OFFICIAL_REPLY" />
      </el-select>
      <el-select v-model="filters.author_role" placeholder="作者角色" clearable>
        <el-option label="用户" value="USER" />
        <el-option label="官方" value="OFFICIAL" />
        <el-option label="版主" value="MODERATOR" />
        <el-option label="达人" value="EXPERT" />
      </el-select>
      <el-input-number
        v-model="filters.quality_score_min"
        :min="0"
        :max="1"
        :step="0.1"
        placeholder="最低分"
      />
      <el-input-number
        v-model="filters.quality_score_max"
        :min="0"
        :max="1"
        :step="0.1"
        placeholder="最高分"
      />
      <el-button type="primary" @click="applyFilters">筛选</el-button>
    </section>

    <section class="panel table-panel">
      <el-table
        v-loading="loading"
        :data="rows"
        empty-text="暂无治理结果"
        @row-click="selected = $event"
      >
        <el-table-column prop="review_id" label="ID" width="80" />
        <el-table-column label="类型" width="120">
          <template #default="{ row }: { row: ReviewQuality }">{{
            recordTypeLabels[row.record_type] || '未知类型'
          }}</template>
        </el-table-column>
        <el-table-column
          prop="normalized_text"
          label="正文摘要"
          min-width="300"
          show-overflow-tooltip
        />
        <el-table-column label="角色" width="110">
          <template #default="{ row }: { row: ReviewQuality }">{{
            authorRoleLabels[row.author_role] || '未知'
          }}</template>
        </el-table-column>
        <el-table-column label="AI 可用" width="100">
          <template #default="{ row }: { row: ReviewQuality }">
            <el-tag :type="row.eligible_for_ai ? 'success' : 'info'">{{
              row.eligible_for_ai ? '是' : '否'
            }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="排除原因" width="140">
          <template #default="{ row }: { row: ReviewQuality }">{{
            reasonLabels[row.exclusion_reason]
          }}</template>
        </el-table-column>
        <el-table-column prop="quality_score" label="质量分" width="90" />
        <el-table-column label="发布时间" min-width="180">
          <template #default="{ row }: { row: ReviewQuality }">{{
            formatPublishedAt(row.published_at)
          }}</template>
        </el-table-column>
      </el-table>
      <el-pagination
        v-model:current-page="page"
        :page-size="10"
        :total="total"
        layout="prev, pager, next, total"
        @current-change="loadData"
      />
    </section>

    <el-drawer
      :model-value="Boolean(selected)"
      title="治理结果详情"
      size="min(760px, 94vw)"
      @close="selected = null"
    >
      <el-descriptions v-if="selected" :column="1" border>
        <el-descriptions-item label="原始内容">
          <pre>{{ selected.original_content }}</pre>
        </el-descriptions-item>
        <el-descriptions-item label="标准化文本">
          <pre>{{ selected.normalized_text }}</pre>
        </el-descriptions-item>
        <el-descriptions-item label="上下文">
          <pre>{{ selected.context_text }}</pre>
        </el-descriptions-item>
        <el-descriptions-item label="规则标记">
          <pre>{{ JSON.stringify(selected.flags_json, null, 2) }}</pre>
        </el-descriptions-item>
        <el-descriptions-item label="人工覆盖">{{
          selected.manual_override ? selected.manual_reason : '无'
        }}</el-descriptions-item>
      </el-descriptions>
    </el-drawer>
  </div>
</template>

<style scoped>
.notice,
.governance-actions,
.breakdown,
.filters,
.table-panel {
  margin-bottom: 18px;
}

.metric-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
  margin-bottom: 18px;
}

.metric-card,
.breakdown > div {
  padding: 18px;
  background: #12283f;
  border: 1px solid #29435c;
  border-radius: 12px;
}

.metric-card span,
.breakdown span,
.breakdown small {
  display: block;
  color: #96adc6;
}

.metric-card strong {
  color: #edf5ff;
  display: block;
  margin-top: 10px;
  font-size: 28px;
}

.breakdown {
  display: grid;
  grid-template-columns: repeat(7, minmax(0, 1fr));
  gap: 10px;
}

.breakdown > div {
  padding: 12px;
}

.breakdown strong {
  color: #32d6c6;
  display: block;
  margin: 6px 0;
  font-size: 20px;
}

.filters {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.filters .el-select {
  width: 160px;
}

.table-panel .el-pagination {
  justify-content: flex-end;
  margin-top: 16px;
}

pre {
  max-height: 300px;
  margin: 0;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
}

@media (max-width: 1000px) {
  .metric-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .breakdown {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}
</style>
