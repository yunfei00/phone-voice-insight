<script setup lang="ts">
import { ElMessage } from 'element-plus'
import { onMounted, onUnmounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'

import {
  createStructuredBatch,
  retryRemainingStructuredAnalysis,
  getStructuredCorpusProgress,
  getProducts,
  getStructuredAggregates,
  getStructuredAnalyses,
  getStructuredBatches,
  getStructuredQuality,
  getTaxonomy,
} from '@/api'
import HighlightText from '@/components/HighlightText.vue'
import type { StructuredCorpusProgress } from '@/api'
import type {
  Product,
  StructuredAggregates,
  StructuredAnalysisV1,
  StructuredBatch,
  StructuredQuality,
  TaxonomyDefinition,
} from '@/types/api'

const router = useRouter()
const starting = ref(false)
const startingAll = ref(false)
const corpusProgress = ref<StructuredCorpusProgress>()
let progressTimer: ReturnType<typeof setInterval> | undefined
let aggregateTimer: ReturnType<typeof setInterval> | undefined
let requestGeneration = 0
let disposed = false
let progressRequestPending = false
let aggregateRequestPending = false
let lastProgressActive = false
let resultsController: AbortController | undefined
let qualityController: AbortController | undefined
let aggregateController: AbortController | undefined
let batchesController: AbortController | undefined
let taxonomyController: AbortController | undefined
let progressController: AbortController | undefined
const sampleSize = ref(20)
const loading = ref(false)
const error = ref('')
const qualityLoading = ref(false)
const qualityError = ref('')
const aggregatesLoading = ref(false)
const aggregatesError = ref('')
const batchesLoading = ref(false)
const batchesError = ref('')
const taxonomyError = ref('')
const progressLoading = ref(false)
const progressError = ref('')
const items = ref<StructuredAnalysisV1[]>([])
const count = ref(0)
const taxonomy = ref<TaxonomyDefinition>()
const products = ref<Product[]>([])
const selectedProduct = ref<number>()
const quality = ref<StructuredQuality>()
const aggregates = ref<StructuredAggregates>()
const batches = ref<StructuredBatch[]>([])
const batchCount = ref(0)
const page = ref(1)
const batchPage = ref(1)
const filters = reactive({ search: '', aspect_code: '', sentiment: '' })

const batchStatusLabels: Record<StructuredBatch['status'], string> = {
  PENDING: '排队中',
  RUNNING: '执行中',
  SUCCESS: '已成功',
  PARTIAL: '部分成功',
  FAILED: '已失败',
  CANCELLED: '已取消',
  PAUSED: '已暂停',
  BUDGET_EXCEEDED: '预算已停止',
}

function batchStatusLabel(status: StructuredBatch['status']): string {
  return batchStatusLabels[status]
}

function batchStatusType(
  status: StructuredBatch['status'],
): 'success' | 'warning' | 'danger' | 'info' {
  if (status === 'SUCCESS') return 'success'
  if (status === 'FAILED' || status === 'BUDGET_EXCEEDED') return 'danger'
  if (status === 'RUNNING' || status === 'PENDING' || status === 'PARTIAL') return 'warning'
  return 'info'
}

function isCancelled(reason: unknown): boolean {
  const candidate = reason as { code?: string; name?: string }
  return candidate?.code === 'ERR_CANCELED' || candidate?.name === 'AbortError'
}

function shouldRetry(reason: unknown): boolean {
  const status = (reason as { response?: { status?: number } })?.response?.status
  return status === undefined || status === 408 || status === 429 || status >= 500
}

function waitForRetry(delay: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const onAbort = () => {
      clearTimeout(timer)
      const error = new Error('请求已取消')
      error.name = 'AbortError'
      reject(error)
    }
    const timer = setTimeout(() => {
      signal.removeEventListener('abort', onAbort)
      resolve()
    }, delay)
    signal.addEventListener('abort', onAbort, { once: true })
  })
}

async function withBoundedRetry<T>(task: () => Promise<T>, signal: AbortSignal): Promise<T> {
  const retryDelays = [100, 300]
  let lastError: unknown
  for (let attempt = 0; attempt <= retryDelays.length; attempt += 1) {
    try {
      return await task()
    } catch (reason: unknown) {
      if (isCancelled(reason) || signal.aborted) throw reason
      lastError = reason
      if (!shouldRetry(reason) || attempt === retryDelays.length) break
      await waitForRetry(retryDelays[attempt], signal)
    }
  }
  throw lastError
}

function isCurrent(generation: number, productId: number | undefined): boolean {
  return !disposed && generation === requestGeneration && selectedProduct.value === productId
}

function abortRequests(): void {
  resultsController?.abort()
  qualityController?.abort()
  aggregateController?.abort()
  batchesController?.abort()
  taxonomyController?.abort()
  progressController?.abort()
}

async function loadResults(generation = requestGeneration): Promise<void> {
  const productId = selectedProduct.value
  resultsController?.abort()
  const controller = new AbortController()
  resultsController = controller
  loading.value = true
  error.value = ''
  try {
    const response = await withBoundedRetry(
      () =>
        getStructuredAnalyses(
          { ...filters, product: productId, page: page.value, page_size: 10 },
          { signal: controller.signal, suppressGlobalError: true },
        ),
      controller.signal,
    )
    if (!isCurrent(generation, productId)) return
    items.value = response.results
    count.value = response.count
  } catch (reason: unknown) {
    if (!isCancelled(reason) && isCurrent(generation, productId)) {
      error.value = '分析结果加载失败，请稍后重试。'
    }
  } finally {
    if (isCurrent(generation, productId) && resultsController === controller) loading.value = false
  }
}

async function loadQuality(generation = requestGeneration): Promise<void> {
  const productId = selectedProduct.value
  qualityController?.abort()
  const controller = new AbortController()
  qualityController = controller
  qualityLoading.value = true
  qualityError.value = ''
  try {
    const result = await withBoundedRetry(
      () =>
        getStructuredQuality(
          { product: productId },
          { signal: controller.signal, suppressGlobalError: true },
        ),
      controller.signal,
    )
    if (isCurrent(generation, productId)) quality.value = result
  } catch (reason: unknown) {
    if (!isCancelled(reason) && isCurrent(generation, productId)) {
      qualityError.value = '质量统计加载失败，已保留上次成功数据。'
    }
  } finally {
    if (isCurrent(generation, productId) && qualityController === controller)
      qualityLoading.value = false
  }
}

async function loadAggregates(generation = requestGeneration): Promise<void> {
  const productId = selectedProduct.value
  aggregateController?.abort()
  const controller = new AbortController()
  aggregateController = controller
  aggregatesLoading.value = true
  aggregatesError.value = ''
  try {
    const result = await withBoundedRetry(
      () =>
        getStructuredAggregates(
          { product: productId },
          { signal: controller.signal, suppressGlobalError: true },
        ),
      controller.signal,
    )
    if (isCurrent(generation, productId)) aggregates.value = result
  } catch (reason: unknown) {
    if (!isCancelled(reason) && isCurrent(generation, productId)) {
      aggregatesError.value = '聚合统计加载失败，任务进度仍会继续更新。'
    }
  } finally {
    if (isCurrent(generation, productId) && aggregateController === controller) {
      aggregatesLoading.value = false
    }
  }
}

async function loadBatches(generation = requestGeneration): Promise<void> {
  const productId = selectedProduct.value
  batchesController?.abort()
  const controller = new AbortController()
  batchesController = controller
  batchesLoading.value = true
  batchesError.value = ''
  try {
    const result = await withBoundedRetry(
      () =>
        getStructuredBatches(
          { product: productId, page: batchPage.value, page_size: 10 },
          { signal: controller.signal, suppressGlobalError: true },
        ),
      controller.signal,
    )
    if (!isCurrent(generation, productId)) return
    batches.value = result.results
    batchCount.value = result.count
  } catch (reason: unknown) {
    if (!isCancelled(reason) && isCurrent(generation, productId)) {
      batchesError.value = '任务列表加载失败，其他模块不受影响。'
    }
  } finally {
    if (isCurrent(generation, productId) && batchesController === controller)
      batchesLoading.value = false
  }
}

async function loadTaxonomy(generation = requestGeneration): Promise<void> {
  if (taxonomy.value) return
  const productId = selectedProduct.value
  taxonomyController?.abort()
  const controller = new AbortController()
  taxonomyController = controller
  taxonomyError.value = ''
  try {
    const result = await withBoundedRetry(
      () => getTaxonomy({ signal: controller.signal, suppressGlobalError: true }),
      controller.signal,
    )
    if (isCurrent(generation, productId)) taxonomy.value = result
  } catch (reason: unknown) {
    if (!isCancelled(reason) && isCurrent(generation, productId)) {
      taxonomyError.value = '分类体系暂时不可用，不影响结果和任务进度。'
    }
  }
}

async function loadProgress(
  generation = requestGeneration,
  detectCompletion = false,
): Promise<void> {
  const productId = selectedProduct.value
  if (!productId) {
    corpusProgress.value = undefined
    progressError.value = ''
    return
  }
  progressController?.abort()
  const controller = new AbortController()
  progressController = controller
  progressLoading.value = true
  progressError.value = ''
  try {
    const result = await withBoundedRetry(
      () =>
        getStructuredCorpusProgress(productId, {
          signal: controller.signal,
          suppressGlobalError: true,
        }),
      controller.signal,
    )
    if (!isCurrent(generation, productId)) return
    const justCompleted = detectCompletion && lastProgressActive && !result.active
    corpusProgress.value = result
    lastProgressActive = result.active
    if (justCompleted) {
      await Promise.allSettled([
        loadResults(generation),
        loadQuality(generation),
        loadAggregates(generation),
        loadBatches(generation),
      ])
    }
  } catch (reason: unknown) {
    if (!isCancelled(reason) && isCurrent(generation, productId)) {
      progressError.value = '任务进度更新失败，将在下个周期自动重试。'
    }
  } finally {
    if (isCurrent(generation, productId) && progressController === controller)
      progressLoading.value = false
  }
}

async function load(): Promise<void> {
  requestGeneration += 1
  abortRequests()
  const generation = requestGeneration
  await Promise.allSettled([
    loadResults(generation),
    loadQuality(generation),
    loadAggregates(generation),
    loadBatches(generation),
    loadTaxonomy(generation),
    loadProgress(generation),
  ])
}

async function pollProgress(): Promise<void> {
  if (progressRequestPending || disposed || document.hidden || !selectedProduct.value) return
  progressRequestPending = true
  try {
    await loadProgress(requestGeneration, true)
  } finally {
    progressRequestPending = false
  }
}

async function refreshAggregatesOnSchedule(): Promise<void> {
  if (aggregateRequestPending || disposed || document.hidden) return
  aggregateRequestPending = true
  try {
    await loadAggregates(requestGeneration)
  } finally {
    aggregateRequestPending = false
  }
}

async function startAll() {
  if (!selectedProduct.value || startingAll.value || corpusProgress.value?.active) return
  startingAll.value = true
  try {
    const result = await retryRemainingStructuredAnalysis(selectedProduct.value)
    ElMessage.success(
      result.queued
        ? `已提交 ${result.queued} 条剩余语料（包含历史失败项）`
        : '没有待分析的有效评论',
    )
    await load()
  } catch (reason: unknown) {
    const detail = reason as { response?: { data?: { error_code?: string; batch_id?: number } } }
    const code = detail.response?.data?.error_code
    ElMessage.error(
      code === 'ANALYSIS_ALREADY_RUNNING'
        ? `批次 #${detail.response?.data?.batch_id} 正在执行`
        : code === 'AI_NOT_CONFIGURED'
          ? '请先配置 AI 模型'
          : '任务未成功启动，请检查 Worker',
    )
  } finally {
    startingAll.value = false
  }
}

async function startSample() {
  if (!selectedProduct.value || starting.value || startingAll.value || corpusProgress.value?.active)
    return
  starting.value = true
  try {
    const result = await createStructuredBatch({
      product_id: selectedProduct.value,
      max_items: sampleSize.value,
      dry_run: false,
      max_concurrency: 1,
      requests_per_minute: 10,
    })
    ElMessage.success(
      `已提交真实分析任务 #${result.batch.id}，匹配 ${result.matched_content_ids.length} 条语料`,
    )
    await load()
  } catch (reason: unknown) {
    const detail = reason as { response?: { data?: { error_code?: string; detail?: string } } }
    const code = detail.response?.data?.error_code
    ElMessage.error(
      code === 'NO_CONTENT_MATCHED'
        ? '没有可分析的最终有效语料，请先在数据质量页面完成 AI 治理'
        : detail.response?.data?.detail || '任务创建失败，请检查 AI 配置和后台任务服务',
    )
  } finally {
    starting.value = false
  }
}

async function changeProduct() {
  page.value = 1
  batchPage.value = 1
  lastProgressActive = false
  await load()
}

async function applyResultFilters(): Promise<void> {
  page.value = 1
  await loadResults()
}

function startRefreshTimers(): void {
  progressTimer ||= setInterval(() => void pollProgress(), 5000)
  aggregateTimer ||= setInterval(() => void refreshAggregatesOnSchedule(), 60_000)
}

function stopRefreshTimers(): void {
  if (progressTimer) clearInterval(progressTimer)
  if (aggregateTimer) clearInterval(aggregateTimer)
  progressTimer = undefined
  aggregateTimer = undefined
}

defineExpose({ changeProduct, selectedProduct })

onMounted(async () => {
  try {
    products.value = (await getProducts({ page_size: 100 })).results
    selectedProduct.value = products.value[0]?.id
  } catch {
    ElMessage.warning('产品列表加载失败')
  }
  await load()
  startRefreshTimers()
})
onUnmounted(() => {
  disposed = true
  stopRefreshTimers()
  abortRequests()
})
</script>

<template>
  <section class="page-stack">
    <header class="page-header">
      <div>
        <h1>AI 结构化分析</h1>
        <p>自动治理后的有效反馈将无人值守进入结构化分析；证据不足和技术错误不会混入问题统计。</p>
      </div>
    </header>
    <el-card shadow="never">
      <div class="filters">
        <strong>下一步：启动真实 AI 结构化分析</strong>
        <el-select v-model="selectedProduct" placeholder="先选择手机产品" @change="changeProduct">
          <el-option
            v-for="product in products"
            :key="product.id"
            :label="product.name"
            :value="product.id"
          />
        </el-select>
        <el-input-number v-model="sampleSize" :min="1" :max="1000" :step="10" />
        <el-button
          type="primary"
          :loading="starting"
          :disabled="!selectedProduct || startingAll || starting || corpusProgress?.active"
          @click="startSample"
        >
          开始分析（非模拟）
        </el-button>
        <el-button
          type="success"
          :loading="startingAll"
          :disabled="!selectedProduct || startingAll || starting || corpusProgress?.active"
          @click="startAll"
          >一键补齐全部剩余（含历史失败）</el-button
        >
        <el-button @click="load">刷新结果与任务进度</el-button>
      </div>
      <p>
        已完成的评论自动跳过；全量任务按每批 100 条持续执行。系统每 30
        分钟检查新增有效评论并自动分析，失败记录不会无限重试。
      </p>
    </el-card>
    <el-alert
      v-if="progressError"
      :title="progressError"
      type="warning"
      show-icon
      :closable="false"
    >
      <el-button text @click="loadProgress()">立即重试</el-button>
    </el-alert>
    <el-card v-if="corpusProgress" v-loading="progressLoading" shadow="never">
      <template #header><strong>全量分析进度（每 5 秒更新）</strong></template>
      <el-progress
        :percentage="
          corpusProgress.total
            ? Math.round((corpusProgress.completed / corpusProgress.total) * 100)
            : 100
        "
      />
      <p>
        有效语料 {{ corpusProgress.total }} · 已完成 {{ corpusProgress.completed }} · 剩余
        {{ corpusProgress.remaining }}
      </p>
      <p v-if="corpusProgress.batch">
        批次 #{{ corpusProgress.batch.id }} · {{ batchStatusLabel(corpusProgress.batch.status) }} ·
        本批
        {{
          corpusProgress.batch.success_count +
          corpusProgress.batch.failed_count +
          corpusProgress.batch.skipped_count
        }}/{{ corpusProgress.batch.requested_count }}
      </p>
      <p v-if="corpusProgress.batch">
        <el-tag type="success" effect="plain">成功 {{ corpusProgress.batch.success_count }}</el-tag>
        <el-tag type="danger" effect="plain">失败 {{ corpusProgress.batch.failed_count }}</el-tag>
        <el-tag type="info" effect="plain">跳过 {{ corpusProgress.batch.skipped_count }}</el-tag>
      </p>
      <el-alert v-if="corpusProgress.batch?.error_message" :title="corpusProgress.batch.error_message" type="error" :closable="false" />
      <p v-if="corpusProgress.active">任务执行中，已禁止重复提交。</p>
      <el-button v-if="corpusProgress.batch" type="primary" plain @click="router.push('/ai-tasks')"
        >查看任务中心</el-button
      >
    </el-card>
    <el-alert v-if="qualityError" :title="qualityError" type="warning" show-icon :closable="false">
      <el-button text @click="loadQuality()">重试质量统计</el-button>
    </el-alert>
    <div v-loading="qualityLoading" class="metric-grid">
      <el-card shadow="never"
        ><span>AI 已分析量</span><strong>{{ quality?.total_runs || 0 }}</strong></el-card
      >
      <el-card shadow="never"
        ><span>有效分析量</span><strong>{{ quality?.successful_runs || 0 }}</strong></el-card
      >
      <el-card shadow="never"
        ><span>明确问题/观点</span><strong>{{ aggregates?.opinion_count || 0 }}</strong></el-card
      >
      <el-card shadow="never"
        ><span>分析失败量</span
        ><strong>{{
          (quality?.total_runs || 0) - (quality?.successful_runs || 0)
        }}</strong></el-card
      >
    </div>
    <el-card shadow="never">
      <div class="filters">
        <el-select v-model="selectedProduct" placeholder="选择手机产品" @change="changeProduct">
          <el-option
            v-for="product in products"
            :key="product.id"
            :label="product.name"
            :value="product.id"
          />
        </el-select>
        <el-input
          v-model="filters.search"
          clearable
          placeholder="搜索原文、摘要或证据"
          @keyup.enter="applyResultFilters"
        />
        <el-select v-model="filters.aspect_code" clearable placeholder="一级分类">
          <el-option
            v-for="tag in taxonomy?.domains"
            :key="tag.tag_id"
            :label="`${tag.name} (${tag.tag_id})`"
            :value="tag.tag_id"
          />
        </el-select>
        <el-select v-model="filters.sentiment" clearable placeholder="情感">
          <el-option
            v-for="value in ['POSITIVE', 'NEUTRAL', 'NEGATIVE', 'MIXED', 'UNKNOWN']"
            :key="value"
            :value="value"
          />
        </el-select>
        <el-button type="primary" @click="applyResultFilters">查询</el-button>
      </div>
    </el-card>
    <el-alert
      v-if="taxonomyError"
      :title="taxonomyError"
      type="warning"
      show-icon
      :closable="false"
    >
      <el-button text @click="loadTaxonomy()">重试分类体系</el-button>
    </el-alert>
    <el-alert v-if="error" :title="error" type="error" show-icon
      ><el-button text @click="load">重试</el-button></el-alert
    >
    <div v-loading="loading" class="analysis-list">
      <el-empty
        v-if="!loading && !error && !items.length"
        description="暂无结构化分析结果；自动流水线将在治理通过且预算可用时运行"
      />
      <el-card v-for="item in items" :key="item.id" class="analysis-card" shadow="hover">
        <template #header>
          <div class="card-title">
            <strong>{{ item.original_title || `反馈 #${item.content}` }}</strong
            ><span> {{ item.product_name }} · {{ item.source_name }}</span>
          </div>
        </template>
        <p class="original">{{ item.original_content }}</p>
        <p class="summary">AI 摘要：{{ item.summary || '—' }}</p>
        <div class="opinions">
          <div v-for="aspect in item.aspects" :key="aspect.id" class="opinion">
            <div>
              <el-tag>{{ aspect.aspect_code }}</el-tag
              ><el-tag effect="plain">{{ aspect.topic_code }}</el-tag
              ><el-tag
                :type="
                  aspect.sentiment === 'NEGATIVE'
                    ? 'danger'
                    : aspect.sentiment === 'POSITIVE'
                      ? 'success'
                      : 'info'
                "
                >{{ aspect.sentiment }}</el-tag
              ><el-tag type="warning" effect="plain">{{ aspect.severity }}</el-tag>
            </div>
            <p>
              <strong>证据：</strong
              ><HighlightText :text="item.original_content" :keyword="aspect.evidence_text" />
            </p>
            <small
              >置信度 {{ Number(aspect.confidence).toFixed(2) }} · {{ aspect.intent }} ·
              {{ aspect.issue_type }}</small
            >
          </div>
          <el-empty v-if="!item.aspects.length" :image-size="48" description="无相关观点" />
        </div>
        <footer>
          <span
            >{{ item.provider }} / {{ item.model }} · {{ item.prompt_version }} · Schema
            {{ item.schema_version }}</span
          >
        </footer>
      </el-card>
    </div>
    <el-pagination
      v-model:current-page="page"
      :page-size="10"
      :total="count"
      layout="prev, pager, next, total"
      @current-change="loadResults"
    />
    <el-alert
      v-if="aggregatesError"
      :title="aggregatesError"
      type="warning"
      show-icon
      :closable="false"
    >
      <el-button text @click="loadAggregates()">重试聚合统计</el-button>
    </el-alert>
    <el-card v-loading="aggregatesLoading" shadow="never">
      <template #header><strong>高频问题与分类</strong></template>
      <div class="ranking">
        <el-tag v-for="item in aggregates?.high_frequency_clusters || []" :key="item.topic_code">
          {{ item.topic_code }} · {{ item.count }}
        </el-tag>
        <el-empty
          v-if="!aggregates?.high_frequency_clusters.length"
          :image-size="48"
          description="暂无聚合结果"
        />
      </div>
    </el-card>
    <el-card v-loading="batchesLoading" shadow="never">
      <template #header><strong>最近自动分析任务</strong></template>
      <el-alert
        v-if="batchesError"
        :title="batchesError"
        type="warning"
        show-icon
        :closable="false"
      >
        <el-button text @click="loadBatches()">重试任务列表</el-button>
      </el-alert>
      <el-table :data="batches" empty-text="暂无自动分析任务">
        <el-table-column prop="id" label="任务 ID" width="90" />
        <el-table-column prop="product_name" label="产品" />
        <el-table-column label="状态" width="120">
          <template #default="{ row }">
            <el-tag :type="batchStatusType(row.status)">{{ batchStatusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="进度"
          ><template #default="{ row }"
            >{{ row.success_count + row.failed_count + row.skipped_count }} /
            {{ row.requested_count }}</template
          ></el-table-column
        >
        <el-table-column prop="success_count" label="成功" width="85" />
        <el-table-column prop="failed_count" label="失败" width="85" />
        <el-table-column label="失败原因" min-width="170" show-overflow-tooltip>
          <template #default="{ row }">{{ row.error_message || (row.failed_count ? '在任务中心查看失败帖子' : '—') }}</template>
        </el-table-column>
        <el-table-column prop="total_tokens" label="Token" width="100" />
      </el-table>
      <el-pagination
        v-model:current-page="batchPage"
        :page-size="10"
        :total="batchCount"
        layout="prev, pager, next, total"
        @current-change="loadBatches"
      />
    </el-card>
  </section>
</template>

<style scoped>
.page-stack {
  display: grid;
  gap: 18px;
}
.page-header,
.card-title,
footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}
.page-header h1 {
  margin: 0;
}
.page-header p {
  margin: 6px 0 0;
  color: var(--pvi-muted);
}
.metric-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}
.metric-grid span,
.metric-grid strong {
  display: block;
}
.metric-grid span {
  color: var(--pvi-muted);
}
.metric-grid strong {
  margin-top: 8px;
  font-size: 28px;
}
.filters {
  display: grid;
  grid-template-columns: minmax(240px, 2fr) repeat(3, minmax(140px, 1fr)) auto;
  gap: 12px;
}
.analysis-list {
  min-height: 180px;
  display: grid;
  gap: 14px;
}
.analysis-card {
  border-radius: 12px;
}
.card-title span,
footer,
small {
  color: var(--pvi-muted);
}
.original {
  white-space: pre-wrap;
}
.summary {
  padding: 10px 12px;
  color: var(--pvi-text);
  background: var(--el-fill-color-light);
  border: 1px solid var(--pvi-border);
  border-radius: 8px;
}
.opinions {
  display: grid;
  gap: 10px;
}
.opinion {
  padding: 12px;
  color: var(--pvi-text);
  background: var(--el-fill-color-light);
  border: 1px solid var(--pvi-border);
  border-radius: 9px;
}
.opinion > div {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}
.opinion p {
  margin: 10px 0;
}
footer {
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px solid var(--pvi-border);
}
.json-editor {
  margin: 14px 0;
}
.count {
  text-align: center;
  color: var(--pvi-muted);
}
.ranking {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
@media (max-width: 900px) {
  .filters {
    grid-template-columns: 1fr;
  }
  .page-header,
  .card-title,
  footer {
    align-items: flex-start;
    flex-direction: column;
  }
  .metric-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
