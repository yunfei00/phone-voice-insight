<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { getProducts, getReviews, getSources } from '@/api'
import type { DataSource, Product, ProductVariant, ReviewRecord } from '@/types/api'

const reviews = ref<ReviewRecord[]>([])
const sources = ref<DataSource[]>([])
const products = ref<Product[]>([])
const selected = ref<ReviewRecord | null>(null)
const loading = ref(false)
const error = ref('')
const total = ref(0)
const filters = reactive({
  page: 1,
  page_size: 20,
  source: undefined as number | undefined,
  product_variant: undefined as number | undefined,
  rating: undefined as number | undefined,
  search: '',
  record_type: '',
  author_role: '',
  is_official: '' as '' | 'true' | 'false',
})

const variants = computed<ProductVariant[]>(() =>
  products.value.flatMap((product) => product.variants),
)

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
    })
    reviews.value = response.results
    total.value = response.count
  } catch {
    error.value = '原始反馈加载失败。'
  } finally {
    loading.value = false
  }
}

function applyFilters(): void {
  filters.page = 1
  void loadReviews()
}

onMounted(async () => {
  try {
    const [sourcePage, productPage] = await Promise.all([
      getSources({ page_size: 100 }),
      getProducts({ page_size: 100 }),
    ])
    sources.value = sourcePage.results
    products.value = productPage.results
  } finally {
    await loadReviews()
  }
})
</script>

<template>
  <div>
    <div class="page-header">
      <div>
        <h1 class="page-title">原始反馈</h1>
        <p class="page-description">统一查看评价、追评、帖子、回复和官方回复。</p>
      </div>
    </div>
    <el-alert v-if="error" :title="error" type="error" :closable="false" class="notice" />
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
          v-model="filters.product_variant"
          clearable
          placeholder="产品版本"
          @change="applyFilters"
        >
          <el-option
            v-for="variant in variants"
            :key="variant.id"
            :label="variant.sku_name"
            :value="variant.id"
          />
        </el-select>
        <el-select v-model="filters.rating" clearable placeholder="评分" @change="applyFilters">
          <el-option
            v-for="rating in [5, 4, 3, 2, 1, 0]"
            :key="rating"
            :label="`${rating} 星`"
            :value="rating"
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

      <el-table
        v-loading="loading"
        :data="reviews"
        empty-text="暂无反馈记录"
        @row-click="selected = $event"
      >
        <el-table-column prop="source_name" label="来源" width="120" />
        <el-table-column prop="product_name" label="产品" width="150" />
        <el-table-column prop="record_type" label="类型" width="130" />
        <el-table-column prop="variant_name" label="产品版本" min-width="170" />
        <el-table-column prop="content" label="内容" min-width="300" show-overflow-tooltip />
        <el-table-column prop="rating" label="评分" width="80" />
        <el-table-column label="角色" width="90">
          <template #default="{ row }: { row: ReviewRecord }">
            <el-tag :type="row.is_official ? 'warning' : 'info'">{{ row.author_role }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="published_at" label="发布时间" min-width="170" />
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
          <el-descriptions-item label="产品">{{ selected.product_name }}</el-descriptions-item>
          <el-descriptions-item label="类型">{{ selected.record_type }}</el-descriptions-item>
          <el-descriptions-item label="评分">{{ selected.rating || '—' }}</el-descriptions-item>
          <el-descriptions-item label="产品版本">{{
            selected.variant_name || '—'
          }}</el-descriptions-item>
          <el-descriptions-item label="标题">{{ selected.title || '—' }}</el-descriptions-item>
          <el-descriptions-item label="内容">{{ selected.content }}</el-descriptions-item>
          <el-descriptions-item label="发布时间">{{
            selected.published_at || '—'
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
