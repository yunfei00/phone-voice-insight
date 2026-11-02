<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{ result: Record<string, unknown> }>()

type Row = Record<string, unknown>

const overview = computed<Row | null>(() => {
  const value = props.result.overview
  return value && typeof value === 'object' ? (value as Row) : null
})
const products = computed<Row[]>(() =>
  Array.isArray(props.result.products) ? (props.result.products as Row[]) : [],
)
const posts = computed<Row[]>(() =>
  Array.isArray(props.result.posts) ? (props.result.posts as Row[]) : [],
)
const meta = computed<Row>(() =>
  props.result.meta && typeof props.result.meta === 'object' ? (props.result.meta as Row) : {},
)

function productMetric(row: Row, name: string): unknown {
  const value = row.overview
  return value && typeof value === 'object' ? (value as Row)[name] : undefined
}
</script>

<template>
  <section v-if="overview || products.length || posts.length" class="tool-result">
    <div v-if="overview" class="metric-grid">
      <div>
        <span>原始反馈</span><strong>{{ overview.raw_feedback ?? 0 }}</strong>
      </div>
      <div>
        <span>有效反馈</span><strong>{{ overview.valid_feedback ?? 0 }}</strong>
      </div>
      <div>
        <span>AI 已分析</span><strong>{{ overview.ai_analyzed ?? 0 }}</strong>
      </div>
      <div>
        <span>明确问题</span><strong>{{ overview.explicit_issue_feedback ?? 0 }}</strong>
      </div>
    </div>
    <el-table v-if="products.length" :data="products" size="small" class="compare-table">
      <el-table-column prop="product_name" label="产品" min-width="130" />
      <el-table-column label="有效反馈" width="90">
        <template #default="{ row }">{{ productMetric(row, 'valid_feedback') ?? 0 }}</template>
      </el-table-column>
      <el-table-column label="AI 已分析" width="90">
        <template #default="{ row }">{{ productMetric(row, 'ai_analyzed') ?? 0 }}</template>
      </el-table-column>
      <el-table-column label="明确问题" width="90">
        <template #default="{ row }">{{
          productMetric(row, 'explicit_issue_feedback') ?? 0
        }}</template>
      </el-table-column>
    </el-table>
    <div v-if="posts.length" class="retrieval-note">
      已检索 {{ posts.length }} 个真实帖子
      <span v-if="meta.vector_status"> · 向量检索：{{ meta.vector_status }}</span>
    </div>
    <p v-if="meta.scope_note" class="scope">统计口径：{{ meta.scope_note }}</p>
  </section>
</template>

<style scoped>
.tool-result {
  margin: 12px 0;
  padding: 12px;
  border: 1px solid #29435c;
  border-radius: 10px;
  background: #0a192a;
}
.metric-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
}
.metric-grid div {
  padding: 10px;
  border: 1px solid #29435c;
  border-radius: 8px;
  background: #12283f;
}
.metric-grid span,
.scope,
.retrieval-note {
  color: #96adc6;
  font-size: 12px;
}
.metric-grid strong {
  display: block;
  margin-top: 4px;
  color: #42d6c6;
  font-size: 20px;
}
.compare-table {
  --el-table-bg-color: #12283f;
  --el-table-tr-bg-color: #12283f;
  --el-table-header-bg-color: #0a192a;
  --el-table-text-color: #edf5ff;
  --el-table-header-text-color: #96adc6;
  --el-table-border-color: #29435c;
}
.retrieval-note,
.scope {
  margin: 9px 0 0;
}
@media (max-width: 640px) {
  .metric-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
