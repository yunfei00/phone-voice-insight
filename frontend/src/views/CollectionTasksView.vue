<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'

import {
  createCollectionTask,
  getCollectionTask,
  getCollectionTasks,
  getProducts,
  getSources,
  runCollectionTask,
} from '@/api'
import type {
  CollectionStatus,
  CollectionTask,
  DataSource,
  Product,
  SourceTarget,
} from '@/types/api'

const tasks = ref<CollectionTask[]>([])
const products = ref<Product[]>([])
const sources = ref<DataSource[]>([])
const loading = ref(false)
const dialogVisible = ref(false)
const submitting = ref(false)
const runningTaskIds = ref(new Set<number>())
const selected = ref<CollectionTask | null>(null)
const error = ref('')
let pollTimer: ReturnType<typeof setInterval> | undefined
let pollAttempts = 0
const form = reactive({
  product: undefined as number | undefined,
  source: undefined as number | undefined,
  source_target: undefined as number | undefined,
  task_type: 'INCREMENTAL' as 'FULL' | 'INCREMENTAL',
  requested_limit: 10,
})

const targets = computed<SourceTarget[]>(() => {
  const source = sources.value.find((item) => item.id === form.source)
  return (source?.targets || []).filter(
    (target) => target.is_active && (!form.product || target.product === form.product),
  )
})

const selectedSourceCode = computed(
  () => sources.value.find((item) => item.id === form.source)?.code || '',
)
const requestedLimitMax = computed(() => (selectedSourceCode.value === 'JD' ? 30 : 20))

const statusType: Record<CollectionStatus, 'info' | 'primary' | 'warning' | 'success' | 'danger'> =
  {
    PENDING: 'info',
    RUNNING: 'primary',
    PAUSED: 'warning',
    SUCCESS: 'success',
    FAILED: 'danger',
    CANCELLED: 'info',
  }

async function loadData(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    const [taskPage, productPage, sourcePage] = await Promise.all([
      getCollectionTasks({ page_size: 100 }),
      getProducts({ page_size: 100 }),
      getSources({ page_size: 100 }),
    ])
    tasks.value = taskPage.results
    products.value = productPage.results
    sources.value = sourcePage.results
  } catch {
    error.value = '采集任务数据加载失败。'
  } finally {
    loading.value = false
  }
}

function stopPolling(): void {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = undefined
  }
  pollAttempts = 0
}

async function pollActiveTasks(): Promise<void> {
  const activeTasks = tasks.value.filter((task) => ['PENDING', 'RUNNING'].includes(task.status))
  if (!activeTasks.length || pollAttempts >= 150) {
    stopPolling()
    return
  }
  pollAttempts += 1
  const refreshed = await Promise.all(activeTasks.map((task) => getCollectionTask(task.id)))
  const byId = new Map(refreshed.map((task) => [task.id, task]))
  tasks.value = tasks.value.map((task) => byId.get(task.id) || task)
  if (selected.value && byId.has(selected.value.id)) {
    selected.value = byId.get(selected.value.id) || null
  }
  if (!tasks.value.some((task) => ['PENDING', 'RUNNING'].includes(task.status))) {
    stopPolling()
  }
}

function startPolling(): void {
  if (pollTimer) return
  pollAttempts = 0
  pollTimer = setInterval(() => void pollActiveTasks(), 4000)
}

async function executeTask(task: CollectionTask): Promise<void> {
  runningTaskIds.value.add(task.id)
  error.value = ''
  try {
    await runCollectionTask(task.id)
    task.status = 'PENDING'
    startPolling()
  } catch {
    error.value = `任务 #${task.id} 启动失败，请检查任务状态和 Celery。`
  } finally {
    runningTaskIds.value.delete(task.id)
  }
}

async function refreshTasks(): Promise<void> {
  await loadData()
  if (tasks.value.some((task) => ['PENDING', 'RUNNING'].includes(task.status))) startPolling()
}

function canRun(task: CollectionTask): boolean {
  return !['RUNNING', 'PAUSED', 'CANCELLED'].includes(task.status)
}

function handleSourceChange(): void {
  form.source_target = undefined
  if (form.requested_limit > requestedLimitMax.value) {
    form.requested_limit = requestedLimitMax.value
  }
}

async function submitTask(): Promise<void> {
  if (!form.product || !form.source || !form.source_target) {
    error.value = '请选择产品、数据来源和采集目标。'
    return
  }
  submitting.value = true
  try {
    await createCollectionTask({
      source_target: form.source_target,
      task_type: form.task_type,
      requested_limit: form.requested_limit,
    })
    dialogVisible.value = false
    await refreshTasks()
  } catch {
    error.value = '任务创建失败，请检查采集入口配置。'
  } finally {
    submitting.value = false
  }
}

onMounted(refreshTasks)
onUnmounted(stopPolling)
</script>

<template>
  <div>
    <div class="page-header">
      <div>
        <h1 class="page-title">采集任务</h1>
        <p class="page-description">创建任务、执行受限采集并查看分页 checkpoint。</p>
      </div>
      <div class="header-actions">
        <el-button :loading="loading" @click="refreshTasks">刷新</el-button>
        <el-button type="primary" @click="dialogVisible = true">创建任务</el-button>
      </div>
    </div>
    <el-alert
      title="荣耀俱乐部已通过 20 帖门禁；京东框架已就绪，但当前目标因登录墙与接口未验证保持停用。"
      type="info"
      show-icon
      :closable="false"
      class="notice"
    />
    <el-alert v-if="error" :title="error" type="error" :closable="false" class="notice" />
    <div class="panel">
      <el-table v-loading="loading" :data="tasks" empty-text="暂无采集任务">
        <el-table-column prop="id" label="ID" width="75" />
        <el-table-column prop="product_name" label="产品" min-width="150" />
        <el-table-column prop="source_name" label="来源" width="130" />
        <el-table-column prop="target_name" label="目标" min-width="150" />
        <el-table-column prop="task_type" label="类型" width="110" />
        <el-table-column label="状态" width="110">
          <template #default="{ row }: { row: CollectionTask }">
            <el-tag :type="statusType[row.status]">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="success_count" label="成功" width="80" />
        <el-table-column prop="skipped_count" label="跳过" width="80" />
        <el-table-column prop="failure_count" label="失败" width="80" />
        <el-table-column prop="started_at" label="开始时间" min-width="170" />
        <el-table-column prop="finished_at" label="结束时间" min-width="170" />
        <el-table-column
          prop="error_message"
          label="错误信息"
          min-width="190"
          show-overflow-tooltip
        />
        <el-table-column label="操作" width="165" fixed="right">
          <template #default="{ row }: { row: CollectionTask }">
            <el-button link type="primary" @click="selected = row">详情</el-button>
            <el-button
              link
              type="success"
              :disabled="!canRun(row)"
              :loading="runningTaskIds.has(row.id)"
              @click="executeTask(row)"
              >执行</el-button
            >
          </template>
        </el-table-column>
      </el-table>
    </div>

    <el-dialog v-model="dialogVisible" title="创建采集任务" width="min(520px, 92vw)">
      <el-form label-position="top">
        <el-form-item label="手机产品" required>
          <el-select
            v-model="form.product"
            placeholder="选择产品"
            class="full-width"
            @change="form.source_target = undefined"
          >
            <el-option
              v-for="product in products"
              :key="product.id"
              :label="product.name"
              :value="product.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="数据来源" required>
          <el-select
            v-model="form.source"
            placeholder="选择来源"
            class="full-width"
            @change="handleSourceChange"
          >
            <el-option
              v-for="source in sources"
              :key="source.id"
              :label="source.name"
              :value="source.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="采集目标" required>
          <el-select
            v-model="form.source_target"
            placeholder="选择已在 Admin 配置的入口"
            class="full-width"
          >
            <el-option
              v-for="target in targets"
              :key="target.id"
              :label="target.name"
              :value="target.id"
            />
          </el-select>
          <small v-if="form.source && form.product && !targets.length" class="hint"
            >没有可用入口，请先在 Django Admin 中录入真实且合规的目标。</small
          >
        </el-form-item>
        <el-form-item label="任务类型">
          <el-radio-group v-model="form.task_type">
            <el-radio value="INCREMENTAL">增量</el-radio>
            <el-radio value="FULL">全量</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="最多采集条数">
          <el-input-number v-model="form.requested_limit" :min="1" :max="requestedLimitMax" />
          <small class="hint">荣耀最多 20 个帖子；京东 PoC 强制最多 30 条主评价。</small>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submitTask">创建</el-button>
      </template>
    </el-dialog>

    <el-drawer
      :model-value="Boolean(selected)"
      title="采集任务详情"
      size="min(640px, 94vw)"
      @close="selected = null"
    >
      <el-descriptions v-if="selected" :column="1" border>
        <el-descriptions-item label="任务">#{{ selected.id }}</el-descriptions-item>
        <el-descriptions-item label="状态">{{ selected.status }}</el-descriptions-item>
        <el-descriptions-item label="来源 / 产品">
          {{ selected.source_name }} / {{ selected.product_name }}
        </el-descriptions-item>
        <el-descriptions-item label="目标">{{ selected.target_name }}</el-descriptions-item>
        <el-descriptions-item label="统计">
          成功 {{ selected.success_count }} / 跳过 {{ selected.skipped_count }} / 失败
          {{ selected.failure_count }}
        </el-descriptions-item>
        <el-descriptions-item label="开始时间">{{
          selected.started_at || '—'
        }}</el-descriptions-item>
        <el-descriptions-item label="结束时间">{{
          selected.finished_at || '—'
        }}</el-descriptions-item>
        <el-descriptions-item label="Checkpoint">
          <pre>{{ JSON.stringify(selected.last_checkpoint, null, 2) }}</pre>
        </el-descriptions-item>
        <el-descriptions-item label="错误信息">{{
          selected.error_message || '—'
        }}</el-descriptions-item>
      </el-descriptions>
    </el-drawer>
  </div>
</template>

<style scoped>
.notice {
  margin-bottom: 16px;
}

.full-width {
  width: 100%;
}

.hint {
  display: block;
  margin-top: 8px;
  color: #b45309;
}

.header-actions {
  display: flex;
  gap: 10px;
}

pre {
  margin: 0;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}
</style>
