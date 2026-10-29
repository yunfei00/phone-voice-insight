<script setup lang="ts">
import { Search } from '@element-plus/icons-vue'
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { getDashboardIssue, getDashboardIssues, getTaxonomy } from '@/api'
import DashboardFilters from '@/components/DashboardFilters.vue'
import type {
  DashboardFilters as FilterValues,
  DashboardIssue,
  DashboardIssueDetail,
  TaxonomyTag,
} from '@/types/api'

const route = useRoute()
const router = useRouter()
const filters = ref<FilterValues>({
  product_id: route.query.product_id ? Number(route.query.product_id) : undefined,
  source_id: route.query.source_id ? Number(route.query.source_id) : undefined,
  start_date: String(route.query.start_date || ''),
  end_date: String(route.query.end_date || ''),
})
const search = ref(String(route.query.search || ''))
const category = ref(String(route.query.category || ''))
const severity = ref('')
const ordering = ref('-feedback_count')
const domains = ref<TaxonomyTag[]>([])
const rows = ref<DashboardIssue[]>([])
const total = ref(0)
const page = ref(1)
const loading = ref(false)
const error = ref('')
const drawer = ref(false)
const detail = ref<DashboardIssueDetail>()
const detailLoading = ref(false)
const severityLabels: Record<string, string> = {
  CRITICAL: '严重', HIGH: '高', MEDIUM: '中', LOW: '低', INFO: '提示',
}
function severityLabel(value: string): string {
  return severityLabels[value] || value
}
function findTaxonomyName(code: string, tags: TaxonomyTag[]): string | undefined {
  for (const tag of tags) {
    if (tag.tag_id === code) return tag.name
    const child = findTaxonomyName(code, tag.children || [])
    if (child) return child
  }
  return undefined
}
function categoryLabel(code: string): string {
  return findTaxonomyName(code, domains.value) || code
}

async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    const data = await getDashboardIssues({
      ...filters.value,
      search: search.value || undefined,
      category: category.value || undefined,
      severity: severity.value || undefined,
      ordering: ordering.value,
      page: page.value,
      page_size: 10,
    })
    rows.value = data.results
    total.value = data.count
    await router.replace({
      query: {
        ...filters.value,
        search: search.value || undefined,
        category: category.value || undefined,
      },
    })
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '问题列表加载失败'
  } finally {
    loading.value = false
  }
}
async function openIssue(item: DashboardIssue): Promise<void> {
  drawer.value = true
  detailLoading.value = true
  try {
    detail.value = await getDashboardIssue(item.id, filters.value)
  } finally {
    detailLoading.value = false
  }
}
function format(value: string | null): string {
  return value ? new Date(value).toLocaleString('zh-CN') : '暂无'
}
onMounted(async () => {
  domains.value = (await getTaxonomy()).domains
  await load()
})
</script>

<template>
  <div class="dashboard-page">
    <div class="page-header">
      <div>
        <p class="eyebrow">问题洞察</p>
        <h1 class="page-title">用户问题洞察</h1>
        <p class="page-description">仅展示治理 ACCEPTED 且通过结构化证据校验的明确问题</p>
      </div>
    </div>
    <section class="tech-panel filters">
      <DashboardFilters
        v-model="filters"
        @change="
          () => {
            page = 1
            load()
          }
        "
      />
      <div class="issue-filters">
        <el-select v-model="category" clearable placeholder="一级分类" @change="load"
          ><el-option
            v-for="item in domains"
            :key="item.tag_id"
            :label="item.name"
            :value="item.tag_id" /></el-select
        ><el-select v-model="severity" clearable placeholder="严重程度" @change="load"
          ><el-option
            v-for="item in ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO']"
            :key="item"
            :label="severityLabel(item)"
            :value="item" /></el-select
        ><el-select v-model="ordering" @change="load"
          ><el-option label="反馈最多" value="-feedback_count" /><el-option
            label="最近出现"
            value="-last_seen" /><el-option label="近 7 天最多" value="-recent_count" /><el-option
            label="严重程度"
            value="-severity" /></el-select
        ><el-input
          v-model="search"
          :prefix-icon="Search"
          clearable
          placeholder="搜索问题关键词"
          @keyup.enter="load"
        /><el-button type="primary" @click="load">搜索</el-button>
      </div>
    </section>
    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />
    <section class="tech-panel issue-table" v-loading="loading">
      <el-table :data="rows" empty-text="当前筛选范围暂无明确问题"
        ><el-table-column prop="name" label="问题名称" min-width="170" /><el-table-column
          prop="product_name"
          label="产品"
          min-width="130"
        /><el-table-column label="分类" min-width="150"><template #default="{ row }">{{ categoryLabel(row.topic_code) }}</template></el-table-column><el-table-column
          prop="feedback_count"
          label="关联反馈"
          width="95"
        /><el-table-column prop="recent_count" label="近 7 天" width="90" /><el-table-column
          label="环比"
          width="90"
          ><template #default="{ row }">{{
            row.is_new ? '新出现' : row.growth_rate === null ? '—' : `${row.growth_rate}%`
          }}</template></el-table-column
        ><el-table-column label="严重度" width="100"
          ><template #default="{ row }"
            ><el-tag
              :type="row.severity === 'CRITICAL' || row.severity === 'HIGH' ? 'danger' : 'warning'"
              effect="dark"
              >{{ severityLabel(row.severity) }}</el-tag
            ></template
          ></el-table-column
        ><el-table-column label="最近出现" min-width="160"
          ><template #default="{ row }">{{ format(row.last_seen) }}</template></el-table-column
        ><el-table-column label="操作" width="100"
          ><template #default="{ row }"
            ><el-button text type="primary" @click="openIssue(row)">查看证据</el-button></template
          ></el-table-column
        ></el-table
      ><el-pagination
        v-if="total"
        v-model:current-page="page"
        :page-size="10"
        :total="total"
        layout="prev, pager, next, total"
        @current-change="load"
      />
    </section>
    <el-drawer v-model="drawer" size="min(720px, 94vw)" class="issue-drawer"
      ><template #header
        ><div>
          <small>问题证据</small>
          <h2>{{ detail?.name || '问题详情' }}</h2>
        </div></template
      >
      <div v-loading="detailLoading" class="detail">
        <template v-if="detail"
          ><p class="summary">{{ detail.summary }}</p>
          <div class="detail-metrics">
            <span
              >关联反馈<strong>{{ detail.feedback_count }}</strong></span
            ><span
              >近 7 天<strong>{{ detail.recent_count }}</strong></span
            ><span
              >严重程度<strong>{{ severityLabel(detail.severity) }}</strong></span
            ><span
              >最近出现<strong>{{ format(detail.last_seen) }}</strong></span
            >
          </div>
          <h3>典型原始证据</h3>
          <article v-for="item in detail.evidence" :key="item.id" class="evidence-card">
            <div>
              <el-tag size="small">{{ severityLabel(item.severity) }}</el-tag
              ><time>{{
                format(item.analysis__content__published_at || item.analysis__content__collected_at)
              }}</time>
            </div>
            <blockquote>{{ item.evidence_text }}</blockquote>
            <p>{{ item.analysis__content__content }}</p>
            <a
              v-if="item.analysis__content__source_url"
              :href="item.analysis__content__source_url"
              target="_blank"
              rel="noopener noreferrer"
              >打开原帖 ↗</a
            ><span v-else>原帖链接不可用，以上为已保存原始内容</span>
          </article></template
        >
      </div></el-drawer
    >
  </div>
</template>

<style scoped>
.eyebrow {
  margin: 0 0 6px;
  color: var(--pvi-blue);
  font-size: 12px;
  letter-spacing: 0.18em;
}
.tech-panel {
  padding: 18px;
  background: var(--pvi-card);
  border: 1px solid var(--pvi-border);
  border-radius: 14px;
}
.filters {
  display: grid;
  gap: 14px;
  margin-bottom: 16px;
}
.issue-filters {
  display: grid;
  grid-template-columns: 150px 150px 150px minmax(220px, 1fr) auto;
  gap: 10px;
}
.issue-table :deep(.el-table) {
  --el-table-bg-color: transparent;
  --el-table-tr-bg-color: transparent;
  --el-table-header-bg-color: #0a192a;
  --el-table-border-color: #29435c;
  --el-table-text-color: #edf5ff;
  --el-table-header-text-color: #96adc6;
}
.el-pagination {
  justify-content: flex-end;
  margin-top: 18px;
}
.detail .summary {
  padding: 14px;
  background: #0a192a;
  border-left: 3px solid var(--pvi-blue);
}
.detail-metrics {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
  margin: 16px 0;
}
.detail-metrics span {
  color: var(--pvi-muted);
  font-size: 12px;
}
.detail-metrics strong {
  display: block;
  margin-top: 7px;
  color: var(--pvi-text);
}
.evidence-card {
  padding: 16px;
  margin: 12px 0;
  background: #0a192a;
  border: 1px solid #29435c;
  border-radius: 12px;
}
.evidence-card div {
  display: flex;
  justify-content: space-between;
}
.evidence-card time,
.evidence-card span {
  color: var(--pvi-muted);
  font-size: 12px;
}
.evidence-card blockquote {
  margin: 14px 0;
  padding: 10px;
  color: var(--pvi-blue);
  background: #35b9f010;
}
.evidence-card p {
  line-height: 1.7;
}
.evidence-card a {
  color: var(--pvi-green);
}
@media (max-width: 900px) {
  .issue-filters {
    grid-template-columns: 1fr 1fr;
  }
  .detail-metrics {
    grid-template-columns: 1fr 1fr;
  }
}
@media (max-width: 560px) {
  .issue-filters {
    grid-template-columns: 1fr;
  }
}
</style>
