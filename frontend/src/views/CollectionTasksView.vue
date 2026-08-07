<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { createCollectionTask, getCollectionTasks, getProducts, getSources } from '@/api'
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
const error = ref('')
const form = reactive({
  product: undefined as number | undefined,
  source: undefined as number | undefined,
  source_target: undefined as number | undefined,
  task_type: 'INCREMENTAL' as 'FULL' | 'INCREMENTAL',
  requested_limit: 100,
})

const targets = computed<SourceTarget[]>(() => {
  const source = sources.value.find((item) => item.id === form.source)
  return (source?.targets || []).filter(
    (target) => !form.product || target.product === form.product,
  )
})

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
    await loadData()
  } catch {
    error.value = '任务创建失败，请检查采集入口配置。'
  } finally {
    submitting.value = false
  }
}

onMounted(loadData)
</script>

<template>
  <div>
    <div class="page-header">
      <div>
        <h1 class="page-title">采集任务</h1>
        <p class="page-description">管理采集计划和运行状态，不包含具体网站页面逻辑。</p>
      </div>
      <el-button type="primary" @click="dialogVisible = true">创建任务</el-button>
    </div>
    <el-alert
      title="Phase 1 的京东与荣耀俱乐部采集器尚未实现；执行任务会明确记录 collector not implemented，不会生成虚假数据。"
      type="warning"
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
        <el-table-column prop="failure_count" label="失败" width="80" />
        <el-table-column
          prop="error_message"
          label="错误信息"
          min-width="190"
          show-overflow-tooltip
        />
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
            @change="form.source_target = undefined"
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
          <el-input-number v-model="form.requested_limit" :min="1" :max="10000" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submitTask">创建</el-button>
      </template>
    </el-dialog>
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
</style>
