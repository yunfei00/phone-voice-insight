<script setup lang="ts">
import { ChatDotRound, Clock, Link, Search, Star, View } from '@element-plus/icons-vue'
import { computed, onMounted, reactive, ref } from 'vue'

import HighlightText from '@/components/HighlightText.vue'
import ReplyTreeNode from '@/components/ReplyTreeNode.vue'
import { getProducts, getSources, getThreadTree, getThreadTrees } from '@/api'
import type { DataSource, Product, ThreadDetail, ThreadSummary } from '@/types/api'
import {
  buildThreadQuery,
  type ThreadFilters,
  type TimeBasis,
  type TimePreset,
} from '@/views/thread-query'

const threads = ref<ThreadSummary[]>([])
const products = ref<Product[]>([])
const sources = ref<DataSource[]>([])
const loading = ref(false)
const detailLoading = ref(false)
const error = ref('')
const total = ref(0)
const totalThreads = ref(0)
const matchedReplyCount = ref(0)
const detail = ref<ThreadDetail | null>(null)
const drawerVisible = ref(false)
const customRange = ref<[Date, Date] | null>(null)
const filters = reactive<ThreadFilters>({
  page: 1,
  page_size: 12,
  product: undefined as number | undefined,
  source: undefined as number | undefined,
  search: '',
  timePreset: 'all' as TimePreset,
  timeBasis: 'activity' as TimeBasis,
  ordering: 'latest_reply',
})

const appliedSearch = ref('')
const resultSummary = computed(() => {
  if (appliedSearch.value) {
    return `“${appliedSearch.value}”相关帖子 ${total.value.toLocaleString()} 个，命中回复 ${matchedReplyCount.value.toLocaleString()} 条`
  }
  if (total.value === totalThreads.value) return `共 ${totalThreads.value.toLocaleString()} 个帖子`
  return `共 ${totalThreads.value.toLocaleString()} 个帖子，本次筛选 ${total.value.toLocaleString()} 个`
})

function formatDate(value: string | null): string {
  if (!value) return '暂无'
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(new Date(value))
}

function formatCount(value: number | null): string {
  return value === null ? '—' : value.toLocaleString('zh-CN')
}

function buildParams(): Record<string, string | number | undefined> {
  return buildThreadQuery(filters, customRange.value)
}

async function loadThreads(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    const response = await getThreadTrees(buildParams())
    threads.value = response.results
    total.value = response.count
    totalThreads.value = response.total_threads
    matchedReplyCount.value = response.matched_reply_count
    appliedSearch.value = filters.search.trim()
  } catch {
    error.value = '帖子数据加载失败，请稍后重试。'
  } finally {
    loading.value = false
  }
}

function applyFilters(): void {
  filters.page = 1
  void loadThreads()
}

function handleTimePresetChange(): void {
  if (filters.timePreset !== 'custom') customRange.value = null
  applyFilters()
}

async function openThread(thread: ThreadSummary): Promise<void> {
  drawerVisible.value = true
  detail.value = null
  detailLoading.value = true
  try {
    detail.value = await getThreadTree(thread.id)
  } catch {
    drawerVisible.value = false
  } finally {
    detailLoading.value = false
  }
}

onMounted(async () => {
  try {
    const [productPage, sourcePage] = await Promise.all([
      getProducts({ page_size: 100 }),
      getSources({ page_size: 100 }),
    ])
    products.value = productPage.results
    sources.value = sourcePage.results
  } finally {
    await loadThreads()
  }
})
</script>

<template>
  <div class="threads-page">
    <div class="page-header">
      <div>
        <h1 class="page-title">帖子视图</h1>
        <p class="page-description">从帖子和完整回复脉络中，快速查看用户正在讨论什么。</p>
      </div>
      <div class="result-summary">{{ resultSummary }}</div>
    </div>

    <section class="filter-panel">
      <div class="filter-row">
        <el-select
          v-model="filters.product"
          clearable
          placeholder="全部手机产品"
          @change="applyFilters"
        >
          <el-option
            v-for="product in products"
            :key="product.id"
            :label="product.name"
            :value="product.id"
          />
        </el-select>
        <el-select
          v-model="filters.source"
          clearable
          placeholder="全部数据来源"
          @change="applyFilters"
        >
          <el-option
            v-for="source in sources"
            :key="source.id"
            :label="source.name"
            :value="source.id"
          />
        </el-select>
        <el-select
          v-model="filters.timePreset"
          aria-label="时间范围"
          @change="handleTimePresetChange"
        >
          <el-option label="全部时间" value="all" />
          <el-option label="今天" value="today" />
          <el-option label="最近 3 天" value="3d" />
          <el-option label="最近 7 天" value="7d" />
          <el-option label="最近 30 天" value="30d" />
          <el-option label="自定义" value="custom" />
        </el-select>
        <el-select v-model="filters.timeBasis" aria-label="时间依据" @change="applyFilters">
          <el-option label="最新活跃" value="activity" />
          <el-option label="发布时间" value="published" />
        </el-select>
        <el-date-picker
          v-if="filters.timePreset === 'custom'"
          v-model="customRange"
          type="daterange"
          unlink-panels
          range-separator="至"
          start-placeholder="开始日期"
          end-placeholder="结束日期"
          @change="applyFilters"
        />
      </div>
      <div class="search-row">
        <el-input
          v-model="filters.search"
          class="thread-search"
          size="large"
          clearable
          placeholder="搜索帖子和回复，例如：信号、导航、续航、发热"
          @keyup.enter="applyFilters"
          @clear="applyFilters"
        >
          <template #prefix
            ><el-icon><Search /></el-icon
          ></template>
          <template #append
            ><el-button type="primary" @click="applyFilters">搜索</el-button></template
          >
        </el-input>
        <div class="ordering">
          <span>排序</span>
          <el-select v-model="filters.ordering" aria-label="排序" @change="applyFilters">
            <el-option label="最新回复" value="latest_reply" />
            <el-option label="最新帖子" value="latest_thread" />
            <el-option label="评论最多" value="reply_count" />
            <el-option label="浏览最多" value="view_count" />
            <el-option label="点赞最多" value="like_count" />
          </el-select>
        </div>
      </div>
    </section>

    <el-alert v-if="error" :title="error" type="error" :closable="false" class="notice" show-icon>
      <template #default
        ><el-button text type="primary" @click="loadThreads">重新加载</el-button></template
      >
    </el-alert>

    <div v-loading="loading" class="thread-list" data-testid="thread-list">
      <article v-for="thread in threads" :key="thread.id" class="thread-card">
        <div class="card-heading">
          <h2><HighlightText :text="thread.title || '无标题帖子'" :keyword="appliedSearch" /></h2>
          <a
            v-if="thread.source_url"
            :href="thread.source_url"
            target="_blank"
            rel="noreferrer"
            class="source-link"
            title="查看原帖"
          >
            <el-icon><Link /></el-icon>
          </a>
        </div>
        <p class="thread-content">
          <HighlightText :text="thread.content || '（帖子无正文）'" :keyword="appliedSearch" />
        </p>
        <div v-if="appliedSearch" class="match-reasons">
          <el-tag v-if="thread.thread_match" type="primary" effect="plain" size="small"
            >命中：帖子</el-tag
          >
          <el-tag v-if="thread.reply_match_count" type="success" effect="plain" size="small"
            >回复命中 {{ thread.reply_match_count }}</el-tag
          >
        </div>
        <div class="time-row">
          <span
            ><el-icon><Clock /></el-icon>发布时间 {{ formatDate(thread.published_at) }}</span
          >
          <span>最新回复 {{ formatDate(thread.latest_reply_at) }}</span>
        </div>
        <div class="card-footer">
          <div class="metrics">
            <span title="来源回复数 / 已采集回复数"
              ><el-icon><ChatDotRound /></el-icon>{{ formatCount(thread.reply_count) }}
              <small>来源</small><b>{{ thread.collected_reply_count.toLocaleString() }}</b>
              <small>已采集</small></span
            >
            <span
              ><el-icon><View /></el-icon>{{ formatCount(thread.view_count) }}</span
            >
            <span
              ><el-icon><Star /></el-icon>{{ formatCount(thread.like_count) }}</span
            >
          </div>
          <div class="card-actions">
            <span class="source-product">{{ thread.source_name }} · {{ thread.product_name }}</span>
            <el-button type="primary" plain @click="openThread(thread)"
              >展开 {{ thread.collected_reply_count }} 条回复</el-button
            >
          </div>
        </div>
      </article>

      <el-empty v-if="!loading && !threads.length && !error" description="没有找到符合条件的帖子" />
    </div>

    <el-pagination
      v-if="total > filters.page_size"
      v-model:current-page="filters.page"
      v-model:page-size="filters.page_size"
      class="pagination"
      layout="total, prev, pager, next"
      :total="total"
      @current-change="loadThreads"
    />

    <el-drawer
      v-model="drawerVisible"
      size="min(760px, 96vw)"
      destroy-on-close
      class="thread-drawer"
    >
      <template #header><span class="drawer-title">帖子与回复</span></template>
      <div v-loading="detailLoading" class="drawer-body">
        <template v-if="detail">
          <section class="drawer-thread">
            <div class="drawer-thread-heading">
              <h2>
                <HighlightText
                  :text="detail.thread.title || '无标题帖子'"
                  :keyword="appliedSearch"
                />
              </h2>
              <a
                v-if="detail.thread.source_url"
                :href="detail.thread.source_url"
                target="_blank"
                rel="noreferrer"
                >查看原帖 <el-icon><Link /></el-icon
              ></a>
            </div>
            <p>
              <HighlightText
                :text="detail.thread.content || '（帖子无正文）'"
                :keyword="appliedSearch"
              />
            </p>
            <div class="drawer-stats">
              <span>发布 {{ formatDate(detail.thread.published_at) }}</span>
              <span>回复 {{ formatCount(detail.thread.reply_count) }}</span>
              <span>已采集 {{ detail.thread.collected_reply_count }}</span>
              <span>浏览 {{ formatCount(detail.thread.view_count) }}</span>
              <span>点赞 {{ formatCount(detail.thread.like_count) }}</span>
            </div>
          </section>
          <div class="reply-heading">
            <h3>回复树</h3>
            <span>{{ detail.thread.collected_reply_count }} 条已采集回复</span>
          </div>
          <div v-if="detail.replies.length" class="reply-tree">
            <ReplyTreeNode
              v-for="reply in detail.replies"
              :key="reply.id"
              :reply="reply"
              :keyword="appliedSearch"
            />
          </div>
          <el-empty v-else description="该帖子暂无已采集回复" />
        </template>
      </div>
    </el-drawer>
  </div>
</template>

<style scoped>
.threads-page {
  max-width: 1240px;
  margin: 0 auto;
}
.result-summary {
  padding: 10px 14px;
  color: #3e5876;
  font-size: 14px;
  background: #eef4fb;
  border-radius: 9px;
}
.filter-panel {
  padding: 18px;
  margin-bottom: 20px;
  background: #fff;
  border: 1px solid #e4e9f1;
  border-radius: 14px;
  box-shadow: 0 4px 16px rgb(31 42 68 / 4%);
}
.filter-row {
  display: grid;
  grid-template-columns: repeat(4, minmax(150px, 1fr));
  gap: 12px;
}
.filter-row :deep(.el-date-editor) {
  width: 100%;
}
.search-row {
  display: flex;
  gap: 16px;
  margin-top: 14px;
}
.thread-search {
  flex: 1;
}
.ordering {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #687386;
  font-size: 13px;
}
.ordering .el-select {
  width: 138px;
}
.notice {
  margin-bottom: 16px;
}
.thread-list {
  min-height: 240px;
  display: grid;
  gap: 16px;
}
.thread-card {
  padding: 22px 24px;
  background: #fff;
  border: 1px solid #e4e9f1;
  border-radius: 14px;
  box-shadow: 0 5px 18px rgb(31 42 68 / 5%);
  transition:
    transform 0.18s ease,
    box-shadow 0.18s ease,
    border-color 0.18s ease;
}
.thread-card:hover {
  border-color: #cbd8e9;
  box-shadow: 0 10px 28px rgb(31 42 68 / 9%);
  transform: translateY(-2px);
}
.card-heading,
.drawer-thread-heading {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}
.card-heading h2,
.drawer-thread h2 {
  flex: 1;
  margin: 0;
  color: #1c2940;
  font-size: 18px;
  line-height: 1.45;
}
.source-link {
  display: grid;
  width: 34px;
  height: 34px;
  flex: 0 0 auto;
  place-items: center;
  color: #4779ad;
  background: #f1f6fb;
  border-radius: 9px;
}
.thread-content {
  display: -webkit-box;
  margin: 12px 0 0;
  overflow: hidden;
  color: #596579;
  line-height: 1.75;
  overflow-wrap: anywhere;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 3;
}
.match-reasons {
  display: flex;
  gap: 8px;
  margin-top: 12px;
}
.time-row {
  display: flex;
  flex-wrap: wrap;
  gap: 18px;
  margin-top: 16px;
  color: #8993a5;
  font-size: 12px;
}
.time-row span {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}
.card-footer {
  display: flex;
  align-items: end;
  justify-content: space-between;
  gap: 18px;
  padding-top: 16px;
  margin-top: 16px;
  border-top: 1px solid #edf0f5;
}
.metrics {
  display: flex;
  flex-wrap: wrap;
  gap: 18px;
}
.metrics span {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: #455268;
  font-weight: 600;
}
.metrics .el-icon {
  color: #7088a5;
  font-size: 18px;
}
.metrics small {
  color: #9099a9;
  font-size: 11px;
  font-weight: 400;
}
.metrics b {
  color: #2c6da8;
  font-size: 13px;
}
.card-actions {
  display: flex;
  align-items: center;
  gap: 14px;
}
.source-product {
  color: #7a8495;
  font-size: 13px;
  white-space: nowrap;
}
.pagination {
  justify-content: flex-end;
  margin-top: 20px;
}
.drawer-title {
  color: #26364d;
  font-size: 18px;
  font-weight: 700;
}
.drawer-body {
  min-height: 260px;
}
.drawer-thread {
  padding: 18px;
  background: #f7f9fc;
  border: 1px solid #e7ecf3;
  border-radius: 12px;
}
.drawer-thread-heading a {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: #3974ad;
  font-size: 13px;
  white-space: nowrap;
}
.drawer-thread p {
  margin: 12px 0;
  color: #4f5d72;
  line-height: 1.75;
  white-space: pre-wrap;
}
.drawer-stats {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 16px;
  color: #7c8798;
  font-size: 12px;
}
.reply-heading {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin: 22px 0 8px;
}
.reply-heading h3 {
  margin: 0;
  color: #26364d;
}
.reply-heading span {
  color: #8993a5;
  font-size: 12px;
}
.reply-tree {
  display: grid;
  gap: 14px;
}

@media (max-width: 900px) {
  .filter-row {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .card-footer {
    align-items: flex-start;
    flex-direction: column;
  }
  .card-actions {
    width: 100%;
    justify-content: space-between;
  }
}

@media (max-width: 540px) {
  .filter-panel {
    padding: 14px;
  }
  .filter-row {
    grid-template-columns: 1fr;
  }
  .search-row {
    flex-direction: column;
  }
  .ordering {
    justify-content: space-between;
  }
  .ordering .el-select {
    flex: 1;
  }
  .thread-card {
    padding: 18px 16px;
  }
  .card-heading h2 {
    font-size: 17px;
  }
  .time-row {
    gap: 7px;
    flex-direction: column;
  }
  .card-actions {
    align-items: stretch;
    flex-direction: column;
  }
  .source-product {
    white-space: normal;
  }
  .card-actions .el-button {
    width: 100%;
    margin: 0;
  }
  .result-summary {
    width: 100%;
  }
  .pagination {
    overflow-x: auto;
    justify-content: flex-start;
  }
}
</style>
