<script setup lang="ts">
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'

import {
  getCollectionTargets,
  getProducts,
  getSources,
  createSourceTarget,
  recoverStaleCollectionTask,
  stopCollectionTask,
  createCollectionTask,
  runCollectionTask,
  getCollectionTasks,
  saveCollectionSchedule,
} from '@/api'
import { useAuthStore } from '@/stores/auth'
import type {
  CollectionStatus,
  CollectionTargetState,
  CollectionTask,
  Product,
  DataSource,
} from '@/types/api'

const auth = useAuthStore()
const targets = ref<CollectionTargetState[]>([])
const products = ref<Product[]>([])
const sources = ref<DataSource[]>([])
const createDialogVisible = ref(false)
const createSubmitting = ref(false)
const createForm = reactive({
  product: undefined as number | undefined,
  source_target: undefined as number | undefined,
  pages: 2,
  target_url: '',
  target_name: '',
})
const availableEntries = computed(() =>
  sources.value.flatMap((source) =>
    (source.targets || [])
      .filter((target) => target.is_active && target.product === createForm.product)
      .map((target) => ({
        id: target.id,
        label: `${source.name} / ${target.name}`,
        status: target.validation_status,
      })),
  ),
)

const loading = ref(false)
const error = ref('')
const startingIds = ref(new Set<number>())
const scheduleDialogVisible = ref(false)
const scheduleSubmitting = ref(false)
const scheduleTarget = ref<CollectionTargetState | null>(null)
const historyVisible = ref(false)
const historyTarget = ref<CollectionTargetState | null>(null)
const history = ref<CollectionTask[]>([])
const activeTasks = ref<Record<number, CollectionTask>>({})
const refreshedAt = ref('')
const historyCount = ref(0)
const historyPage = ref(1)
const historyLoading = ref(false)
const selectedTask = ref<CollectionTask | null>(null)
const scheduleForm = reactive({ enabled: true, interval_hours: 6 })
let pollTimer: ReturnType<typeof setInterval> | undefined

const productTargets = computed(() => {
  const seen = new Set<number>()
  return [...targets.value]
    .sort((a, b) => Number(Boolean(b.active_task)) - Number(Boolean(a.active_task)))
    .filter((target) => {
      if (seen.has(target.product_id)) return false
      seen.add(target.product_id)
      return true
    })
})
const modeByProduct = reactive<Record<number, 'FULL' | 'INCREMENTAL' | 'PAGES'>>({})
const pagesByProduct = reactive<Record<number, number>>({})
const productBusy = (target: CollectionTargetState): boolean =>
  targets.value.some((item) => item.product_id === target.product_id && Boolean(item.active_task))

const hasActiveTarget = computed(() => targets.value.some((item) => Boolean(item.active_task)))
const statusType: Record<CollectionStatus, 'info' | 'primary' | 'warning' | 'success' | 'danger'> =
  {
    PENDING: 'info',
    RUNNING: 'primary',
    PAUSED: 'warning',
    SUCCESS: 'success',
    FAILED: 'danger',
    CANCELLED: 'info',
    STOPPING: 'warning',
  }
const triggerLabels: Record<CollectionTask['trigger_type'], string> = {
  MANUAL: '手工',
  SCHEDULED: '定时',
  RETRY: '重试',
  RECOVERY: '恢复',
}

function formatTime(value: string | null): string {
  if (!value) return '—'
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value))
}

function baselineText(target: CollectionTargetState): string {
  if (target.full_verified) return '全量完整性验证通过'
  if (target.has_historical_data) return '已有历史数据，待完整性验证'
  return '尚未完成全量初始化'
}

function currentStatus(target: CollectionTargetState): string {
  if (target.active_task_status === 'PENDING') return '等待中'
  if (target.active_task_status === 'RUNNING') return staleTask(target) ? '采集可能卡住' : '采集中'
  if (target.active_task_status === 'PAUSED') return '已暂停'
  if (target.active_task_status === 'STOPPING') return '正在停止'
  if (target.status === 'DEGRADED') return '最近运行异常'
  return '空闲'
}

async function loadTargets(silent = false): Promise<void> {
  if (!silent) loading.value = true
  error.value = ''
  try {
    const [response, productResponse, sourceResponse] = await Promise.all([
      getCollectionTargets({ page_size: 100 }),
      getProducts({ page_size: 100 }),
      getSources({ page_size: 100 }),
    ])
    products.value = productResponse.results
    sources.value = sourceResponse.results
    targets.value = response.results
    const activeIds = targets.value
      .map((target) => target.active_task)
      .filter((id): id is number => id !== null)
    if (activeIds.length) {
      const activePage = await getCollectionTasks({ page_size: 100, ordering: '-created_at' })
      activeTasks.value = Object.fromEntries(
        activePage.results
          .filter((task) => activeIds.includes(task.id))
          .map((task) => [task.id, task]),
      )
    } else activeTasks.value = {}
    refreshedAt.value = new Date().toLocaleTimeString('zh-CN')
    if (silent && !targets.value.some((item) => Boolean(item.active_task))) stopPolling()
  } catch {
    error.value = '采集控制状态加载失败。'
  } finally {
    if (!silent) loading.value = false
  }
}

function activeTask(target: CollectionTargetState): CollectionTask | undefined {
  return target.active_task ? activeTasks.value[target.active_task] : undefined
}

function staleTask(target: CollectionTargetState): boolean {
  const task = activeTask(target)
  return Boolean(task && Date.now() - new Date(task.updated_at).getTime() > 10 * 60_000)
}

function taskProgress(target: CollectionTargetState): string {
  const task = activeTask(target)
  if (!task) return target.active_task ? '正在读取任务进度…' : '无运行任务'
  if (task.status === 'PENDING') return `等待中 · ${task.waiting_reason || '等待来源调度'}`
  const checkpoint = task.last_checkpoint || {}
  const location = Object.entries(checkpoint)
    .filter(
      ([key, value]) =>
        /page|thread|cursor/i.test(key) && ['string', 'number'].includes(typeof value),
    )
    .slice(0, 3)
    .map(([key, value]) => `${key}: ${value}`)
    .join(' · ')
  return `任务 #${task.id} · 新增 ${task.new_records} · 重复 ${task.duplicate_records} · 失败 ${task.failure_count}${location ? ' · ' + location : ''}`
}

function collectionPhase(task: CollectionTask): string {
  const phase = String(task.last_checkpoint?.phase || '')
  if (phase === 'discovery') return '正在扫描帖子列表'
  if (phase === 'collection') return '正在采集帖子和回复'
  if (phase === 'retry') return '正在重试失败帖子'
  if (phase === 'verification') return '正在校验采集完整性'
  if (phase === 'completed') return '采集处理已结束'
  return task.status === 'PENDING' ? '等待调度' : '正在处理采集任务'
}

function discoveryProgress(task: CollectionTask): string {
  const checkpoint = task.last_checkpoint || {}
  const scanned = Number(checkpoint.scanned_topic_pages || 0)
  const expected = Number(checkpoint.expected_topic_pages || 0)
  return expected > 0
    ? `列表扫描 ${scanned} / ${expected} 页`
    : `已扫描 ${scanned} 页，正在确定总数`
}

function startPolling(): void {
  if (pollTimer) return
  pollTimer = setInterval(() => void loadTargets(true), 5000)
}

function stopPolling(): void {
  if (pollTimer) clearInterval(pollTimer)
  pollTimer = undefined
}

async function startProductCollection(target: CollectionTargetState): Promise<void> {
  if (productBusy(target)) {
    ElMessage.warning('该产品已有采集任务')
    return
  }
  const mode = modeByProduct[target.product_id] || 'PAGES'
  if (mode === 'INCREMENTAL' && !target.full_verified) {
    ElMessage.warning('请先完成全量完整性验证')
    return
  }
  try {
    await ElMessageBox.confirm(
      mode === 'PAGES'
        ? `确认执行最多 ${pagesByProduct[target.product_id] || 2} 页的测试采集？这不会建立全量基线。`
        : mode === 'FULL'
          ? '确认开始完整全量采集？'
          : '确认开始增量采集？',
      '启动采集',
      { type: 'warning' },
    )
  } catch {
    return
  }
  startingIds.value.add(target.id)
  try {
    const task = await createCollectionTask({
      source_target: target.source_target,
      task_type: mode === 'FULL' ? 'FULL' : 'INCREMENTAL',
      requested_pages: mode === 'PAGES' ? pagesByProduct[target.product_id] || 2 : undefined,
    })
    await runCollectionTask(task.id)
    ElMessage.success(`任务 #${task.id} 已启动`)
    await loadTargets(true)
    startPolling()
  } catch {
    ElMessage.error('启动失败，请检查是否存在运行中任务或采集入口状态')
  } finally {
    startingIds.value.delete(target.id)
  }
}

async function stopActive(target: CollectionTargetState): Promise<void> {
  if (!target.active_task) return
  try {
    await ElMessageBox.confirm('停止当前采集？已入库的数据将保留。', '停止采集', {
      type: 'warning',
      confirmButtonText: '停止采集',
      cancelButtonText: '返回',
    })
  } catch {
    return
  }
  try {
    const result = await stopCollectionTask(target.active_task)
    ElMessage.info(
      result.status === 'CANCELLED' ? '待执行任务已取消' : '已请求停止，等待当前采集步骤安全结束',
    )
    await loadTargets(true)
    startPolling()
  } catch {
    ElMessage.error('停止请求失败，请检查任务状态或管理员权限')
  }
}

async function recoverStale(target: CollectionTargetState): Promise<void> {
  if (!target.active_task) return
  try {
    await ElMessageBox.confirm(
      '仅当任务超过 15 分钟无更新且来源租约已过期时允许恢复。请先确认 Worker 没有仍在处理该任务。',
      '恢复异常任务',
      { type: 'warning' },
    )
    await recoverStaleCollectionTask(target.active_task)
    ElMessage.success('异常任务已标记失败，可重新创建采集')
    await loadTargets(true)
  } catch {
    await loadTargets(true)
  }
}

async function submitTestCollection(): Promise<void> {
  if (!createForm.product) {
    ElMessage.warning('请选择手机产品')
    return
  }
  createSubmitting.value = true
  try {
    let targetId = createForm.source_target
    if (!targetId) {
      const source = sources.value.find((item) => item.code === 'HONOR_CLUB')
      if (!source || !createForm.target_url.trim()) {
        ElMessage.warning('没有采集入口，请填写荣耀俱乐部入口 URL')
        return
      }
      const created = await createSourceTarget({
        source: source.id,
        product: createForm.product,
        name: createForm.target_name.trim() || '荣耀俱乐部测试入口',
        target_type: 'COMMUNITY',
        target_url: createForm.target_url.trim(),
        external_id: '',
        is_active: true,
      })
      targetId = created.id
    }
    const task = await createCollectionTask({
      source_target: targetId,
      task_type: 'INCREMENTAL',
      requested_pages: createForm.pages,
    })
    await runCollectionTask(task.id)
    createDialogVisible.value = false
    ElMessage.success(`测试任务 #${task.id} 已启动，最多采集 ${createForm.pages} 页`)
    await loadTargets(true)
    startPolling()
  } catch {
    ElMessage.error('创建失败：请检查采集入口、任务占用或网络配置')
  } finally {
    createSubmitting.value = false
  }
}

function openSchedule(target: CollectionTargetState): void {
  scheduleTarget.value = target
  scheduleForm.enabled = target.schedule_enabled
  scheduleForm.interval_hours = target.schedule_interval_hours ?? 6
  scheduleDialogVisible.value = true
}

async function submitSchedule(): Promise<void> {
  if (!scheduleTarget.value) return
  scheduleSubmitting.value = true
  try {
    await saveCollectionSchedule({
      source_target: scheduleTarget.value.source_target,
      enabled: scheduleForm.enabled,
      interval_hours: scheduleForm.interval_hours,
    })
    scheduleDialogVisible.value = false
    ElMessage.success('定时设置已保存')
    await loadTargets(true)
  } catch {
    error.value = '定时采集保存失败。'
  } finally {
    scheduleSubmitting.value = false
  }
}

async function loadHistory(page = historyPage.value): Promise<void> {
  if (!historyTarget.value) return
  historyLoading.value = true
  try {
    const response = await getCollectionTasks({
      source_target: historyTarget.value.source_target,
      page,
      page_size: 10,
      ordering: '-created_at',
    })
    history.value = response.results
    historyCount.value = response.count
    historyPage.value = page
  } catch {
    error.value = '运行历史加载失败。'
  } finally {
    historyLoading.value = false
  }
}

async function openHistory(target: CollectionTargetState): Promise<void> {
  historyTarget.value = target
  historyVisible.value = true
  historyPage.value = 1
  await loadHistory(1)
}

onMounted(async () => {
  await loadTargets()
  if (hasActiveTarget.value) startPolling()
})
onUnmounted(stopPolling)
</script>

<template>
  <div>
    <div class="page-header">
      <div>
        <h1 class="page-title">采集控制</h1>
        <p class="page-description">可先按指定页数测试采集；全量基线验证通过后才能启用正式增量。</p>
      </div>
      <div>
        <span v-if="refreshedAt" class="refresh-time"
          >最近刷新 {{ refreshedAt }} · 运行中每 5 秒自动更新</span
        ><el-button v-if="auth.canWrite" type="primary" @click="createDialogVisible = true"
          >新建测试采集</el-button
        ><el-button :loading="loading" @click="loadTargets()">刷新</el-button>
      </div>
    </div>

    <el-alert
      title="历史任务和反馈会完整保留；全量校验只会刷新、补漏和去重，不会删除已有数据。"
      type="info"
      show-icon
      :closable="false"
      class="notice"
    />
    <el-alert v-if="error" :title="error" type="error" :closable="false" class="notice" />

    <div v-loading="loading" class="target-grid">
      <el-card
        v-for="target in productTargets"
        :key="target.product_id"
        class="target-card"
        shadow="hover"
      >
        <div class="card-heading">
          <div>
            <h2>{{ target.product_name }}</h2>
            <p>{{ target.source_name }} · {{ target.target_name }}</p>
          </div>
          <el-tag
            :type="
              target.active_task ? 'primary' : target.status === 'DEGRADED' ? 'danger' : 'info'
            "
          >
            {{ currentStatus(target) }}
          </el-tag>
        </div>

        <div v-if="target.active_task" class="live-progress">
          <strong>实时采集状态</strong>
          <p v-if="activeTask(target)">
            <strong>{{ collectionPhase(activeTask(target)!) }}</strong> ·
            {{ discoveryProgress(activeTask(target)!) }}
          </p>
          <p>{{ taskProgress(target) }}</p>
          <p>
            状态：{{ activeTask(target)?.status || target.active_task_status }} · 最近心跳：{{
              formatTime(activeTask(target)?.updated_at || null)
            }}
          </p>
          <el-alert
            v-if="staleTask(target)"
            type="warning"
            :closable="false"
            title="任务超过 10 分钟未更新，可能卡住或 Worker 已停止；请检查任务详情与 Worker 日志，暂勿重复创建任务。"
          /><el-button size="small" @click="openHistory(target)">查看任务详情</el-button
          ><el-button
            v-if="
              auth.canWrite &&
              ['PENDING', 'RUNNING', 'PAUSED'].includes(
                activeTask(target)?.status || target.active_task_status || '',
              )
            "
            size="small"
            type="danger"
            plain
            @click="stopActive(target)"
            >停止采集</el-button
          ><el-button
            v-if="staleTask(target) && auth.canWrite"
            size="small"
            type="warning"
            @click="recoverStale(target)"
            >安全恢复</el-button
          >
        </div>
        <div class="state-block" :class="{ verified: target.full_verified }">
          <span class="state-label">数据基线</span>
          <strong>{{ baselineText(target) }}</strong>
          <small v-if="target.full_verified_at"
            >验证于 {{ formatTime(target.full_verified_at) }}</small
          >
        </div>

        <div class="facts">
          <div>
            <span>自动增量</span>
            <strong v-if="target.schedule_enabled"
              >每 {{ target.schedule_interval_hours }} 小时</strong
            >
            <strong v-else>未启用</strong>
          </div>
          <div>
            <span>最近成功</span>
            <strong>{{ formatTime(target.last_success_at) }}</strong>
          </div>
          <div>
            <span>最近验证帖子</span>
            <strong>{{ target.last_verified_thread_count || '—' }}</strong>
          </div>
        </div>

        <el-alert
          v-if="target.last_error"
          :title="target.last_error"
          type="error"
          :closable="false"
          class="target-error"
        />

        <div class="card-actions">
          <el-radio-group
            v-model="modeByProduct[target.product_id]"
            :disabled="productBusy(target)"
          >
            <el-radio-button value="FULL">全量</el-radio-button>
            <el-radio-button value="INCREMENTAL">增量</el-radio-button>
            <el-radio-button value="PAGES">测试采集（指定页数）</el-radio-button>
          </el-radio-group>
          <el-input-number
            v-if="(modeByProduct[target.product_id] || 'PAGES') === 'PAGES'"
            v-model="pagesByProduct[target.product_id]"
            :min="1"
            :max="10"
            :disabled="productBusy(target)"
          />
          <el-button
            type="primary"
            :disabled="!auth.canWrite || productBusy(target)"
            :loading="startingIds.has(target.id)"
            @click="startProductCollection(target)"
            >开始采集</el-button
          >
          <el-button :disabled="!auth.canWrite" @click="openSchedule(target)">定时设置</el-button>
          <el-button @click="openHistory(target)">运行历史</el-button>
        </div>
      </el-card>
      <el-empty v-if="!loading && !targets.length" description="暂无可用采集入口" />
    </div>

    <el-dialog v-model="createDialogVisible" title="新建测试采集任务" width="min(520px, 94vw)">
      <el-form label-position="top">
        <el-form-item label="手机产品"
          ><el-select
            v-model="createForm.product"
            filterable
            placeholder="选择产品"
            style="width: 100%"
            @change="createForm.source_target = undefined"
            ><el-option
              v-for="product in products"
              :key="product.id"
              :label="product.name"
              :value="product.id" /></el-select
        ></el-form-item>
        <el-form-item label="已有采集入口"
          ><el-select
            v-model="createForm.source_target"
            clearable
            placeholder="没有入口时可在下方新建"
            style="width: 100%"
            ><el-option
              v-for="entry in availableEntries"
              :key="entry.id"
              :label="entry.label"
              :value="entry.id" /></el-select
        ></el-form-item>
        <template v-if="!createForm.source_target">
          <el-form-item label="荣耀俱乐部入口 URL"
            ><el-input
              v-model="createForm.target_url"
              placeholder="https://club.honor.com/cn/threadtopic-..."
          /></el-form-item>
          <el-form-item label="入口名称"
            ><el-input v-model="createForm.target_name" placeholder="荣耀俱乐部测试入口"
          /></el-form-item>
        </template>
        <el-form-item label="最多采集页数"
          ><el-input-number v-model="createForm.pages" :min="1" :max="10"
        /></el-form-item>
        <el-alert
          type="info"
          :closable="false"
          title="测试采集无需全量基线；只保存本次采集结果，不标记全量完成。新入口需符合来源 URL 校验规则。"
        />
      </el-form>
      <template #footer
        ><el-button @click="createDialogVisible = false">取消</el-button
        ><el-button type="primary" :loading="createSubmitting" @click="submitTestCollection"
          >创建并启动</el-button
        ></template
      >
    </el-dialog>

    <el-dialog v-model="scheduleDialogVisible" title="定时增量设置" width="min(460px, 92vw)">
      <el-form label-position="top">
        <el-form-item label="采集入口">
          <strong>{{ scheduleTarget?.product_name }} / {{ scheduleTarget?.target_name }}</strong>
        </el-form-item>
        <el-form-item label="启用自动增量">
          <el-switch v-model="scheduleForm.enabled" />
        </el-form-item>
        <el-form-item label="执行频率">
          <el-input-number v-model="scheduleForm.interval_hours" :min="1" :max="168" />
          <span class="schedule-unit">小时</span>
        </el-form-item>
        <el-alert
          title="全量基线未验证时会记录跳过，不会创建或堆积增量任务；验证通过后按此频率运行。"
          type="info"
          :closable="false"
        />
      </el-form>
      <template #footer>
        <el-button @click="scheduleDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="scheduleSubmitting" @click="submitSchedule"
          >保存</el-button
        >
      </template>
    </el-dialog>

    <el-drawer v-model="historyVisible" size="min(900px, 96vw)" title="运行历史">
      <p v-if="historyTarget" class="history-subtitle">
        {{ historyTarget.product_name }} · {{ historyTarget.source_name }} ·
        {{ historyTarget.target_name }}
      </p>
      <el-table v-loading="historyLoading" :data="history" empty-text="暂无历史任务">
        <el-table-column prop="id" label="任务" width="75" />
        <el-table-column label="触发" width="80">
          <template #default="{ row }: { row: CollectionTask }">{{
            triggerLabels[row.trigger_type]
          }}</template>
        </el-table-column>
        <el-table-column prop="task_type" label="类型" width="110" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }: { row: CollectionTask }">
            <el-tag :type="statusType[row.status]">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="开始" min-width="135">
          <template #default="{ row }: { row: CollectionTask }">{{
            formatTime(row.started_at)
          }}</template>
        </el-table-column>
        <el-table-column label="新增 / 重复 / 失败" min-width="150">
          <template #default="{ row }: { row: CollectionTask }">
            {{ row.new_records }} / {{ row.duplicate_records }} / {{ row.failure_count }}
          </template>
        </el-table-column>
        <el-table-column label="完整性" width="100">
          <template #default="{ row }: { row: CollectionTask }">
            {{ row.task_type === 'FULL' ? (row.completion_verified ? '通过' : '未通过') : '—' }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="75" fixed="right">
          <template #default="{ row }: { row: CollectionTask }">
            <el-button link type="primary" @click="selectedTask = row">详情</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-pagination
        v-if="historyCount > 10"
        class="history-pagination"
        layout="prev, pager, next, total"
        :current-page="historyPage"
        :page-size="10"
        :total="historyCount"
        @current-change="loadHistory"
      />
    </el-drawer>

    <el-dialog
      :model-value="Boolean(selectedTask)"
      title="任务详情"
      width="min(700px, 94vw)"
      @close="selectedTask = null"
    >
      <el-descriptions v-if="selectedTask" :column="1" border>
        <el-descriptions-item label="任务">#{{ selectedTask.id }}</el-descriptions-item>
        <el-descriptions-item label="触发 / 类型 / 状态">
          {{ triggerLabels[selectedTask.trigger_type] }} / {{ selectedTask.task_type }} /
          {{ selectedTask.status }}
        </el-descriptions-item>
        <el-descriptions-item label="执行阶段">{{
          collectionPhase(selectedTask)
        }}</el-descriptions-item>
        <el-descriptions-item label="发现进度">{{
          discoveryProgress(selectedTask)
        }}</el-descriptions-item>
        <el-descriptions-item label="统计">
          新增 {{ selectedTask.new_records }}，重复 {{ selectedTask.duplicate_records }}，失败
          {{ selectedTask.failure_count }}
        </el-descriptions-item>
        <el-descriptions-item label="完整性报告">
          <pre>{{ JSON.stringify(selectedTask.verification_report, null, 2) }}</pre>
        </el-descriptions-item>
        <el-descriptions-item label="Checkpoint">
          <pre>{{ JSON.stringify(selectedTask.last_checkpoint, null, 2) }}</pre>
        </el-descriptions-item>
        <el-descriptions-item label="错误">{{
          selectedTask.error_message || '—'
        }}</el-descriptions-item>
      </el-descriptions>
    </el-dialog>
  </div>
</template>

<style scoped>
.live-progress {
  margin-top: 16px;
  padding: 14px;
  border: 1px solid var(--el-border-color);
  border-radius: 10px;
  background: var(--el-fill-color-light);
  color: var(--el-text-color-primary);
}
.live-progress p {
  margin: 8px 0;
  overflow-wrap: anywhere;
}
.refresh-time {
  margin-right: 12px;
  color: var(--el-text-color-regular);
  font-size: 12px;
}
.notice {
  margin-bottom: 16px;
}
.target-grid {
  display: grid;
  gap: 16px;
  min-height: 120px;
}
.target-card {
  border-radius: 14px;
}
.card-heading {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
}
.card-heading h2 {
  margin: 0 0 5px;
  font-size: 20px;
  color: var(--el-text-color-primary);
}
.card-heading p,
.history-subtitle {
  margin: 0;
  color: var(--el-text-color-regular);
}
.state-block {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 9px;
  margin: 18px 0;
  padding: 14px 16px;
  border-radius: 10px;
  border: 1px solid var(--el-color-warning-light-5);
  background: var(--el-fill-color-light);
  color: var(--el-text-color-primary);
}
.state-block.verified {
  border-color: var(--el-color-success-light-5);
  background: var(--el-fill-color-light);
  color: var(--el-text-color-primary);
}
.state-block small {
  color: var(--el-text-color-regular);
}
.state-label {
  color: var(--el-text-color-regular);
  margin-right: 4px;
}
.facts {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}
.facts div {
  padding: 12px 14px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 10px;
}
.facts span {
  display: block;
  margin-bottom: 7px;
  color: var(--el-text-color-regular);
  font-size: 13px;
}
.facts strong {
  color: var(--el-text-color-primary);
}
.target-error {
  margin-top: 14px;
}
.card-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 18px;
}
.card-actions .el-button {
  margin-left: 0;
}
.schedule-unit {
  margin-left: 8px;
}
.history-subtitle {
  margin-bottom: 16px;
}
.history-pagination {
  justify-content: flex-end;
  margin-top: 18px;
}
pre {
  margin: 0;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
  max-height: 320px;
  overflow: auto;
}
@media (max-width: 720px) {
  .facts {
    grid-template-columns: 1fr;
  }
  .card-heading {
    align-items: center;
  }
  .card-actions .el-button {
    flex: 1 1 calc(50% - 8px);
  }
}
</style>
