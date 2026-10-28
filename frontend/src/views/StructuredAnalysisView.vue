<script setup lang="ts">
import { ElMessage } from 'element-plus'
import { onMounted, reactive, ref } from 'vue'

import { getStructuredAnalyses, getTaxonomy, reviewStructuredAnalysis } from '@/api'
import HighlightText from '@/components/HighlightText.vue'
import type { StructuredAnalysisV1, TaxonomyDefinition } from '@/types/api'

const loading = ref(false)
const error = ref('')
const items = ref<StructuredAnalysisV1[]>([])
const count = ref(0)
const taxonomy = ref<TaxonomyDefinition>()
const filters = reactive({ search: '', aspect_code: '', sentiment: '', review_required: '' })
const reviewVisible = ref(false)
const reviewTarget = ref<StructuredAnalysisV1>()
const correctedJson = ref('')
const reviewReason = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    const response = await getStructuredAnalyses({ ...filters, page_size: 30 })
    items.value = response.results
    count.value = response.count
    taxonomy.value ||= await getTaxonomy()
  } catch {
    error.value = '结构化分析数据加载失败，请稍后重试。'
  } finally {
    loading.value = false
  }
}

function openReview(item: StructuredAnalysisV1) {
  reviewTarget.value = item
  correctedJson.value = JSON.stringify(
    {
      schema_version: item.schema_version,
      taxonomy_version: item.taxonomy_version,
      overall_sentiment: item.overall_sentiment,
      language: item.language,
      content_type: item.content_type,
      relevance: item.relevance,
      summary: item.summary,
      model_mentions: item.model_mentions,
      aspects: item.aspects.map((aspect) =>
        Object.fromEntries(Object.entries(aspect).filter(([key]) => key !== 'id')),
      ),
    },
    null,
    2,
  )
  reviewReason.value = ''
  reviewVisible.value = true
}

async function saveReview() {
  if (!reviewTarget.value) return
  try {
    const payload = JSON.parse(correctedJson.value) as Record<string, unknown>
    await reviewStructuredAnalysis(reviewTarget.value.id, payload, reviewReason.value)
    ElMessage.success('复核结果已保存，修改前后版本均已留存')
    reviewVisible.value = false
    await load()
  } catch {
    ElMessage.error('复核内容无效或保存失败')
  }
}

onMounted(load)
</script>

<template>
  <section class="page-stack">
    <header class="page-header">
      <div>
        <h1>AI 结构化分析</h1>
        <p>查看观点拆分、标签、证据与人工复核状态</p>
      </div>
      <el-tag effect="plain">Taxonomy {{ taxonomy?.taxonomy_version || '1.0.0' }}</el-tag>
    </header>
    <el-card shadow="never">
      <div class="filters">
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
        <el-select v-model="filters.review_required" clearable placeholder="复核状态">
          <el-option label="待复核" value="true" /><el-option label="已确认" value="false" />
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
        description="暂无 V1 结构化分析结果；系统不会自动调用收费模型"
      />
      <el-card v-for="item in items" :key="item.id" class="analysis-card" shadow="hover">
        <template #header>
          <div class="card-title">
            <strong>{{ item.original_title || `反馈 #${item.content}` }}</strong
            ><span
              ><el-tag v-if="item.review_required" type="warning">待复核</el-tag>
              {{ item.product_name }} · {{ item.source_name }}</span
            >
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
          ><el-button @click="openReview(item)">人工复核</el-button>
        </footer>
      </el-card>
    </div>
    <p v-if="count" class="count">共 {{ count }} 条结果</p>
    <el-dialog
      v-model="reviewVisible"
      title="人工复核（可修改、删除或补充观点）"
      width="min(900px, 94vw)"
    >
      <el-alert
        title="保存时会再次校验标签父子关系和原文证据，修改历史不会被覆盖。"
        type="info"
        :closable="false"
      />
      <el-input v-model="correctedJson" class="json-editor" type="textarea" :rows="20" />
      <el-input v-model="reviewReason" placeholder="复核原因" />
      <template #footer
        ><el-button @click="reviewVisible = false">取消</el-button
        ><el-button type="primary" @click="saveReview">校验并保存</el-button></template
      >
    </el-dialog>
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
}
</style>
