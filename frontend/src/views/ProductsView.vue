<script setup lang="ts">
import { ElMessage } from 'element-plus'
import { computed, nextTick, onMounted, onUnmounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import CollectionTasksView from './CollectionTasksView.vue'

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
const targetValidationError = ref('')
const cleanupDialog = ref(false)
const targetId = ref<number | null>(null)
const editingId = ref<number | null>(null)
const inlineEditingId = ref<number | null>(null)
const inlineName = ref('')
const inlineSaving = ref(false)
const inlineInput = ref<{ focus: () => void } | null>(null)
let inlineCancelPending = false
function beginInlineEdit(product: Product): void {
  if (!auth.canWrite || inlineSaving.value) return
  inlineCancelPending = false
  inlineEditingId.value = product.id
  inlineName.value = product.name
  void nextTick(() => inlineInput.value?.focus())
}
function cancelInlineEdit(): void {
  inlineCancelPending = true
  inlineEditingId.value = null
  inlineName.value = ''
}
async function saveInlineName(product: Product): Promise<void> {
  if (inlineCancelPending || inlineEditingId.value !== product.id || inlineSaving.value) return
  const name = inlineName.value.trim()
  if (!name) {
    cancelInlineEdit()
    return
  }
  if (name === product.name) {
    cancelInlineEdit()
    return
  }
  inlineSaving.value = true
  try {
    await updateProduct(product.id, { name })
    cancelInlineEdit()
    await load()
  } catch {
    ElMessage.error('修改失败，请重试')
  } finally {
    inlineSaving.value = false
  }
}

const operatingTargetId = ref<number | null>(null)
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
  targetValidationError.value = ''
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

function validationErrorMessage(error: unknown): string {
  const response = (
    error as { response?: { data?: { detail?: string; code?: string; message?: string } } }
  )?.response?.data
  return (
    response?.detail ||
    response?.message ||
    (error instanceof Error ? error.message : '验证失败，请检查采集网址和网络连接')
  )
}

async function saveTarget(): Promise<void> {
  if (!targetForm.product || !targetForm.source || !targetForm.target_url.trim()) {
    targetValidationError.value = '请填写来源及入口网址'
    return
  }
  saving.value = true
  targetValidationError.value = ''
  try {
    let id = targetId.value
    if (id) {
      await updateSourceTarget(id, {
        target_url: targetForm.target_url.trim(),
        external_id: targetForm.external_id,
      })
    } else {
      const created = await createSourceTarget({
        source: targetForm.source,
        product: targetForm.product,
        name: targetForm.name,
        target_type: 'COMMUNITY',
        target_url: targetForm.target_url.trim(),
        external_id: targetForm.external_id,
        is_active: true,
      })
      id = created.id
      targetId.value = id
    }
    if (!id) throw new Error('采集入口保存成功，但未返回入口编号')
    const validation = await validateSourceTarget(id)
    if (validation.valid !== true) {
      targetValidationError.value = validation.detail || '入口验证未通过'
      return
    }
    targetDialog.value = false
    await load()
  } catch (error) {
    targetValidationError.value = validationErrorMessage(error)
    await load().catch(() => undefined)
  } finally {
    saving.value = false
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
            ><div v-if="inlineEditingId === row.id" class="inline-name-editor">
              <el-input
                ref="inlineInput"
                v-model="inlineName"
                size="small"
                maxlength="100"
                :disabled="inlineSaving"
                aria-label="修改手机名称"
                @keyup.enter="($event.target as HTMLInputElement).blur()"
                @keyup.esc.stop.prevent="cancelInlineEdit"
                @blur="saveInlineName(row)"
              />
            </div>
            <strong
              v-else-if="auth.canWrite"
              class="editable-product-name"
              role="button"
              tabindex="0"
              @click="beginInlineEdit(row)"
              @keydown.enter.prevent="beginInlineEdit(row)"
              @keydown.space.prevent="beginInlineEdit(row)"
              >{{ row.name }}</strong
            >
            <strong v-else>{{ row.name }}</strong>
          </template></el-table-column
        >
        <el-table-column label="采集入口" min-width="210">
          <template #default="{ row }">
            <template v-if="targetFor(row)">
              <el-link
                v-if="targetFor(row)?.target_url"
                :href="targetFor(row)?.target_url"
                target="_blank"
                type="primary"
                :underline="false"
                :title="`打开采集入口：${targetFor(row)?.name}`"
                >{{ targetFor(row)?.name }}</el-link
              >
              <span v-else>{{ targetFor(row)?.name }}</span>
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
              link
              type="success"
              :disabled="
                targetFor(row)?.validation_status !== 'VALID' || Boolean(stateFor(row)?.active_task)
              "
              :loading="operatingTargetId === targetFor(row)?.id"
              @click="smartStart(row)"
              >智能采集</el-button
            >
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

    <section v-if="auth.isAdmin" class="panel" style="margin-top: 18px">
      <h2>采集任务管理</h2>
      <p class="page-description">
        各产品默认折叠，运行中或异常时自动展开；点击产品名称查看采集计划、任务进度及历史。
      </p>
      <CollectionTasksView embedded />
    </section>

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
      <el-alert
        v-if="targetValidationError"
        :title="targetValidationError"
        type="error"
        :closable="false"
        show-icon
        style="margin-top: 12px"
      />
      <template #footer
        ><el-button @click="targetDialog = false">取消</el-button
        ><el-button type="primary" :loading="saving" @click="saveTarget"
          >保存并验证</el-button
        ></template
      >
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
.editable-product-name {
  cursor: text;
}
.editable-product-name:focus-visible {
  outline-offset: 3px;
}
.inline-name-editor {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 240px;
}
.inline-name-editor :deep(.el-input) {
  min-width: 110px;
}

.product-panel {
  overflow: hidden;
}
.muted {
  color: var(--el-text-color-regular);
}
/* Keep the progress dialog readable without selecting text or hovering rows. */
.product-panel :deep(.el-table) {
  --el-table-header-bg-color: var(--el-fill-color-light);
  --el-table-row-hover-bg-color: var(--el-fill-color-light);
  --el-table-text-color: var(--el-text-color-primary);
}
.product-panel :deep(.el-table th.el-table__cell) {
  color: var(--el-text-color-primary);
  font-weight: 600;
}
.product-panel :deep(.el-tag) {
  font-weight: 600;
}
</style>
