<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'

import { getReviewFacets, getReviewMetadataCompleteness, getReviews, getSources } from '@/api'
import type { DataSource, ReviewMetadataCompleteness, ReviewRecord } from '@/types/api'

const reviews = ref<ReviewRecord[]>([])
const route = useRoute()
const sources = ref<DataSource[]>([])
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

function formatRate(value: number): string {
  return `${(value * 100).toFixed(2)}%`
}

const reasonLabels: Record<string, string> = {
  source_time_missing: '页面未提供发布时间',
  source_time_missing_or_legacy_not_captured: '页面未提供或历史版本未保存时间',
  legacy_relative_time_not_normalized: '历史相对时间未标准化',
  legacy_time_parse_failed: '历史时间格式无法解析',
  relative_day_without_time_precision: '页面仅显示“几天前”，缺少具体时分',
  unsupported_time_format: '时间格式不受支持',
  legacy_ip_location_not_captured: '历史版本未采集 IP 属地',
  source_ip_location_missing: '页面未提供 IP 属地',
  source_ip_location_unknown: '页面显示属地未知',
  profile_region_not_publicly_labeled: '页面未公开标注用户填写地区',
}

function summarizeReasons(reasons: Record<string, number>): string {
  const items = Object.entries(reasons)
  if (!items.length) return '无'
  return items.map(([reason, count]) => `${reasonLabels[reason] || reason} ${count}`).join('；')
}

function applyFilters(): void {
  filters.page = 1
  void Promise.all([loadReviews(), loadMetadata()])
}

onMounted(async () => {
  try {
    const [sourcePage, facetPage, metadataPage] = await Promise.all([
      getSources({ page_size: 100 }),
      getReviewFacets(),
      getReviewMetadataCompleteness({
        product: filters.product,
        source_target: filters.source_target,
      }),
    ])
    sources.value = sourcePage.results
    facets.value = facetPage
    metadata.value = metadataPage
  } finally {
    await loadReviews()
  }
})
</script>

<template>
  <div>
    <div class="page-header">
      <div>
        <h1 class="page-title">原始数据</h1>
      </div>
    </div>
    <el-alert v-if="error" :title="error" type="error" :closable="false" class="notice" />
    <div v-if="metadata" class="metadata-grid">
      <div class="metadata-card">
        <span>发布时间完整率</span>
        <strong>{{ formatRate(metadata.summary.published_at_rate) }}</strong>
        <small>{{ metadata.summary.published_at_count }} / {{ metadata.summary.total }}</small>
      </div>
      <div class="metadata-card">
        <span>公开 IP 属地完整率</span>
        <strong>{{ formatRate(metadata.summary.ip_location_rate) }}</strong>
        <small>{{ metadata.summary.ip_location_count }} / {{ metadata.summary.total }}</small>
      </div>
      <div class="metadata-card">
        <span>用户填写地区完整率</span>
        <strong>{{ formatRate(metadata.summary.profile_region_rate) }}</strong>
        <small>{{ metadata.summary.profile_region_count }} / {{ metadata.summary.total }}</small>
      </div>
    </div>
    <el-alert
      v-if="metadata"
      type="info"
      :closable="false"
      class="notice"
      :title="`缺失原因｜发布时间：${summarizeReasons(metadata.failure_reasons.published_at)}｜IP 属地：${summarizeReasons(metadata.failure_reasons.ip_location)}｜用户填写地区：${summarizeReasons(metadata.failure_reasons.profile_region)}`"
    />
    <div class="panel">
      <div class="filters">
        <el-select v-model="filters.source" clearable placeholder="全部来源" @change="applyFilters">
          <el-option
            v-for="source in sources"
            :key="source.id"
            :label="source.name"
            :value="source.id"
          />
        </el-select>
        <el-select
          v-model="filters.source_region"
          clearable
          placeholder="来源地域"
          @change="applyFilters"
          ><el-option
            v-for="region in facets.regions"
            :key="region.source_region"
            :label="`${region.source_region} (${region.count})`"
            :value="region.source_region" /><el-option label="未知地域" value="__UNKNOWN__"
        /></el-select>
        <el-select
          v-if="facets.ratings.length"
          v-model="filters.rating"
          clearable
          placeholder="原始评分"
          @change="applyFilters"
          ><el-option
            v-for="item in facets.ratings"
            :key="item.rating"
            :label="`${item.rating} 分 (${item.count})`"
            :value="Number(item.rating)"
        /></el-select>
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

      <el-table
        v-loading="loading"
        :data="reviews"
        empty-text="暂无反馈记录"
        @row-click="selected = $event"
      >
        <el-table-column prop="source_name" label="来源" width="120" />
        <el-table-column prop="product_name" label="产品" width="150" />
        <el-table-column label="IP 属地" width="130"
          ><template #default="{ row }">{{
            row.ip_location || '未提供'
          }}</template></el-table-column
        >
        <el-table-column label="用户填写地区" width="140"
          ><template #default="{ row }">{{
            row.profile_region || '未提供'
          }}</template></el-table-column
        >
        <el-table-column prop="record_type" label="类型" width="130" />
        <el-table-column prop="content" label="内容" min-width="300" show-overflow-tooltip />
        <el-table-column label="原始评分" width="100"
          ><template #default="{ row }">{{
            row.rating == null ? '未提供' : row.rating
          }}</template></el-table-column
        >
        <el-table-column label="角色" width="90">
          <template #default="{ row }: { row: ReviewRecord }">
            <el-tag :type="row.is_official ? 'warning' : 'info'">{{ row.author_role }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="发布时间" min-width="170"
          ><template #default="{ row }">{{
            row.published_at || '未提供'
          }}</template></el-table-column
        >
        <el-table-column prop="collected_at" label="采集时间" min-width="170" />
      </el-table>

      <el-pagination
        v-model:current-page="filters.page"
        v-model:page-size="filters.page_size"
        class="pagination"
        layout="total, prev, pager, next"
        :total="total"
        @current-change="loadReviews"
      />
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
          <el-descriptions-item label="公开 IP 属地">{{
            selected.ip_location || '未提供'
          }}</el-descriptions-item>
          <el-descriptions-item label="用户填写地区">{{
            selected.profile_region || '未提供'
          }}</el-descriptions-item>
          <el-descriptions-item label="地域依据">{{
            selected.region_evidence || '未提供'
          }}</el-descriptions-item>
          <el-descriptions-item label="产品">{{ selected.product_name }}</el-descriptions-item>
          <el-descriptions-item label="类型">{{ selected.record_type }}</el-descriptions-item>
          <el-descriptions-item label="评分">{{
            selected.rating ?? '未提供'
          }}</el-descriptions-item>
          <el-descriptions-item label="标题">{{ selected.title || '—' }}</el-descriptions-item>
          <el-descriptions-item label="内容">{{ selected.content }}</el-descriptions-item>
          <el-descriptions-item label="发布时间">{{
            selected.published_at || '—'
          }}</el-descriptions-item>
          <el-descriptions-item label="采集时间">{{ selected.collected_at }}</el-descriptions-item>
          <el-descriptions-item label="软件版本">{{
            selected.software_version || '未提供'
          }}</el-descriptions-item>
          <el-descriptions-item label="角色">{{ selected.author_role }}</el-descriptions-item>
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

.metadata-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 12px;
}

.metadata-card {
  display: grid;
  gap: 6px;
  padding: 16px 18px;
  border: 1px solid var(--el-border-color-light);
  border-radius: 10px;
  background: var(--el-bg-color);
}

.metadata-card span,
.metadata-card small {
  color: var(--el-text-color-secondary);
}

.metadata-card strong {
  color: var(--el-text-color-primary);
  font-size: 24px;
}

.filters {
  display: grid;
  grid-template-columns: repeat(6, minmax(120px, 1fr));
  gap: 12px;
  margin-bottom: 18px;
}

pre {
  margin: 0;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}

.pagination {
  justify-content: flex-end;
  margin-top: 18px;
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
