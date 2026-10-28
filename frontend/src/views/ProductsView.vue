<script setup lang="ts">
import { ElMessage } from 'element-plus'
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'

import {
  cleanupSourceTarget,
  createBrand,
  createProduct,
  createSourceTarget,
  getBrands,
  getCollectionTargets,
  getProducts,
  getSourceTargetCleanupPreview,
  getSources,
  startSmartCollection,
  updateProduct,
  updateSourceTarget,
  validateSourceTarget,
} from '@/api'
import { useAuthStore } from '@/stores/auth'
import type {
  CollectionTargetState,
  DataSource,
  Product,
  SourceTarget,
  SourceTargetCleanupPreview,
} from '@/types/api'

const auth = useAuthStore()
const router = useRouter()
const products = ref<Product[]>([])
const brands = ref<{ id: number; name: string; code: string }[]>([])
const sources = ref<DataSource[]>([])
const states = ref<CollectionTargetState[]>([])
const loading = ref(false)
const saving = ref(false)
const productDialog = ref(false)
const brandDialog = ref(false)
const targetDialog = ref(false)
const progressDialog = ref(false)
const cleanupDialog = ref(false)
const targetId = ref<number | null>(null)
const editingId = ref<number | null>(null)
const operatingTargetId = ref<number | null>(null)
const progressState = ref<CollectionTargetState | null>(null)
const cleanupPreview = ref<SourceTargetCleanupPreview | null>(null)
const cleanupConfirmation = ref('')
const form = reactive({ brand_id: undefined as number | undefined, name: '', is_active: true })
const brandForm = reactive({ name: '', code: '' })
const targetForm = reactive({
  product: undefined as number | undefined,
  source: undefined as number | undefined,
  name: '',
  target_url: '',
  external_id: '',
})
let pollTimer: ReturnType<typeof setInterval> | undefined

const honorSource = computed(() => sources.value.find((source) => source.code === 'HONOR_CLUB'))

function targetFor(product: Product): SourceTarget | undefined {
  return honorSource.value?.targets?.find((target) => target.product === product.id)
}

function stateFor(product: Product): CollectionTargetState | undefined {
  const target = targetFor(product)
  return target ? states.value.find((state) => state.source_target === target.id) : undefined
}

function collectionStatus(product: Product): {
  text: string
  type: 'info' | 'warning' | 'danger' | 'success'
} {
  const target = targetFor(product)
  const state = stateFor(product)
  if (!target) return { text: '未配置', type: 'info' }
  if (target.validation_status === 'UNVERIFIED') return { text: '待验证', type: 'warning' }
  if (target.validation_status === 'INVALID') return { text: '入口异常', type: 'danger' }
  if (state?.active_task_status === 'PENDING') return { text: '排队中', type: 'warning' }
  if (state?.status === 'FULL_RUNNING') return { text: '全量采集中', type: 'warning' }
  if (state?.status === 'INCREMENTAL_RUNNING') return { text: '增量采集中', type: 'warning' }
  if (state?.last_task_status === 'FAILED') return { text: '采集失败', type: 'danger' }
  if (state?.has_historical_data && !state.full_verified)
    return { text: '需要恢复', type: 'warning' }
  if (state?.last_task_status === 'SUCCESS') return { text: '采集成功', type: 'success' }
  return { text: '待采集', type: 'info' }
}

async function load(showLoading = true): Promise<void> {
  if (showLoading) loading.value = true
  try {
    const [productResult, brandResult, sourceResult, stateResult] = await Promise.all([
      getProducts({ page_size: 100 }),
      getBrands(),
      getSources({ page_size: 100 }),
      getCollectionTargets({ page_size: 100 }),
    ])
    products.value = productResult.results
    brands.value = brandResult.results
    sources.value = sourceResult.results
    states.value = stateResult.results
    if (progressState.value) {
      progressState.value =
        states.value.find((state) => state.id === progressState.value?.id) ?? null
    }
  } finally {
    loading.value = false
  }
}

async function saveProduct(): Promise<void> {
  if (!form.brand_id || !form.name.trim()) return
  saving.value = true
  try {
    if (editingId.value) {
      await updateProduct(editingId.value, { name: form.name, is_active: form.is_active })
    } else {
      await createProduct({ brand_id: form.brand_id, name: form.name })
    }
    productDialog.value = false
    ElMessage.success('手机信息已保存')
    await load()
  } finally {
    saving.value = false
  }
}

function openProduct(product?: Product): void {
  editingId.value = product?.id ?? null
  form.brand_id = product?.brand.id
  form.name = product?.name ?? ''
  form.is_active = product?.is_active ?? true
  productDialog.value = true
}

async function saveBrand(): Promise<void> {
  if (!brandForm.name.trim() || !brandForm.code.trim()) return
  saving.value = true
  try {
    await createBrand({ ...brandForm })
    brandDialog.value = false
    ElMessage.success('品牌已创建')
    await load()
  } finally {
    saving.value = false
  }
}

function openTarget(product: Product): void {
  const source = honorSource.value ?? sources.value[0]
  const existing = source?.targets?.find((target) => target.product === product.id)
  targetId.value = existing?.id ?? null
  Object.assign(targetForm, {
    product: product.id,
    source: source?.id,
    name: existing?.name ?? `${product.name} 荣耀俱乐部`,
    target_url: existing?.target_url ?? '',
    external_id: existing?.external_id ?? '',
  })
  targetDialog.value = true
}

async function saveTarget(): Promise<void> {
  if (!targetForm.product || !targetForm.source || !targetForm.target_url.trim()) {
    ElMessage.warning('请填写来源及入口网址')
    return
  }
  saving.value = true
  try {
    if (targetId.value) {
      await updateSourceTarget(targetId.value, {
        target_url: targetForm.target_url,
        external_id: targetForm.external_id,
      })
    } else {
      await createSourceTarget({
        source: targetForm.source,
        product: targetForm.product,
        name: targetForm.name,
        target_type: 'COMMUNITY',
        target_url: targetForm.target_url,
        external_id: targetForm.external_id,
        is_active: true,
      })
    }
    targetDialog.value = false
    ElMessage.success('入口已保存; 请先验证入口')
    await load()
  } finally {
    saving.value = false
  }
}

async function validateTarget(product: Product): Promise<void> {
  const target = targetFor(product)
  if (!target) return
  operatingTargetId.value = target.id
  try {
    await validateSourceTarget(target.id)
    ElMessage.success('入口验证通过')
  } finally {
    operatingTargetId.value = null
    await load()
  }
}

async function smartStart(product: Product): Promise<void> {
  const target = targetFor(product)
  const state = stateFor(product)
  if (!target || !state) {
    ElMessage.warning('请先配置并验证采集入口')
    return
  }
  operatingTargetId.value = target.id
  try {
    const result = await startSmartCollection(state.id)
    ElMessage.success(
      result.existing
        ? `已有采集任务 #${result.task_id}`
        : `已启动${result.task_type === 'FULL' ? '全量' : '增量'}任务 #${result.task_id}`,
    )
    await load()
  } finally {
    operatingTargetId.value = null
  }
}

function showProgress(product: Product): void {
  progressState.value = stateFor(product) ?? null
  progressDialog.value = true
}

async function showCleanup(product: Product): Promise<void> {
  const target = targetFor(product)
  if (!target) return
  cleanupPreview.value = await getSourceTargetCleanupPreview(target.id)
  cleanupConfirmation.value = ''
  cleanupDialog.value = true
}

async function confirmCleanup(): Promise<void> {
  if (!cleanupPreview.value) return
  const targetIdValue = cleanupPreview.value.source_target_id
  const expected = `DELETE ${targetIdValue}`
  if (cleanupConfirmation.value !== expected) {
    ElMessage.warning(`请输入确认文本: ${expected}`)
    return
  }
  saving.value = true
  try {
    await cleanupSourceTarget(targetIdValue, cleanupConfirmation.value)
    cleanupDialog.value = false
    ElMessage.success('该入口数据已清理; 手机和入口配置仍保留')
    await load()
  } finally {
    saving.value = false
  }
}

function openRawData(product: Product): void {
  const target = targetFor(product)
  void router.push({ path: '/reviews', query: { product: product.id, source_target: target?.id } })
}

onMounted(async () => {
  await load()
  pollTimer = setInterval(() => {
    if (states.value.some((state) => state.active_task !== null)) void load(false)
  }, 5000)
})
onUnmounted(() => pollTimer && clearInterval(pollTimer))
</script>

<template>
  <div>
    <div class="page-header">
      <div>
        <h1 class="page-title">手机产品</h1>
        <p class="page-description">
          配置并验证公开入口后，系统会自动选择全量初始化、恢复或增量采集。
        </p>
      </div>
      <div>
        <el-button @click="load()">刷新</el-button>
        <el-button v-if="auth.canWrite" @click="brandDialog = true">新增品牌</el-button>
        <el-button v-if="auth.canWrite" type="primary" @click="openProduct()">新增手机</el-button>
      </div>
    </div>

    <div class="panel product-panel">
      <el-table v-loading="loading" :data="products" empty-text="暂无手机产品">
        <el-table-column label="手机产品" min-width="150"
          ><template #default="{ row }"
            ><strong>{{ row.name }}</strong
            ><el-button v-if="auth.canWrite" link @click="openProduct(row)"
              >编辑</el-button
            ></template
          ></el-table-column
        >
        <el-table-column label="采集入口" min-width="210">
          <template #default="{ row }">
            <template v-if="targetFor(row)">
              <div>{{ targetFor(row)?.name }}</div>
              <el-link :href="targetFor(row)?.target_url" target="_blank" type="primary"
                >打开原始网页</el-link
              >
            </template>
            <span v-else class="muted">未配置</span>
          </template>
        </el-table-column>
        <el-table-column label="入口验证" width="120">
          <template #default="{ row }">
            <el-tag v-if="targetFor(row)?.validation_status === 'VALID'" type="success"
              >已验证</el-tag
            >
            <el-tag v-else-if="targetFor(row)?.validation_status === 'INVALID'" type="danger"
              >验证失败</el-tag
            >
            <el-tag v-else type="warning">待验证</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="采集状态" width="120"
          ><template #default="{ row }"
            ><el-tag :type="collectionStatus(row).type">{{
              collectionStatus(row).text
            }}</el-tag></template
          ></el-table-column
        >
        <el-table-column label="采集状态" width="130">
          <template #default="{ row }"
            ><el-tag :type="collectionStatus(row).type">{{
              collectionStatus(row).text
            }}</el-tag></template
          >
        </el-table-column>
        <el-table-column label="最近结果" min-width="190">
          <template #default="{ row }">
            <template v-if="stateFor(row)?.last_task_type">
              {{ stateFor(row)?.last_task_type }} · 新帖 {{ stateFor(row)?.last_new_threads }} ·
              新回复 {{ stateFor(row)?.last_new_replies }}
            </template>
            <span v-else class="muted">暂无运行记录</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="420" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openTarget(row)">配置入口</el-button>
            <el-button
              v-if="targetFor(row)"
              link
              type="primary"
              :loading="operatingTargetId === targetFor(row)?.id"
              @click="validateTarget(row)"
              >验证入口</el-button
            >
            <el-button
              link
              type="success"
              :disabled="
                targetFor(row)?.validation_status !== 'VALID' || Boolean(stateFor(row)?.active_task)
              "
              :loading="operatingTargetId === targetFor(row)?.id"
              @click="smartStart(row)"
              >智能采集</el-button
            >
            <el-button v-if="stateFor(row)" link @click="showProgress(row)">查看进度</el-button>
            <el-button link @click="openRawData(row)">查看原始数据</el-button>
            <el-button
              v-if="auth.isAdmin && targetFor(row)"
              link
              type="danger"
              @click="showCleanup(row)"
              >清理该入口数据</el-button
            >
          </template>
        </el-table-column>
      </el-table>
    </div>

    <el-dialog
      v-model="productDialog"
      :title="editingId ? '编辑手机' : '新增手机'"
      width="min(520px, 94vw)"
    >
      <el-form label-position="top">
        <el-form-item label="品牌"
          ><el-select v-model="form.brand_id" :disabled="Boolean(editingId)"
            ><el-option
              v-for="brand in brands"
              :key="brand.id"
              :label="brand.name"
              :value="brand.id" /></el-select
        ></el-form-item>
        <el-form-item label="手机名称"
          ><el-input v-model="form.name" placeholder="如 荣耀 Power"
        /></el-form-item>
        <el-form-item v-if="editingId" label="启用"
          ><el-switch v-model="form.is_active"
        /></el-form-item>
      </el-form>
      <template #footer
        ><el-button @click="productDialog = false">取消</el-button
        ><el-button type="primary" :loading="saving" @click="saveProduct">保存</el-button></template
      >
    </el-dialog>
    <el-dialog v-model="brandDialog" title="新增品牌" width="min(440px, 94vw)">
      <el-form label-position="top"
        ><el-form-item label="品牌名称"><el-input v-model="brandForm.name" /></el-form-item
        ><el-form-item label="唯一编码"><el-input v-model="brandForm.code" /></el-form-item
      ></el-form>
      <template #footer
        ><el-button @click="brandDialog = false">取消</el-button
        ><el-button type="primary" :loading="saving" @click="saveBrand">保存</el-button></template
      >
    </el-dialog>
    <el-dialog
      v-model="targetDialog"
      :title="targetId ? '编辑采集入口' : '新增采集入口'"
      width="min(560px, 94vw)"
    >
      <el-form label-position="top">
        <el-form-item label="数据来源"
          ><el-select v-model="targetForm.source" :disabled="Boolean(targetId)"
            ><el-option
              v-for="source in sources"
              :key="source.id"
              :label="source.name"
              :value="source.id" /></el-select
        ></el-form-item>
        <el-form-item label="采集网址"
          ><el-input v-model="targetForm.target_url" placeholder="荣耀俱乐部公开话题页" /><el-link
            v-if="targetForm.target_url"
            :href="targetForm.target_url"
            target="_blank"
            type="primary"
            >打开原始网页</el-link
          ></el-form-item
        >
        <el-alert
          title="网址修改后，原验证结果和全量基线会自动失效。"
          type="warning"
          :closable="false"
        />
      </el-form>
      <template #footer
        ><el-button @click="targetDialog = false">取消</el-button
        ><el-button type="primary" :loading="saving" @click="saveTarget"
          >保存入口</el-button
        ></template
      >
    </el-dialog>

    <el-dialog v-model="progressDialog" title="采集进度" width="min(620px, 94vw)">
      <el-descriptions v-if="progressState" :column="2" border>
        <el-descriptions-item label="当前状态">{{ progressState.status }}</el-descriptions-item>
        <el-descriptions-item label="任务阶段">{{
          progressState.progress_stage || '空闲'
        }}</el-descriptions-item>
        <el-descriptions-item label="最近任务"
          >{{ progressState.last_task_type || '—' }} /
          {{ progressState.last_task_status || '—' }}</el-descriptions-item
        >
        <el-descriptions-item label="失败数量">{{
          progressState.last_failure_count
        }}</el-descriptions-item>
        <el-descriptions-item label="新增帖子">{{
          progressState.last_new_threads
        }}</el-descriptions-item>
        <el-descriptions-item label="新增回复">{{
          progressState.last_new_replies
        }}</el-descriptions-item>
        <el-descriptions-item label="最近错误" :span="2">{{
          progressState.last_error || '无'
        }}</el-descriptions-item>
      </el-descriptions>
      <el-alert
        title="仅展示后台可确认的阶段和数量，不提供推测性百分比。"
        type="info"
        :closable="false"
        style="margin-top: 16px"
      />
    </el-dialog>

    <el-dialog v-model="cleanupDialog" title="清理该入口数据" width="min(660px, 94vw)">
      <template v-if="cleanupPreview">
        <el-alert
          title="只清理当前入口，不删除手机和入口配置；操作在单个数据库事务中完成。"
          type="error"
          :closable="false"
        />
        <el-descriptions :column="2" border style="margin: 16px 0">
          <el-descriptions-item label="手机">{{ cleanupPreview.product_name }}</el-descriptions-item
          ><el-descriptions-item label="来源">{{
            cleanupPreview.source_name
          }}</el-descriptions-item>
          <el-descriptions-item label="帖子">{{ cleanupPreview.thread_count }}</el-descriptions-item
          ><el-descriptions-item label="回复">{{
            cleanupPreview.reply_count
          }}</el-descriptions-item>
          <el-descriptions-item label="治理记录">{{
            cleanupPreview.review_quality_count + cleanupPreview.review_quality_run_count
          }}</el-descriptions-item
          ><el-descriptions-item label="AI/结构化结果">{{
            cleanupPreview.analysis_result_count +
            cleanupPreview.analysis_run_count +
            cleanupPreview.structured_analysis_count
          }}</el-descriptions-item>
          <el-descriptions-item label="历史采集任务">{{
            cleanupPreview.collection_task_count
          }}</el-descriptions-item
          ><el-descriptions-item label="活动任务">{{
            cleanupPreview.active_collection_count + cleanupPreview.active_analysis_count
          }}</el-descriptions-item>
        </el-descriptions>
        <el-input
          v-model="cleanupConfirmation"
          :placeholder="`请输入 DELETE ${cleanupPreview.source_target_id}`"
        />
      </template>
      <template #footer
        ><el-button @click="cleanupDialog = false">取消</el-button
        ><el-button type="danger" :loading="saving" @click="confirmCleanup"
          >确认清理</el-button
        ></template
      >
    </el-dialog>
  </div>
</template>

<style scoped>
.product-panel {
  overflow: hidden;
}
.muted {
  color: var(--el-text-color-secondary);
}
</style>
