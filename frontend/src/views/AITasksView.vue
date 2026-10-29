<script setup lang="ts">
import { ElMessage } from 'element-plus'
import { onMounted, onUnmounted, reactive, ref } from 'vue'
import {
  cancelStructuredBatch,
  createStructuredBatch,
  getProducts,
  getSources,
  getStructuredBatches,
  pauseStructuredBatch,
  resumeStructuredBatch,
  retryStructuredBatch,
} from '@/api'
import type { DataSource, Product, StructuredBatch } from '@/types/api'
const loading = ref(false)
const submitting = ref(false)
let refreshTimer: ReturnType<typeof setInterval> | undefined
const error = ref('')
const batches = ref<StructuredBatch[]>([])
const products = ref<Product[]>([])
const sources = ref<DataSource[]>([])
const form = reactive({
  product_id: undefined as number | undefined,
  source_id: undefined as number | undefined,
  max_items: 20,
  dry_run: true,
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
      getStructuredBatches(),
      getProducts({ page_size: 100 }),
      getSources({ page_size: 100 }),
    ])
    batches.value = b.results
    products.value = p.results
    sources.value = s.results
  } catch {
    error.value = '任务数据加载失败'
  } finally {
    loading.value = false
  }
}
async function create() {
  if (submitting.value) return
  submitting.value = true
  try {
    await createStructuredBatch(form)
    ElMessage.success(form.dry_run ? '预估完成，未调用模型' : '任务已提交')
    await load()
  } catch {
    ElMessage.error('创建任务失败，请检查筛选条件或 AI 配置')
  } finally {
    submitting.value = false
  }
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
    <header>
      <h1>AI 任务中心</h1>
      <p>默认 dry-run；只有明确关闭 dry-run 才会调用个人 AI 配置</p>
    </header>
    <el-card shadow="never"
      ><div class="form">
        <el-select v-model="form.product_id" placeholder="选择机型"
          ><el-option v-for="p in products" :key="p.id" :label="p.name" :value="p.id" /></el-select
        ><el-select v-model="form.source_id" clearable placeholder="数据来源（可选）"
          ><el-option v-for="s in sources" :key="s.id" :label="s.name" :value="s.id" /></el-select
        ><el-input-number v-model="form.max_items" :min="1" :max="1000" /><el-switch
          v-model="form.dry_run"
          active-text="仅预估（推荐）"
        /><el-button type="primary" :loading="submitting" :disabled="submitting" @click="create">{{
          form.dry_run ? '执行预估' : '提交真实任务'
        }}</el-button>
      </div>
      <small
        >并发 {{ form.max_concurrency }} · {{ form.requests_per_minute }} 请求/分钟 · Token 上限
        {{ form.token_limit }} · 预算 ¥{{ form.cost_budget }}</small
      ></el-card
    ><el-alert v-if="error" :title="error" type="error" /><el-table
      v-loading="loading"
      :data="batches"
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
      ><el-table-column label="模式"
        ><template #default="{ row }"
          ><el-tag :type="row.dry_run ? 'info' : 'warning'">{{
            row.dry_run ? 'DRY-RUN' : '真实调用'
          }}</el-tag></template
        ></el-table-column
      ><el-table-column prop="actual_cost" label="实际成本" /><el-table-column
        label="操作"
        min-width="230"
        ><template #default="{ row }"
          ><el-button v-if="['PENDING', 'RUNNING'].includes(row.status)" text @click="pause(row.id)"
            >暂停</el-button
          ><el-button v-if="row.status === 'PAUSED'" text type="primary" @click="resume(row.id)"
            >恢复</el-button
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
    >
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
