<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { getDataQualitySummary, getReviewQualities } from '@/api'
import type { DataQualitySummary, ExclusionReason, ReviewQuality } from '@/types/api'

const emptySummary = (): DataQualitySummary => ({
  total: 0,
  eligible: 0,
  excluded: 0,
  eligibility_rate: 0,
  categories: {
    official: 0,
    low_information: 0,
    promotional: 0,
    noise: 0,
    duplicate: 0,
    product_not_matched: 0,
    empty: 0,
  },
  exclusion_reasons: {
    NONE: 0,
    EMPTY_CONTENT: 0,
    OFFICIAL_CONTENT: 0,
    PRODUCT_NOT_MATCHED: 0,
    PAGE_NOISE: 0,
    PROMOTIONAL: 0,
    LOW_INFORMATION: 0,
    DUPLICATE: 0,
    INVALID_ENCODING: 0,
    PARSER_ARTIFACT: 0,
    OTHER: 0,
  },
})

const rows = ref<ReviewQuality[]>([])
const summary = ref<DataQualitySummary>(emptySummary())
const loading = ref(false)
const error = ref('')
const total = ref(0)
const page = ref(1)
const selected = ref<ReviewQuality | null>(null)
const filters = reactive({
  eligible: '',
  exclusion_reason: '',
  record_type: '',
  author_role: '',
  quality_score_min: undefined as number | undefined,
  quality_score_max: undefined as number | undefined,
})

const reasonLabels: Record<ExclusionReason, string> = {
  NONE: '不排除',
  EMPTY_CONTENT: '空文本',
  OFFICIAL_CONTENT: '官方内容',
  PRODUCT_NOT_MATCHED: '产品不相关',
  PAGE_NOISE: '页面噪声',
  PROMOTIONAL: '宣传内容',
  LOW_INFORMATION: '低信息',
  DUPLICATE: '重复',
  INVALID_ENCODING: '编码异常',
  PARSER_ARTIFACT: '解析残留',
  OTHER: '其他',
}

const breakdown = computed(
  () =>
    [
      ['官方回复', summary.value.categories.official],
      ['低信息', summary.value.categories.low_information],
      ['宣传内容', summary.value.categories.promotional],
      ['页面噪声', summary.value.categories.noise],
      ['重复', summary.value.categories.duplicate],
      ['不相关', summary.value.categories.product_not_matched],
      ['空文本', summary.value.categories.empty],
    ] as const,
)

function queryParams(): Record<string, string | number | boolean | undefined> {
  return {
    page: page.value,
    page_size: 20,
    eligible: filters.eligible || undefined,
    exclusion_reason: filters.exclusion_reason || undefined,
    record_type: filters.record_type || undefined,
    author_role: filters.author_role || undefined,
    quality_score_min: filters.quality_score_min,
    quality_score_max: filters.quality_score_max,
    ordering: '-processed_at',
  }
}

async function loadData(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    const [qualityPage, qualitySummary] = await Promise.all([
      getReviewQualities(queryParams()),
      getDataQualitySummary(),
    ])
    rows.value = qualityPage.results
    total.value = qualityPage.count
    summary.value = qualitySummary
  } catch {
    error.value = '数据质量结果加载失败，请先运行治理 Pipeline。'
  } finally {
    loading.value = false
  }
}

function applyFilters(): void {
  page.value = 1
  void loadData()
}

function ratio(value: number): string {
  return summary.value.total ? `${((value / summary.value.total) * 100).toFixed(1)}%` : '0.0%'
}

onMounted(loadData)
</script>

<template>
  <div>
    <div class="page-header">
      <div>
        <h1 class="page-title">数据质量</h1>
        <p class="page-description">治理结果独立于原始反馈；质量分表示语料适用性，不是手机评分。</p>
      </div>
      <el-button :loading="loading" @click="loadData">刷新</el-button>
    </div>

    <el-alert v-if="error" :title="error" type="error" :closable="false" class="notice" />

    <div class="metric-grid">
      <div class="metric-card">
        <span>原始反馈总数</span><strong>{{ summary.total }}</strong>
      </div>
      <div class="metric-card">
        <span>AI 可用语料数</span><strong>{{ summary.eligible }}</strong>
      </div>
      <div class="metric-card">
        <span>排除数量</span><strong>{{ summary.excluded }}</strong>
      </div>
      <div class="metric-card">
        <span>可用率</span><strong>{{ (summary.eligibility_rate * 100).toFixed(1) }}%</strong>
      </div>
    </div>

    <section class="panel breakdown">
      <div v-for="item in breakdown" :key="item[0]">
        <span>{{ item[0] }}</span
        ><strong>{{ item[1] }}</strong
        ><small>{{ ratio(item[1]) }}</small>
      </div>
    </section>

    <section class="panel filters">
      <el-select v-model="filters.eligible" placeholder="AI 可用" clearable>
        <el-option label="可用" value="true" />
        <el-option label="排除" value="false" />
      </el-select>
      <el-select v-model="filters.exclusion_reason" placeholder="排除原因" clearable>
        <el-option
          v-for="(label, value) in reasonLabels"
          :key="value"
          :label="label"
          :value="value"
        />
      </el-select>
      <el-select v-model="filters.record_type" placeholder="记录类型" clearable>
        <el-option label="帖子" value="THREAD" />
        <el-option label="回复" value="REPLY" />
        <el-option label="官方回复" value="OFFICIAL_REPLY" />
      </el-select>
      <el-select v-model="filters.author_role" placeholder="作者角色" clearable>
        <el-option label="用户" value="USER" />
        <el-option label="官方" value="OFFICIAL" />
        <el-option label="版主" value="MODERATOR" />
        <el-option label="达人" value="EXPERT" />
      </el-select>
      <el-input-number
        v-model="filters.quality_score_min"
        :min="0"
        :max="1"
        :step="0.1"
        placeholder="最低分"
      />
      <el-input-number
        v-model="filters.quality_score_max"
        :min="0"
        :max="1"
        :step="0.1"
        placeholder="最高分"
      />
      <el-button type="primary" @click="applyFilters">筛选</el-button>
    </section>

    <section class="panel table-panel">
      <el-table
        v-loading="loading"
        :data="rows"
        empty-text="暂无治理结果"
        @row-click="selected = $event"
      >
        <el-table-column prop="review_id" label="ID" width="80" />
        <el-table-column prop="record_type" label="类型" width="120" />
        <el-table-column
          prop="normalized_text"
          label="正文摘要"
          min-width="300"
          show-overflow-tooltip
        />
        <el-table-column prop="author_role" label="角色" width="110" />
        <el-table-column label="AI 可用" width="100">
          <template #default="{ row }: { row: ReviewQuality }">
            <el-tag :type="row.eligible_for_ai ? 'success' : 'info'">{{
              row.eligible_for_ai ? '是' : '否'
            }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="排除原因" width="140">
          <template #default="{ row }: { row: ReviewQuality }">{{
            reasonLabels[row.exclusion_reason]
          }}</template>
        </el-table-column>
        <el-table-column prop="quality_score" label="质量分" width="90" />
        <el-table-column prop="published_at" label="发布时间" min-width="180" />
      </el-table>
      <el-pagination
        v-model:current-page="page"
        :page-size="20"
        :total="total"
        layout="prev, pager, next, total"
        @current-change="loadData"
      />
    </section>

    <el-drawer
      :model-value="Boolean(selected)"
      title="治理结果详情"
      size="min(760px, 94vw)"
      @close="selected = null"
    >
      <el-descriptions v-if="selected" :column="1" border>
        <el-descriptions-item label="原始内容">
          <pre>{{ selected.original_content }}</pre>
        </el-descriptions-item>
        <el-descriptions-item label="标准化文本">
          <pre>{{ selected.normalized_text }}</pre>
        </el-descriptions-item>
        <el-descriptions-item label="上下文">
          <pre>{{ selected.context_text }}</pre>
        </el-descriptions-item>
        <el-descriptions-item label="规则标记">
          <pre>{{ JSON.stringify(selected.flags_json, null, 2) }}</pre>
        </el-descriptions-item>
        <el-descriptions-item label="人工覆盖">{{
          selected.manual_override ? selected.manual_reason : '无'
        }}</el-descriptions-item>
      </el-descriptions>
    </el-drawer>
  </div>
</template>

<style scoped>
.notice,
.breakdown,
.filters,
.table-panel {
  margin-bottom: 18px;
}

.metric-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
  margin-bottom: 18px;
}

.metric-card,
.breakdown > div {
  padding: 18px;
  background: #fff;
  border: 1px solid #e7eaf0;
  border-radius: 12px;
}

.metric-card span,
.breakdown span,
.breakdown small {
  display: block;
  color: #6b7280;
}

.metric-card strong {
  display: block;
  margin-top: 10px;
  font-size: 28px;
}

.breakdown {
  display: grid;
  grid-template-columns: repeat(7, minmax(0, 1fr));
  gap: 10px;
}

.breakdown > div {
  padding: 12px;
}

.breakdown strong {
  display: block;
  margin: 6px 0;
  font-size: 20px;
}

.filters {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.filters .el-select {
  width: 160px;
}

.table-panel .el-pagination {
  justify-content: flex-end;
  margin-top: 16px;
}

pre {
  max-height: 300px;
  margin: 0;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
}

@media (max-width: 1000px) {
  .metric-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .breakdown {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}
</style>
