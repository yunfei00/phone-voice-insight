<script setup lang="ts">
import { ElMessage } from 'element-plus'
import { onMounted, reactive, ref } from 'vue'

import {
  createStructuredBatch,
  runAllStructuredAnalysis,
  getProducts,
  getStructuredAggregates,
  getStructuredAnalyses,
  getStructuredBatches,
  getStructuredQuality,
  getTaxonomy,
} from '@/api'
import HighlightText from '@/components/HighlightText.vue'
import type {
  Product,
  StructuredAggregates,
  StructuredAnalysisV1,
  StructuredBatch,
  StructuredQuality,
  TaxonomyDefinition,
} from '@/types/api'

const starting = ref(false)
const startingAll = ref(false)
const sampleSize = ref(20)
const loading = ref(false)
const error = ref('')
const items = ref<StructuredAnalysisV1[]>([])
const count = ref(0)
const taxonomy = ref<TaxonomyDefinition>()
const products = ref<Product[]>([])
const selectedProduct = ref<number>()
const quality = ref<StructuredQuality>()
const aggregates = ref<StructuredAggregates>()
const batches = ref<StructuredBatch[]>([])
const batchCount = ref(0)
const page = ref(1)
const batchPage = ref(1)
const filters = reactive({ search: '', aspect_code: '', sentiment: '' })
async function load() {
  loading.value = true
  error.value = ''
  try {
    const scope = { product: selectedProduct.value }
    const [response, qualityResult, aggregateResult, batchResult] = await Promise.all([
      getStructuredAnalyses({ ...filters, ...scope, page: page.value, page_size: 10 }),
      getStructuredQuality(scope),
      getStructuredAggregates(scope),
      getStructuredBatches({ ...scope, page: batchPage.value, page_size: 10 }),
    ])
    items.value = response.results
    count.value = response.count
    quality.value = qualityResult
    aggregates.value = aggregateResult
    batches.value = batchResult.results
    batchCount.value = batchResult.count
    taxonomy.value ||= await getTaxonomy()
  } catch {
    error.value = '结构化分析数据加载失败，请稍后重试。'
  } finally {
    loading.value = false
  }
}

async function startAll() {
  if (!selectedProduct.value || startingAll.value) return
  startingAll.value = true
  try {
    await runAllStructuredAnalysis(selectedProduct.value)
    ElMessage.success('已启动剩余语料全量分析，将自动分批执行；已完成的评论不会重复分析')
    await load()
  } catch {
    ElMessage.error('全量任务启动失败，请检查 AI 配置和 Celery Worker')
  } finally {
    startingAll.value = false
  }
}

async function startSample() {
  if (!selectedProduct.value || starting.value) return
  starting.value = true
  try {
    const result = await createStructuredBatch({
      product_id: selectedProduct.value,
      max_items: sampleSize.value,
      dry_run: false,
      max_concurrency: 1,
      requests_per_minute: 10,
    })
    ElMessage.success(
      `已提交真实分析任务 #${result.batch.id}，匹配 ${result.matched_content_ids.length} 条语料`,
    )
    await load()
  } catch (reason: unknown) {
    const detail = reason as { response?: { data?: { error_code?: string; detail?: string } } }
    const code = detail.response?.data?.error_code
    ElMessage.error(
      code === 'NO_CONTENT_MATCHED'
        ? '没有可分析的最终有效语料，请先在数据质量页面完成 AI 治理'
        : detail.response?.data?.detail || '任务创建失败，请检查 AI 配置和后台任务服务',
    )
  } finally {
    starting.value = false
  }
}

async function changeProduct() {
  page.value = 1
  batchPage.value = 1
  await load()
}

onMounted(async () => {
  try {
    products.value = (await getProducts({ page_size: 100 })).results
    selectedProduct.value = products.value[0]?.id
  } catch {
    ElMessage.warning('产品列表加载失败')
  }
  await load()
})
</script>

<template>
  <section class="page-stack">
    <header class="page-header">
      <div>
        <h1>AI 结构化分析</h1>
        <p>自动治理后的有效反馈将无人值守进入结构化分析；证据不足和技术错误不会混入问题统计。</p>
      </div>
      <el-tag effect="plain">Taxonomy {{ taxonomy?.taxonomy_version || '1.0.0' }}</el-tag>
    </header>
    <el-card shadow="never">
      <div class="filters">
        <strong>下一步：启动真实 AI 结构化分析</strong>
        <el-select v-model="selectedProduct" placeholder="先选择手机产品" @change="changeProduct">
          <el-option
            v-for="product in products"
            :key="product.id"
            :label="product.name"
            :value="product.id"
          />
        </el-select>
        <el-input-number v-model="sampleSize" :min="1" :max="1000" :step="10" />
        <el-button
          type="primary"
          :loading="starting"
          :disabled="!selectedProduct"
          @click="startSample"
        >
          开始分析（非模拟）
        </el-button>
        <el-button
          type="success"
          :loading="startingAll"
          :disabled="!selectedProduct"
          @click="startAll"
          >一键分析全部剩余数据</el-button
        >
        <el-button @click="load">刷新结果与任务进度</el-button>
      </div>
      <p>
        已完成的评论自动跳过；全量任务按每批 100 条持续执行。系统每 30
        分钟检查新增有效评论并自动分析，失败记录不会无限重试。
      </p>
    </el-card>
    <el-alert
      v-if="quality?.error_distribution?.length"
      type="warning"
      show-icon
      :closable="false"
      title="结构化分析失败原因统计（按错误码）"
    >
      <div v-for="item in quality.error_distribution" :key="item.error_code">
        {{ item.error_code || 'UNKNOWN_ERROR' }}：{{ item.count }} 条
      </div>
      <p>如全部失败，请先检查模型连通性和后端 Worker 日志，不要反复批量提交。</p>
    </el-alert>
    <div class="metric-grid">
      <el-card shadow="never"
        ><span>AI 已分析量</span><strong>{{ quality?.total_runs || 0 }}</strong></el-card
      >
      <el-card shadow="never"
        ><span>有效分析量</span><strong>{{ quality?.successful_runs || 0 }}</strong></el-card
      >
      <el-card shadow="never"
        ><span>明确问题/观点</span><strong>{{ aggregates?.opinion_count || 0 }}</strong></el-card
      >
      <el-card shadow="never"
        ><span>分析失败量</span
        ><strong>{{
          (quality?.total_runs || 0) - (quality?.successful_runs || 0)
        }}</strong></el-card
      >
    </div>
    <el-card shadow="never">
      <div class="filters">
        <el-select v-model="selectedProduct" placeholder="选择手机产品" @change="changeProduct">
          <el-option
            v-for="product in products"
            :key="product.id"
            :label="product.name"
            :value="product.id"
          />
        </el-select>
        <el-input
          v-model="filters.search"
          clearable
          placeholder="搜索原文、摘要或证据"
          @keyup.enter="load"
        />
        <el-select v-model="filters.aspect_code" clearable placeholder="一级分类">
          <el-option
            v-for="tag in taxonomy?.domains"
            :key="tag.tag_id"
            :label="`${tag.name} (${tag.tag_id})`"
            :value="tag.tag_id"
          />
        </el-select>
        <el-select v-model="filters.sentiment" clearable placeholder="情感">
          <el-option
            v-for="value in ['POSITIVE', 'NEUTRAL', 'NEGATIVE', 'MIXED', 'UNKNOWN']"
            :key="value"
            :value="value"
          />
        </el-select>
        <el-button type="primary" @click="load">查询</el-button>
      </div>
    </el-card>
    <el-alert v-if="error" :title="error" type="error" show-icon
      ><el-button text @click="load">重试</el-button></el-alert
    >
    <div v-loading="loading" class="analysis-list">
      <el-empty
        v-if="!loading && !error && !items.length"
        description="暂无结构化分析结果；自动流水线将在治理通过且预算可用时运行"
      />
      <el-card v-for="item in items" :key="item.id" class="analysis-card" shadow="hover">
        <template #header>
          <div class="card-title">
            <strong>{{ item.original_title || `反馈 #${item.content}` }}</strong
            ><span> {{ item.product_name }} · {{ item.source_name }}</span>
          </div>
        </template>
        <p class="original">{{ item.original_content }}</p>
        <p class="summary">AI 摘要：{{ item.summary || '—' }}</p>
        <div class="opinions">
          <div v-for="aspect in item.aspects" :key="aspect.id" class="opinion">
            <div>
              <el-tag>{{ aspect.aspect_code }}</el-tag
              ><el-tag effect="plain">{{ aspect.topic_code }}</el-tag
              ><el-tag
                :type="
                  aspect.sentiment === 'NEGATIVE'
                    ? 'danger'
                    : aspect.sentiment === 'POSITIVE'
                      ? 'success'
                      : 'info'
                "
                >{{ aspect.sentiment }}</el-tag
              ><el-tag type="warning" effect="plain">{{ aspect.severity }}</el-tag>
            </div>
            <p>
              <strong>证据：</strong
              ><HighlightText :text="item.original_content" :keyword="aspect.evidence_text" />
            </p>
            <small
              >置信度 {{ Number(aspect.confidence).toFixed(2) }} · {{ aspect.intent }} ·
              {{ aspect.issue_type }}</small
            >
          </div>
          <el-empty v-if="!item.aspects.length" :image-size="48" description="无相关观点" />
        </div>
        <footer>
          <span
            >{{ item.provider }} / {{ item.model }} · {{ item.prompt_version }} · Schema
            {{ item.schema_version }}</span
          >
        </footer>
      </el-card>
    </div>
    <el-pagination
      v-model:current-page="page"
      :page-size="10"
      :total="count"
      layout="prev, pager, next, total"
      @current-change="load"
    />
    <el-card shadow="never">
      <template #header><strong>高频问题与分类</strong></template>
      <div class="ranking">
        <el-tag v-for="item in aggregates?.high_frequency_clusters || []" :key="item.topic_code">
          {{ item.topic_code }} · {{ item.count }}
        </el-tag>
        <el-empty
          v-if="!aggregates?.high_frequency_clusters.length"
          :image-size="48"
          description="暂无聚合结果"
        />
      </div>
    </el-card>
    <el-card shadow="never">
      <template #header><strong>最近自动分析任务</strong></template>
      <el-table :data="batches" empty-text="暂无自动分析任务">
        <el-table-column prop="id" label="任务 ID" width="90" />
        <el-table-column prop="product_name" label="产品" />
        <el-table-column prop="status" label="状态" width="110" />
        <el-table-column label="进度"
          ><template #default="{ row }"
            >{{ row.success_count + row.failed_count + row.skipped_count }} /
            {{ row.requested_count }}</template
          ></el-table-column
        >
        <el-table-column prop="success_count" label="成功" width="85" />
        <el-table-column prop="failed_count" label="失败" width="85" />
        <el-table-column
          prop="error_message"
          label="批次错误"
          min-width="230"
          show-overflow-tooltip
        />
        <el-table-column prop="total_tokens" label="Token" width="100" />
      </el-table>
      <el-pagination
        v-model:current-page="batchPage"
        :page-size="10"
        :total="batchCount"
        layout="prev, pager, next, total"
        @current-change="load"
      />
    </el-card>
  </section>
</template>

<style scoped>
.page-stack {
  display: grid;
  gap: 18px;
}
.page-header,
.card-title,
footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}
.page-header h1 {
  margin: 0;
}
.page-header p {
  margin: 6px 0 0;
  color: #6b7280;
}
.metric-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}
.metric-grid span,
.metric-grid strong {
  display: block;
}
.metric-grid span {
  color: #6b7280;
}
.metric-grid strong {
  margin-top: 8px;
  font-size: 28px;
}
.filters {
  display: grid;
  grid-template-columns: minmax(240px, 2fr) repeat(3, minmax(140px, 1fr)) auto;
  gap: 12px;
}
.analysis-list {
  min-height: 180px;
  display: grid;
  gap: 14px;
}
.analysis-card {
  border-radius: 12px;
}
.card-title span,
footer,
small {
  color: #6b7280;
}
.original {
  white-space: pre-wrap;
}
.summary {
  padding: 10px 12px;
  background: #f7f8fb;
  border-radius: 8px;
}
.opinions {
  display: grid;
  gap: 10px;
}
.opinion {
  padding: 12px;
  border: 1px solid #e5e7eb;
  border-radius: 9px;
}
.opinion > div {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}
.opinion p {
  margin: 10px 0;
}
footer {
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px solid #eef0f3;
}
.json-editor {
  margin: 14px 0;
}
.count {
  text-align: center;
  color: #6b7280;
}
.ranking {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
@media (max-width: 900px) {
  .filters {
    grid-template-columns: 1fr;
  }
  .page-header,
  .card-title,
  footer {
    align-items: flex-start;
    flex-direction: column;
  }
  .metric-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
