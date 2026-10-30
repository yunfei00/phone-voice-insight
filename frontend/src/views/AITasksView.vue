<script setup lang="ts">
import { ElMessage } from 'element-plus'
import { onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import {
  cancelStructuredBatch,
  createStructuredBatch,
  getProducts,
  getSources,
  getStructuredBatches,
  getStructuredBatchFailures,
  pauseStructuredBatch,
  resumeStructuredBatch,
  retryStructuredBatch,
} from '@/api'
import type { DataSource, Product, StructuredBatch } from '@/types/api'
import type { StructuredFailure } from '@/api'
const failureDialog = ref(false)
const failureLoading = ref(false)
const failureRows = ref<StructuredFailure[]>([])
const failureBatchId = ref<number | null>(null)
const failureError = ref('')
const loading = ref(false)
const submitting = ref(false)
const advancedVisible = ref(false)
const preview = ref<{
  matched_count: number
  estimated_tokens: number
  estimated_cost: string
  cost_estimate_reliable: boolean
} | null>(null)
let refreshTimer: ReturnType<typeof setInterval> | undefined
const error = ref('')
const batches = ref<StructuredBatch[]>([])
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)
const products = ref<Product[]>([])
const sources = ref<DataSource[]>([])
const form = reactive({
  product_id: undefined as number | undefined,
  source_id: undefined as number | undefined,
  max_items: 20,
  dry_run: false,
  max_concurrency: 1,
  requests_per_minute: 10,
  token_limit: 50000,
  cost_budget: 1,
})
async function load() {
  loading.value = true
  error.value = ''
  try {
    const [b, p, s] = await Promise.all([
      getStructuredBatches({
        page: page.value,
        page_size: pageSize.value,
        product: form.product_id,
        source: form.source_id,
      }),
      getProducts({ page_size: 100 }),
      getSources({ page_size: 100 }),
    ])
    batches.value = b.results
    total.value = b.count
    products.value = p.results
    sources.value = s.results
  } catch {
    error.value = '任务数据加载失败'
  } finally {
    loading.value = false
  }
}
function onFilterChange() {
  page.value = 1
  void load()
}
watch(() => [form.product_id, form.source_id], onFilterChange)
function onPageSizeChange() {
  if (page.value !== 1) {
    page.value = 1
    return
  }
  void load()
}
async function create() {
  if (submitting.value) return
  submitting.value = true
  try {
    const result = await createStructuredBatch({ ...form })
    if (form.dry_run) {
      preview.value = result.preview || null
      ElMessage.success('预估完成，未调用模型、未创建任务')
    } else {
      preview.value = null
      ElMessage.success('任务已提交')
      page.value = 1
      await load()
    }
  } catch {
    ElMessage.error('创建任务失败，请检查筛选条件或 AI 配置')
  } finally {
    submitting.value = false
  }
}
function createPreview() {
  form.dry_run = true
  void create()
}
function createAnalysis() {
  form.dry_run = false
  void create()
}
async function cancel(id: number) {
  await cancelStructuredBatch(id)
  ElMessage.success('已停止启动后续项目')
  await load()
}
async function pause(id: number) {
  await pauseStructuredBatch(id)
  ElMessage.success('任务已暂停，不再启动新项目')
  await load()
}
async function resume(id: number) {
  await resumeStructuredBatch(id)
  ElMessage.success('任务已恢复')
  await load()
}
async function showFailures(id: number) {
  failureBatchId.value = id
  failureDialog.value = true
  failureLoading.value = true
  failureError.value = ''
  failureRows.value = []
  try {
    const result = await getStructuredBatchFailures(id)
    failureRows.value = result.results
    if (result.next) failureError.value = '失败记录超过 100 条，当前仅展示前 100 条。'
  } catch {
    failureError.value = '失败明细加载失败，请稍后重试。'
  } finally {
    failureLoading.value = false
  }
}
async function retry(id: number) {
  try {
    await retryStructuredBatch(id)
    ElMessage.success('失败项目已创建重试任务')
    await load()
  } catch {
    ElMessage.warning('该任务没有可重试的失败项目')
  }
}
onMounted(() => {
  void load()
  refreshTimer = setInterval(() => {
    if (!loading.value) void load()
  }, 5000)
})
onUnmounted(() => {
  if (refreshTimer) clearInterval(refreshTimer)
})
</script>
<template>
  <section class="tasks">
    <header class="page-header">
      <div>
        <h1 class="page-title">AI 任务中心</h1>
        <p>创建分析任务、查看处理进度和失败明细。</p>
      </div>
    </header>
    <el-card shadow="never"
      ><div class="form">
        <el-select v-model="form.product_id" placeholder="选择机型"
          ><el-option v-for="p in products" :key="p.id" :label="p.name" :value="p.id" /></el-select
        ><el-select v-model="form.source_id" clearable placeholder="数据来源（可选）"
          ><el-option v-for="s in sources" :key="s.id" :label="s.name" :value="s.id" /></el-select
        ><el-input-number v-model="form.max_items" :min="1" :max="1000" aria-label="分析数量" />
        <el-button
          :loading="submitting"
          @click="createPreview"
          >预估任务</el-button
        >
        <el-button
          type="primary"
          :loading="submitting"
          :disabled="submitting"
          @click="createAnalysis"
          >开始分析</el-button
        >
      </div>
      <el-button link @click="advancedVisible = !advancedVisible">{{
        advancedVisible ? '收起高级设置' : '展开高级设置'
      }}</el-button>
      <div v-if="advancedVisible" class="advanced-settings">
        <label>最大并发 <el-input-number v-model="form.max_concurrency" :min="1" :max="8" /></label>
        <label
          >每分钟请求上限 <el-input-number v-model="form.requests_per_minute" :min="1" :max="120"
        /></label>
        <label
          >Token 上限 <el-input-number v-model="form.token_limit" :min="1" :step="10000"
        /></label>
        <label
          >预算上限（元）
          <el-input-number v-model="form.cost_budget" :min="0" :precision="2" :step="1"
        /></label>
        <p>预算依赖模型单价配置和后端累计计算，不能保证实际账单严格不超过该值。</p>
      </div>
    </el-card>
    <el-alert
      v-if="preview"
      type="info"
      :closable="true"
      @close="preview = null"
      :title="`预估结果：${preview.matched_count} 条，约 ${preview.estimated_tokens} Token；${preview.cost_estimate_reliable ? '估算费用 ¥' + preview.estimated_cost : '费用未配置，无法可靠预估'}。未调用模型、未创建任务。`"
    />
    <el-alert v-if="error" :title="error" type="error" /><el-table
      v-loading="loading"
      :data="batches.filter((batch) => !batch.dry_run)"
      empty-text="暂无 V1 任务"
      ><el-table-column prop="id" label="任务" width="80" /><el-table-column
        prop="product_name"
        label="机型"
      /><el-table-column prop="status" label="状态" /><el-table-column label="进度"
        ><template #default="{ row }"
          >{{ row.success_count + row.failed_count + row.skipped_count }}/{{
            row.requested_count
          }}</template
        ></el-table-column
      ><el-table-column prop="success_count" label="成功" width="80" /><el-table-column
        prop="failed_count"
        label="失败"
        width="80"
      /><el-table-column label="实际成本" width="120">
        <template #default="{ row }">{{
          Number(row.actual_cost) > 0 ? '¥' + Number(row.actual_cost).toFixed(4) : '—'
        }}</template> </el-table-column
      ><el-table-column label="操作" min-width="230"
        ><template #default="{ row }"
          ><el-button v-if="['PENDING', 'RUNNING'].includes(row.status)" text @click="pause(row.id)"
            >暂停</el-button
          ><el-button v-if="row.status === 'PAUSED'" text type="primary" @click="resume(row.id)"
            >恢复</el-button
          ><el-button v-if="row.failed_count" text type="primary" @click="showFailures(row.id)"
            >失败详情</el-button
          ><el-button v-if="row.failed_count" text type="warning" @click="retry(row.id)"
            >重试失败</el-button
          ><el-button
            v-if="['PENDING', 'RUNNING', 'PAUSED'].includes(row.status)"
            text
            type="danger"
            @click="cancel(row.id)"
            >取消</el-button
          ></template
        ></el-table-column
      ></el-table
    ><el-pagination
      v-model:current-page="page"
      v-model:page-size="pageSize"
      :page-sizes="[10, 20, 50, 100]"
      :total="total"
      layout="total, sizes, prev, pager, next, jumper"
      background
      @current-change="load"
      @size-change="onPageSizeChange"
    />
    <el-dialog
      v-model="failureDialog"
      :title="`批次 #${failureBatchId} · 失败帖子`"
      width="min(900px, 95%)"
    >
      <el-alert v-if="failureError" :title="failureError" type="warning" :closable="false" />
      <el-table
        v-loading="failureLoading"
        :data="failureRows"
        max-height="450"
        empty-text="暂无失败记录"
      >
        <el-table-column prop="content" label="帖子 ID" width="100" />
        <el-table-column
          prop="content_excerpt"
          label="帖子内容"
          min-width="200"
          show-overflow-tooltip
        />
        <el-table-column prop="error_code" label="错误代码" width="150" />
        <el-table-column
          prop="error_message"
          label="失败原因"
          min-width="260"
          show-overflow-tooltip
        />
        <el-table-column prop="attempt_count" label="尝试次数" width="90" />
      </el-table>
    </el-dialog>
  </section>
</template>
<style scoped>
.tasks {
  display: grid;
  gap: 18px;
}
.tasks h1 {
  margin: 0;
}
.tasks p,
small {
  color: #6b7280;
}
.advanced-settings {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  margin-top: 12px;
}
.advanced-settings label {
  display: flex;
  align-items: center;
  gap: 8px;
}
.advanced-settings p {
  width: 100%;
  font-size: 12px;
}
.form {
  display: grid;
  grid-template-columns: 1fr 1fr auto auto auto;
  gap: 12px;
  align-items: center;
  margin-bottom: 12px;
}
@media (max-width: 900px) {
  .form {
    grid-template-columns: 1fr;
  }
}
</style>
