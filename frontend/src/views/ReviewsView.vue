<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'

import {
  getReviewFacets,
  getReviewMetadataCompleteness,
  getReviews,
  getSources,
  getProducts,
} from '@/api'
import type { DataSource, ReviewMetadataCompleteness, ReviewRecord, Product } from '@/types/api'

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
const reviews = ref<ReviewRecord[]>([])
const route = useRoute()
const sources = ref<DataSource[]>([])
const products = ref<Product[]>([])
const facets = ref<{
  variants: { product_variant_id: number; product_variant__sku_name: string; count: number }[]
  regions: { source_region: string; count: number }[]
  ratings: { rating: string; count: number }[]
}>({ variants: [], regions: [], ratings: [] })
const selected = ref<ReviewRecord | null>(null)
const loading = ref(false)
const error = ref('')
const total = ref(0)
const metadata = ref<ReviewMetadataCompleteness | null>(null)
const filters = reactive({
  page: 1,
  page_size: 20,
  ordering: '-published_at',
  source: undefined as number | undefined,
  rating: undefined as number | undefined,
  search: '',
  source_region: '',
  product: route.query.product ? Number(route.query.product) : (undefined as number | undefined),
  source_target: route.query.source_target
    ? Number(route.query.source_target)
    : (undefined as number | undefined),
  record_type: '',
  author_role: '',
  is_official: '' as '' | 'true' | 'false',
})

async function loadReviews(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    const response = await getReviews({
      ...filters,
      is_official: filters.is_official || undefined,
      record_type: filters.record_type || undefined,
      author_role: filters.author_role || undefined,
      search: filters.search || undefined,
      source_region: filters.source_region || undefined,
      product: filters.product,
      source_target: filters.source_target,
    })
    reviews.value = response.results
    total.value = response.count
  } catch {
    error.value = '原始数据加载失败。'
  } finally {
    loading.value = false
  }
}

async function loadMetadata(): Promise<void> {
  metadata.value = await getReviewMetadataCompleteness({
    source: filters.source,
    product: filters.product,
    source_target: filters.source_target,
    record_type: filters.record_type || undefined,
  })
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
    hourCycle: 'h23',
  }).formatToParts(date)
  const part = (type: string) => parts.find((item) => item.type === type)?.value || ''
  return `${part('year')}-${part('month')}-${part('day')} ${part('hour')}:${part('minute')}`
}

function formatRate(value: number): string {
  return `${(value * 100).toFixed(2)}%`
}

function onSortChange(sort: {
  prop: string | null
  order: 'ascending' | 'descending' | null
}): void {
  const fields: Record<string, string> = {
    source_name: 'source__name',
    product_name: 'product__name',
    record_type: 'record_type',
    content: 'content',
    author_role: 'author_role',
    ip_location: 'source_region',
    published_at: 'published_at',
    collected_at: 'collected_at',
  }
  filters.ordering =
    sort.prop && sort.order && fields[sort.prop]
      ? `${sort.order === 'descending' ? '-' : ''}${fields[sort.prop]}`
      : '-published_at'
  filters.page = 1
  void loadReviews()
}

function onPageSizeChange(size: number): void {
  if (filters.page_size === size) return
  filters.page_size = size
  filters.page = 1
  void loadReviews()
}

function applyFilters(): void {
  filters.page = 1
  void Promise.all([loadReviews(), loadMetadata()])
}

onMounted(async () => {
  try {
    const [sourcePage, productPage, facetPage, metadataPage] = await Promise.all([
      getSources({ page_size: 100 }),
      getProducts({ page_size: 100 }),
      getReviewFacets(),
      getReviewMetadataCompleteness({
        product: filters.product,
        source_target: filters.source_target,
      }),
    ])
    sources.value = sourcePage.results
    products.value = productPage.results
    facets.value = facetPage
    metadata.value = metadataPage
  } finally {
    await loadReviews()
  }
})
</script>

<template>
  <div class="reviews-page">
    <header class="page-header"><div><h1 class="page-title">原始数据</h1><p class="page-description">查看、筛选与检索已采集的原始反馈数据</p></div></header>
    <el-alert v-if="error" :title="error" type="error" :closable="false" class="notice" />
    <div class="panel data-panel">
      <div class="filters">
        <el-select
          v-model="filters.product"
          clearable
          filterable
          placeholder="全部产品"
          @change="applyFilters"
        >
          <el-option
            v-for="product in products"
            :key="product.id"
            :label="product.name"
            :value="product.id"
          />
        </el-select>
        <el-select v-model="filters.source" clearable placeholder="全部来源" @change="applyFilters">
          <el-option
            v-for="source in sources"
            :key="source.id"
            :label="source.name"
            :value="source.id"
          />
        </el-select>
        <el-select
          v-model="filters.record_type"
          clearable
          placeholder="记录类型"
          @change="applyFilters"
        >
          <el-option label="评价" value="REVIEW" />
          <el-option label="追评" value="APPEND_REVIEW" />
          <el-option label="帖子" value="THREAD" />
          <el-option label="回复" value="REPLY" />
          <el-option label="官方回复" value="OFFICIAL_REPLY" />
        </el-select>
        <el-select v-model="filters.is_official" placeholder="是否官方" @change="applyFilters">
          <el-option label="全部角色" value="" />
          <el-option label="仅官方" value="true" />
          <el-option label="仅用户" value="false" />
        </el-select>
        <el-select
          v-model="filters.author_role"
          clearable
          placeholder="作者角色"
          @change="applyFilters"
        >
          <el-option label="普通用户" value="USER" />
          <el-option label="官方" value="OFFICIAL" />
          <el-option label="版主" value="MODERATOR" />
          <el-option label="达人" value="EXPERT" />
          <el-option label="未知" value="UNKNOWN" />
        </el-select>
        <el-input
          v-model="filters.search"
          clearable
          placeholder="搜索内容关键词"
          @keyup.enter="applyFilters"
        >
          <template #append><el-button @click="applyFilters">搜索</el-button></template>
        </el-input>
      </div>

      <div v-if="metadata" class="metadata-strip" aria-label="原始数据字段完整率">
        <span>
          发布时间完整率
          <strong>{{ formatRate(metadata.summary.published_at_rate) }}</strong>
          <small>{{ metadata.summary.published_at_count }}/{{ metadata.summary.total }}</small>
        </span>
        <span>
          公开 IP 属地完整率
          <strong>{{ formatRate(metadata.summary.ip_location_rate) }}</strong>
          <small>{{ metadata.summary.ip_location_count }}/{{ metadata.summary.total }}</small>
        </span>
      </div>

      <el-table
        v-loading="loading"
        :data="reviews"
        empty-text="暂无反馈记录"
        @row-click="selected = $event"
        @sort-change="onSortChange"
        :default-sort="{ prop: 'published_at', order: 'descending' }"
      >
        <el-table-column prop="source_name" label="来源" sortable="custom" width="120" />
        <el-table-column prop="product_name" label="产品" sortable="custom" width="150" />
        <el-table-column prop="record_type" label="类型" sortable="custom" width="130">
          <template #default="{ row }: { row: ReviewRecord }">
            {{ recordTypeLabels[row.record_type] || row.record_type }}
          </template>
        </el-table-column>
        <el-table-column
          prop="content"
          label="内容"
          sortable="custom"
          min-width="300"
          show-overflow-tooltip
        />
        <el-table-column prop="author_role" label="角色" width="90" sortable="custom">
          <template #default="{ row }: { row: ReviewRecord }">
            <el-tag :type="row.is_official ? 'warning' : 'info'">{{
              authorRoleLabels[row.author_role] || row.author_role
            }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="ip_location" label="IP 属地" sortable="custom" width="100" />
        <el-table-column prop="published_at" label="发布时间" sortable="custom" width="150"
          ><template #default="{ row }"
            ><span class="compact-time">{{ formatPublishedAt(row.published_at) }}</span></template
          ></el-table-column
        >
        <el-table-column prop="collected_at" label="采集时间" sortable="custom" width="150"
          ><template #default="{ row }: { row: ReviewRecord }"
            ><span class="compact-time">{{ formatPublishedAt(row.collected_at) }}</span></template
          ></el-table-column
        >
      </el-table>

      <div class="reviews-pagination">
        <el-pagination
          v-model:current-page="filters.page"
          class="pagination"
          layout="total, sizes, prev, pager, next, jumper"
          :page-size="filters.page_size"
          :page-sizes="[10, 20, 50, 100]"
          :total="total"
          @size-change="onPageSizeChange"
          @current-change="loadReviews"
        />
      </div>
    </div>

    <el-drawer
      :model-value="Boolean(selected)"
      title="反馈详情"
      size="min(560px, 92vw)"
      @close="selected = null"
    >
      <template v-if="selected">
        <el-descriptions :column="1" border>
          <el-descriptions-item label="来源">{{ selected.source_name }}</el-descriptions-item>
          <el-descriptions-item label="产品">{{ selected.product_name }}</el-descriptions-item>
          <el-descriptions-item label="类型">{{
            recordTypeLabels[selected.record_type] || selected.record_type
          }}</el-descriptions-item>
          <el-descriptions-item label="标题">{{ selected.title || '—' }}</el-descriptions-item>
          <el-descriptions-item label="内容">{{ selected.content }}</el-descriptions-item>
          <el-descriptions-item label="发布时间">{{
            formatPublishedAt(selected.published_at)
          }}</el-descriptions-item>
          <el-descriptions-item label="IP 属地">{{
            selected.ip_location || ''
          }}</el-descriptions-item>
          <el-descriptions-item label="采集时间">{{
            formatPublishedAt(selected.collected_at)
          }}</el-descriptions-item>
          <el-descriptions-item label="软件版本">{{
            selected.software_version || '未提供'
          }}</el-descriptions-item>
          <el-descriptions-item label="角色">{{
            authorRoleLabels[selected.author_role] || selected.author_role
          }}</el-descriptions-item>
          <el-descriptions-item label="External ID">{{
            selected.external_id || '—'
          }}</el-descriptions-item>
          <el-descriptions-item label="Parent External ID">{{
            selected.parent_external_id || '—'
          }}</el-descriptions-item>
          <el-descriptions-item label="来源 URL">
            <a
              v-if="selected.source_url"
              :href="selected.source_url"
              target="_blank"
              rel="noreferrer"
            >
              {{ selected.source_url }}
            </a>
            <span v-else>—</span>
          </el-descriptions-item>
          <el-descriptions-item label="Raw data">
            <pre>{{ JSON.stringify(selected.raw_data, null, 2) }}</pre>
          </el-descriptions-item>
        </el-descriptions>
      </template>
    </el-drawer>
  </div>
</template>

<style scoped>
.notice {
  margin-bottom: 16px;
}

.data-panel {
  padding: 14px;
}

.metadata-strip {
  display: flex;
  justify-content: flex-end;
  gap: 18px;
  margin: -4px 0 10px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.metadata-strip > span {
  display: inline-flex;
  align-items: baseline;
  gap: 5px;
}

.metadata-strip strong {
  color: var(--el-text-color-primary);
  font-size: 14px;
}

.metadata-strip small {
  color: var(--el-text-color-secondary);
}

.filters {
  display: grid;
  grid-template-columns: repeat(6, minmax(120px, 1fr));
  gap: 12px;
  margin-bottom: 10px;
}

.compact-time {
  white-space: nowrap;
  font-size: 12px;
}

pre {
  margin: 0;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}

@media (max-width: 900px) {
  .metadata-strip {
    justify-content: flex-start;
    flex-wrap: wrap;
  }
}

.reviews-pagination {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  overflow-x: auto;
  margin-top: 18px;
}

.pagination {
  justify-content: flex-end;
}

@media (max-width: 900px) {
  .metadata-grid {
    grid-template-columns: 1fr;
  }

  .filters {
    grid-template-columns: 1fr 1fr;
  }
}

@media (max-width: 540px) {
  .filters {
    grid-template-columns: 1fr;
  }
}
</style>
