<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'

import { getDataQualitySummary, getReviewQualities, getProducts, processGovernanceBatch, startAsyncGovernance, getGovernanceTaskHistory, getGovernanceTaskStatus, retryGovernanceTask, startGovernanceAIReview, getGovernanceAIHistory, getGovernanceAIResults } from '@/api'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import type { Product, DataQualitySummary, ExclusionReason, ReviewQuality } from '@/types/api'
import type { GovernanceTaskInfo, GovernanceAIBatchInfo, GovernanceAIResultInfo } from '@/api'

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
const governanceProduct = ref<number | undefined>(undefined)
const governanceLimit = ref(20)
const governanceBusy = ref(false)
const governanceTasks = ref<GovernanceTaskInfo[]>([])
const taskLoading = ref(false)
const aiBusy = ref(false)
const aiBatches = ref<GovernanceAIBatchInfo[]>([])
const aiResults = ref<GovernanceAIResultInfo[]>([])
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
  const part = (type: string) => parts.find(item => item.type === type)?.value || ''
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
    page_size: 20,
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
      getDataQualitySummary(),
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
  if (!governanceProduct.value) return
  governanceBusy.value = true
  try {
    const result = await processGovernanceBatch({
      product_id: governanceProduct.value,
      limit: governanceLimit.value,
      dry_run: dryRun,
    })
    preview.value = result
    ElMessage.success(result.total === 0 ? '该产品没有待治理的数据' : (dryRun ? '预览完成，未写入治理结果' : '批量治理完成'))
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
    const history = await getGovernanceTaskHistory()
    governanceTasks.value = await Promise.all(history.results.map(async (task) => {
      if (task.status !== 'RUNNING' && task.status !== 'PENDING') return task
      try { return await getGovernanceTaskStatus(task.id) } catch { return task }
    }))
    if (!governanceTasks.value.some(task => task.status === 'RUNNING' || task.status === 'PENDING')) stopTaskPolling()
  } catch {
    ElMessage.error('治理任务列表加载失败')
  } finally {
    taskLoading.value = false
  }
}

async function loadAIReviews(): Promise<void> {
  if (!auth.isAdmin) return
  try {
    const history = await getGovernanceAIHistory()
    aiBatches.value = history.results
    if (governanceProduct.value) {
      const results = await getGovernanceAIResults(governanceProduct.value)
      aiResults.value = results.results
    }
    if (!aiBatches.value.some(b => b.status === 'PENDING' || b.status === 'RUNNING')) stopAIPolling()
  } catch {
    ElMessage.error('AI 复核状态加载失败')
  }
}

function stopAIPolling(): void {
  if (aiPollTimer !== undefined) clearInterval(aiPollTimer)
  aiPollTimer = undefined
}

function startAIPolling(): void {
  if (aiPollTimer !== undefined) return
  aiPollTimer = setInterval(() => { void loadAIReviews() }, 3000)
}

async function startAIReview(): Promise<void> {
  if (!governanceProduct.value) return
  aiBusy.value = true
  try {
    const batch = await startGovernanceAIReview({
      product_id: governanceProduct.value, limit: governanceLimit.value,
    })
    ElMessage.success(`已提交 ${batch.total} 条 AI 复核数据`)
    await loadAIReviews()
    startAIPolling()
  } catch {
    ElMessage.error('AI 复核任务提交失败，请检查模型配置及后台服务')
  } finally {
    aiBusy.value = false
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
  if (!governanceProduct.value) return
  governanceBusy.value = true
  try {
    await startAsyncGovernance({
      product_id: governanceProduct.value,
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
  await loadData()
  if (auth.isAdmin) {
    await loadGovernanceTasks()
    if (governanceTasks.value.some(task => task.status === 'RUNNING' || task.status === 'PENDING')) startTaskPolling()
    try {
      products.value = (await getProducts({ page_size: 100 })).results
    } catch {
      ElMessage.warning('产品列表加载失败')
    }
  }
})
onUnmounted(() => { stopTaskPolling(); stopAIPolling() })
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
      <h3>AI 辅助复核（P2）</h3>
      <p>对已完成规则治理的数据进行 AI 复核；AI 不会覆盖规则结果，冲突及低置信度数据进入待人工确认。</p>
      <div class="filters">
        <el-button type="primary" :loading="aiBusy" :disabled="!governanceProduct" @click="startAIReview">开始 AI 复核</el-button>
        <el-button @click="loadAIReviews">查看复核结果</el-button>
        <span v-if="aiBatches.some(b => b.status === 'RUNNING' || b.status === 'PENDING')">每 3 秒自动更新</span>
      </div>
      <el-table :data="aiBatches" size="small" style="margin-bottom: 12px">
        <el-table-column prop="id" label="任务编号" width="95" />
        <el-table-column label="状态" width="120">
          <template #default="{ row }">{{ ({ PENDING: '等待执行', RUNNING: '正在执行', SUCCESS: '已完成', PARTIAL: '部分失败', FAILED: '失败' } as Record<string, string>)[row.status] || row.status }}</template>
        </el-table-column>
        <el-table-column label="进度">
          <template #default="{ row }">{{ row.processed }} / {{ row.total }}</template>
        </el-table-column>
        <el-table-column prop="succeeded" label="通过" />
        <el-table-column prop="review_required" label="待人工确认" />
        <el-table-column prop="failed" label="失败" />
      </el-table>
      <el-table :data="aiResults" size="small">
        <el-table-column prop="review_id" label="记录 ID" width="95" />
        <el-table-column label="规则结论" width="105">
          <template #default="{ row }">{{ row.rule_eligible ? '保留' : '排除' }}</template>
        </el-table-column>
        <el-table-column label="AI 结论" width="105">
          <template #default="{ row }">{{ row.ai_eligible === null ? '未知' : row.ai_eligible ? '保留' : '排除' }}</template>
        </el-table-column>
        <el-table-column label="复核状态" width="120">
          <template #default="{ row }">{{ row.status === 'REVIEW_REQUIRED' ? '待人工确认' : row.status === 'SUCCEEDED' ? '已复核' : row.status === 'FAILED' ? '失败' : '等待执行' }}</template>
        </el-table-column>
        <el-table-column label="置信度" width="100">
          <template #default="{ row }">{{ row.confidence === null ? '—' : (row.confidence * 100).toFixed(0) + '%' }}</template>
        </el-table-column>
        <el-table-column prop="reason" label="AI 判断理由" min-width="220" show-overflow-tooltip />
        <el-table-column prop="evidence" label="引用证据" min-width="180" show-overflow-tooltip />
      </el-table>
    </section>

    <section v-if="auth.isAdmin" class="panel governance-actions">
      <h3>手动数据治理</h3>
      <p>填写的是本批最大处理条数，不是必须处理的数量。系统自动跳过已治理或正在处理的记录；点击「开始治理」后在后台运行并自动刷新进度。</p>
      <div class="filters">
        <el-select v-model="governanceProduct" placeholder="选择手机产品" style="width: 230px">
          <el-option v-for="product in products" :key="product.id" :label="product.name" :value="product.id" />
        </el-select>
        <el-input-number v-model="governanceLimit" :min="1" :max="100" />
        <el-button :disabled="!governanceProduct" :loading="governanceBusy" @click="runGovernance(true)">预览治理</el-button>
        <el-popconfirm title="确认将下一批未治理数据提交后台处理？原始记录不会修改。" @confirm="startBackgroundGovernance">
          <template #reference>
            <el-button type="primary" :disabled="!governanceProduct || governanceBusy" :loading="governanceBusy">开始治理</el-button>
          </template>
        </el-popconfirm>
      </div>
      <p v-if="preview">本次请求上限 {{ governanceLimit }} 条，实际选中 {{ preview.total }} 条（其余已治理、正在处理或不符合筛选条件）；预计可用 {{ preview.eligible }} 条，排除 {{ preview.excluded }} 条。预览不写入结果。</p>
    </section>

    <section v-if="auth.isAdmin" class="panel table-panel">
      <div class="page-header">
        <h3>后台治理任务</h3>
        <span v-if="governanceTasks.some(task => task.status === 'RUNNING' || task.status === 'PENDING')">每 3 秒自动刷新</span>
        <el-button :loading="taskLoading" @click="loadGovernanceTasks">立即刷新</el-button>
      </div>
      <el-table :data="governanceTasks" empty-text="暂无后台治理任务">
        <el-table-column prop="id" label="任务 ID" width="100" />
        <el-table-column prop="status" label="状态" width="120" />
        <el-table-column label="进度" min-width="200">
          <template #default="{ row }: { row: GovernanceTaskInfo }">
            <el-progress :percentage="row.total ? Math.round(row.processed / row.total * 100) : 100" />
            <small>{{ row.processed }} / {{ row.total }}</small>
          </template>
        </el-table-column>
        <el-table-column prop="eligible" label="有效" width="85" />
        <el-table-column prop="failed" label="失败" width="85" />
        <el-table-column label="操作" width="100">
          <template #default="{ row }: { row: GovernanceTaskInfo }">
            <el-button v-if="row.status === 'FAILED' || row.status === 'PARTIAL'" link type="primary" @click="retryBackgroundGovernance(row.id)">重试</el-button>
          </template>
        </el-table-column>
      </el-table>
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
          <template #default="{ row }: { row: ReviewQuality }">{{ recordTypeLabels[row.record_type] || '未知类型' }}</template>
        </el-table-column>
        <el-table-column
          prop="normalized_text"
          label="正文摘要"
          min-width="300"
          show-overflow-tooltip
        />
        <el-table-column label="角色" width="110">
          <template #default="{ row }: { row: ReviewQuality }">{{ authorRoleLabels[row.author_role] || '未知' }}</template>
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
          <template #default="{ row }: { row: ReviewQuality }">{{ formatPublishedAt(row.published_at) }}</template>
        </el-table-column>
      </el-table>
      <el-pagination
        v-model:current-page="page"
        :page-size="20"
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
  background: #fff;
  border: 1px solid #e7eaf0;
  border-radius: 12px;
}

.metric-card span,
.breakdown span,
.breakdown small {
  display: block;
  color: #6b7280;
}

.metric-card strong {
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
