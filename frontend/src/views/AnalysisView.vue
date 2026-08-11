<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import {
  createAnalysisBatch,
  evaluateAnalysis,
  getAIConfiguration,
  getAnalysisBatches,
  getAnalysisResults,
  getAnalysisSummary,
  getProducts,
  getSamplePreview,
  getSources,
} from '@/api'
import type {
  AIConfiguration,
  AnalysisBatch,
  AnalysisEvaluation,
  AnalysisResult,
  AnalysisSummary,
  DataSource,
  Product,
  SamplePreview,
} from '@/types/api'

const loading = ref(false)
const summary = ref<AnalysisSummary | null>(null)
const configuration = ref<AIConfiguration | null>(null)
const results = ref<AnalysisResult[]>([])
const batches = ref<AnalysisBatch[]>([])
const products = ref<Product[]>([])
const sources = ref<DataSource[]>([])
const total = ref(0)
const page = ref(1)
const createVisible = ref(false)
const detailVisible = ref(false)
const selected = ref<AnalysisResult | null>(null)
const samplePreview = ref<SamplePreview | null>(null)

const filters = reactive({
  sample_version: 'phase5-poc-v2',
  status: '',
  aspect: '',
  sentiment: '',
  record_type: '',
  confidence_min: undefined as number | undefined,
})

const createForm = reactive({
  product_id: undefined as number | undefined,
  source_id: undefined as number | undefined,
  prompt_version: 'review_analysis_v3',
  limit: 20 as 20 | 100 | 278,
})

type EvaluationDecision = boolean | null
type EvaluationForm = Omit<
  AnalysisEvaluation,
  | 'evaluated_at'
  | 'aspect_correct'
  | 'sentiment_correct'
  | 'issue_correct'
  | 'scenario_correct'
  | 'evidence_correct'
  | 'hallucination'
> & {
  aspect_correct: EvaluationDecision
  sentiment_correct: EvaluationDecision
  issue_correct: EvaluationDecision
  scenario_correct: EvaluationDecision
  evidence_correct: EvaluationDecision
  hallucination: EvaluationDecision
}

function emptyEvaluation(): EvaluationForm {
  return {
    aspect_correct: null,
    sentiment_correct: null,
    issue_correct: null,
    scenario_correct: null,
    evidence_correct: null,
    hallucination: null,
    reviewer_notes: '',
  }
}

const evaluation = reactive<EvaluationForm>(emptyEvaluation())

const aspects = [
  'BATTERY',
  'CHARGING',
  'HEATING',
  'SIGNAL',
  'PERFORMANCE',
  'SYSTEM_FLUENCY',
  'SYSTEM_BUG',
  'DISPLAY',
  'CAMERA',
  'WEIGHT_AND_FEEL',
  'BUILD_QUALITY',
  'AUDIO_AND_CALL',
  'DURABILITY',
  'VALUE_FOR_MONEY',
  'AFTER_SALES',
]

const accuracyText = computed(() => {
  if (!summary.value?.evaluated) return 'NOT EVALUATED'
  const value = summary.value.evaluation_accuracy.aspect
  return value === null ? 'NOT EVALUATED' : `${(value * 100).toFixed(1)}%`
})

const sampleQuantity = computed(() => samplePreview.value?.count ?? total.value)
const isPreviewMode = computed(() => filters.sample_version === 'phase5-poc-v2')

async function loadResults() {
  if (isPreviewMode.value) {
    samplePreview.value = await getSamplePreview(filters.sample_version)
    results.value = []
    total.value = 0
    return
  }
  samplePreview.value = null
  const response = await getAnalysisResults({
    page: page.value,
    page_size: 20,
    ...Object.fromEntries(
      Object.entries(filters).filter(([, value]) => value !== '' && value !== undefined),
    ),
  })
  results.value = response.results
  total.value = response.count
}

async function loadAll() {
  loading.value = true
  try {
    const [summaryData, configData, batchData, productData, sourceData] = await Promise.all([
      getAnalysisSummary(),
      getAIConfiguration(),
      getAnalysisBatches(),
      getProducts({ page_size: 100 }),
      getSources({ page_size: 100 }),
    ])
    summary.value = summaryData
    configuration.value = configData
    batches.value = batchData
    products.value = productData.results
    sources.value = sourceData.results
    await loadResults()
    if (!createForm.product_id)
      createForm.product_id = products.value.find(
        (product) => product.normalized_name === 'HONOR_POWER2',
      )?.id
    if (!createForm.source_id)
      createForm.source_id = sources.value.find((source) => source.code === 'HONOR_CLUB')?.id
  } finally {
    loading.value = false
  }
}

async function submitBatch() {
  if (!createForm.product_id || !createForm.source_id) return
  let allowLargeRun = false
  if (createForm.limit > 20) {
    try {
      await ElMessageBox.confirm(
        `本次将调用真实 AI 分析 ${createForm.limit} 条反馈，是否明确继续？`,
        '大任务二次确认',
        { confirmButtonText: '明确继续', cancelButtonText: '取消', type: 'warning' },
      )
      allowLargeRun = true
    } catch {
      return
    }
  }
  try {
    await createAnalysisBatch({
      product_id: createForm.product_id,
      source_id: createForm.source_id,
      prompt_version: createForm.prompt_version,
      limit: createForm.limit,
      allow_large_run: allowLargeRun,
    })
    ElMessage.success('分析批次已创建')
    createVisible.value = false
    await loadAll()
  } catch {
    ElMessage.error('创建失败，请检查 AI 配置与后端日志')
  }
}

function openDetail(row: AnalysisResult) {
  selected.value = row
  Object.assign(evaluation, row.evaluation || emptyEvaluation())
  detailVisible.value = true
}

function sentimentText(row: AnalysisResult) {
  return row.aspects.map((item) => item.sentiment).join(', ')
}

function issueText(row: AnalysisResult) {
  return row.aspects
    .map((item) => item.issue_category)
    .filter(Boolean)
    .join(', ')
}

function escapeHtml(value: string) {
  return value
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;')
}

function highlightEvidence(content: string, evidence: string) {
  if (!evidence) return escapeHtml(content)
  const index = content.indexOf(evidence)
  if (index < 0) return escapeHtml(content)
  return [
    escapeHtml(content.slice(0, index)),
    `<mark>${escapeHtml(evidence)}</mark>`,
    escapeHtml(content.slice(index + evidence.length)),
  ].join('')
}

function evidenceMissing(content: string, evidence: string) {
  return !evidence || !content.includes(evidence)
}

function markAllCorrect() {
  evaluation.aspect_correct = true
  evaluation.sentiment_correct = true
  evaluation.issue_correct = true
  evaluation.scenario_correct = true
  evaluation.evidence_correct = true
  evaluation.hallucination = false
}

function markHasError() {
  Object.assign(evaluation, emptyEvaluation())
}

async function saveEvaluation() {
  if (!selected.value) return
  const decisions = [
    evaluation.aspect_correct,
    evaluation.sentiment_correct,
    evaluation.issue_correct,
    evaluation.scenario_correct,
    evaluation.evidence_correct,
    evaluation.hallucination,
  ]
  if (decisions.some((value) => value === null)) {
    ElMessage.warning('请完成全部人工审核项后再保存')
    return
  }
  await evaluateAnalysis(selected.value.id, {
    aspect_correct: evaluation.aspect_correct as boolean,
    sentiment_correct: evaluation.sentiment_correct as boolean,
    issue_correct: evaluation.issue_correct as boolean,
    scenario_correct: evaluation.scenario_correct as boolean,
    evidence_correct: evaluation.evidence_correct as boolean,
    hallucination: evaluation.hallucination as boolean,
    reviewer_notes: evaluation.reviewer_notes,
  })
  ElMessage.success('人工评价已保存')
  await loadAll()
  selected.value = results.value.find((item) => item.id === selected.value?.id) || selected.value
}

onMounted(loadAll)
</script>

<template>
  <div v-loading="loading">
    <div class="page-header">
      <div>
        <h1 class="page-title">AI 结构化分析</h1>
        <p class="page-description">
          基于治理后的荣耀俱乐部用户反馈进行结构化AI分析，所有结果保留原文证据，本阶段不生成产品综合评分。
        </p>
      </div>
      <el-button
        type="primary"
        :disabled="!configuration?.configured || isPreviewMode"
        @click="createVisible = true"
      >
        创建分析任务
      </el-button>
    </div>

    <el-alert
      v-if="configuration && !configuration.configured"
      title="AI_NOT_CONFIGURED：生产环境尚未配置模型、兼容 API 地址或密钥。"
      type="warning"
      :closable="false"
      show-icon
      class="config-alert"
    />

    <div v-if="summary" class="metric-grid">
      <div class="metric-card">
        <span>评测集数量</span><strong>{{ sampleQuantity }}</strong>
      </div>
      <div class="metric-card">
        <span>可分析语料</span><strong>{{ summary.eligible_corpus }}</strong>
      </div>
      <div class="metric-card success">
        <span>历史分析成功</span><strong>{{ summary.success }}</strong>
      </div>
      <div class="metric-card danger">
        <span>历史分析失败</span><strong>{{ summary.failed }}</strong>
      </div>
      <div class="metric-card">
        <span>待分析语料</span><strong>{{ summary.pending }}</strong>
      </div>
      <div class="metric-card">
        <span>人工 Aspect 准确率</span><strong>{{ accuracyText }}</strong>
      </div>
    </div>

    <div class="panel filters">
      <el-select
        v-model="filters.sample_version"
        clearable
        placeholder="评测集"
        @change="loadResults"
      >
        <el-option label="phase5-poc-v1（固定20条）" value="phase5-poc-v1" />
        <el-option label="phase5-poc-v2（待人工确认）" value="phase5-poc-v2" />
      </el-select>
      <el-select v-model="filters.status" clearable placeholder="状态" @change="loadResults">
        <el-option
          v-for="value in ['SUCCESS', 'FAILED', 'PENDING']"
          :key="value"
          :label="value"
          :value="value"
        />
      </el-select>
      <el-select
        v-model="filters.aspect"
        clearable
        filterable
        placeholder="Aspect"
        @change="loadResults"
      >
        <el-option v-for="value in aspects" :key="value" :label="value" :value="value" />
      </el-select>
      <el-select
        v-model="filters.sentiment"
        clearable
        placeholder="Sentiment"
        @change="loadResults"
      >
        <el-option
          v-for="value in ['POSITIVE', 'NEGATIVE', 'NEUTRAL', 'MIXED']"
          :key="value"
          :label="value"
          :value="value"
        />
      </el-select>
      <el-select
        v-model="filters.record_type"
        clearable
        placeholder="记录类型"
        @change="loadResults"
      >
        <el-option label="THREAD" value="THREAD" /><el-option label="REPLY" value="REPLY" />
      </el-select>
      <el-input-number
        v-model="filters.confidence_min"
        :min="0"
        :max="1"
        :step="0.1"
        placeholder="最低置信度"
        @change="loadResults"
      />
    </div>

    <div v-if="samplePreview" class="panel preview-panel">
      <div class="preview-heading">
        <div>
          <h2>phase5-poc-v2 样本预览</h2>
          <p>请先确认这 20 条是否值得送入 AI；当前没有调用真实模型。</p>
        </div>
        <el-tag type="warning">{{ samplePreview.ai_status }}</el-tag>
      </div>
      <el-table :data="samplePreview.items" row-key="review_id">
        <el-table-column prop="review_id" label="Review ID" width="95" />
        <el-table-column prop="record_type" label="Record Type" width="115" />
        <el-table-column prop="content_purpose" label="Content Purpose" width="170" />
        <el-table-column label="当前正文" min-width="320">
          <template #default="{ row }"
            ><div class="preview-text">{{ row.current_content }}</div></template
          >
        </el-table-column>
        <el-table-column label="必要上下文" min-width="320">
          <template #default="{ row }"
            ><div class="preview-text">{{ row.necessary_context }}</div></template
          >
        </el-table-column>
        <el-table-column label="体验 Signal" min-width="260">
          <template #default="{ row }">
            <div class="preview-text">{{ row.experience_signal_reason }}</div>
            <el-tag v-for="aspect in row.candidate_aspects" :key="aspect" size="small">{{
              aspect
            }}</el-tag>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <div v-if="batches.length" class="panel batch-panel">
      <h2>最近分析任务</h2>
      <el-table :data="batches.slice(0, 5)" size="small">
        <el-table-column prop="id" label="Batch ID" width="90" />
        <el-table-column prop="status" label="状态" width="100" />
        <el-table-column prop="requested_count" label="计划" width="80" />
        <el-table-column prop="success_count" label="成功" width="80" />
        <el-table-column prop="failed_count" label="失败" width="80" />
        <el-table-column prop="skipped_count" label="跳过" width="80" />
        <el-table-column prop="model_name" label="模型" min-width="140" />
        <el-table-column prop="prompt_version" label="Prompt" width="180" />
        <el-table-column prop="created_at" label="创建时间" min-width="180" />
      </el-table>
    </div>

    <div v-if="!isPreviewMode" class="panel">
      <el-table :data="results" @row-click="openDetail">
        <el-table-column prop="review_id" label="Review ID" width="95" />
        <el-table-column prop="record_type" label="Record Type" width="115" />
        <el-table-column label="正文摘要" min-width="240"
          ><template #default="{ row }">{{
            row.original_content.slice(0, 80)
          }}</template></el-table-column
        >
        <el-table-column label="Aspect" min-width="180"
          ><template #default="{ row }"
            ><el-tag v-for="item in row.aspects" :key="item.id" size="small">{{
              item.aspect
            }}</el-tag></template
          ></el-table-column
        >
        <el-table-column label="Sentiment" width="130"
          ><template #default="{ row }">{{ sentimentText(row) }}</template></el-table-column
        >
        <el-table-column label="Issue" min-width="150"
          ><template #default="{ row }">{{ issueText(row) }}</template></el-table-column
        >
        <el-table-column prop="confidence" label="Confidence" width="105" />
        <el-table-column prop="model_name" label="Model" min-width="130" />
        <el-table-column prop="prompt_version" label="Prompt" width="170" />
        <el-table-column prop="status" label="状态" width="100" />
      </el-table>
      <el-pagination
        v-model:current-page="page"
        :total="total"
        :page-size="20"
        layout="prev, pager, next, total"
        @current-change="loadResults"
      />
    </div>

    <el-dialog v-model="createVisible" title="创建分析任务" width="520px">
      <el-form label-width="90px">
        <el-form-item label="产品"
          ><el-select v-model="createForm.product_id"
            ><el-option
              v-for="item in products.filter(
                (product) => product.normalized_name === 'HONOR_POWER2',
              )"
              :key="item.id"
              :label="item.name"
              :value="item.id" /></el-select
        ></el-form-item>
        <el-form-item label="来源"
          ><el-select v-model="createForm.source_id"
            ><el-option
              v-for="item in sources.filter((source) => source.code === 'HONOR_CLUB')"
              :key="item.id"
              :label="item.name"
              :value="item.id" /></el-select
        ></el-form-item>
        <el-form-item label="Prompt"
          ><el-input v-model="createForm.prompt_version" readonly
        /></el-form-item>
        <el-form-item label="数量"
          ><el-radio-group v-model="createForm.limit"
            ><el-radio-button :value="20">20</el-radio-button
            ><el-radio-button :value="100">100</el-radio-button
            ><el-radio-button :value="278">全部</el-radio-button></el-radio-group
          ></el-form-item
        >
        <el-form-item label="模型"
          ><span>{{ configuration?.provider }} / {{ configuration?.model }}</span></el-form-item
        >
      </el-form>
      <template #footer
        ><el-button @click="createVisible = false">取消</el-button
        ><el-button type="primary" @click="submitBatch">创建</el-button></template
      >
    </el-dialog>

    <el-drawer v-model="detailVisible" title="AI 分析详情" size="72%">
      <template v-if="selected">
        <h3>原始区域</h3>
        <dl class="detail-grid">
          <dt>Review ID</dt>
          <dd>{{ selected.review_id }}</dd>
          <dt>记录类型</dt>
          <dd>{{ selected.record_type }}</dd>
          <dt>发布时间</dt>
          <dd>{{ selected.published_at || '未解析' }}</dd>
          <dt>模型</dt>
          <dd>{{ selected.model_name }}</dd>
          <dt>Prompt</dt>
          <dd>{{ selected.prompt_version }}</dd>
          <dt>分析时间</dt>
          <dd>{{ selected.analyzed_at || '未完成' }}</dd>
          <dt>分析状态</dt>
          <dd>{{ selected.status }}</dd>
          <dt>人工审核</dt>
          <dd>
            <el-tag :type="selected.evaluation ? 'success' : 'info'">
              {{ selected.evaluation ? '已审核' : '未审核' }}
            </el-tag>
          </dd>
          <dt>原文</dt>
          <dd class="pre">{{ selected.original_content }}</dd>
          <dt>父帖上下文</dt>
          <dd class="pre">{{ selected.context_text }}</dd>
        </dl>
        <h3>AI 结果</h3>
        <el-alert
          v-if="selected.error_code"
          :title="`${selected.error_code}: ${selected.error_message}`"
          type="error"
          :closable="false"
        />
        <div v-for="item in selected.aspects" :key="item.id" class="aspect-card">
          <div>
            <el-tag>{{ item.aspect }}</el-tag> <el-tag type="info">{{ item.sentiment }}</el-tag>
            <strong>{{ item.confidence }}</strong>
          </div>
          <p><b>问题：</b>{{ item.issue_category }} · {{ item.issue_summary || '—' }}</p>
          <p><b>场景：</b>{{ item.usage_scenario || '—' }}</p>
          <div class="evidence-block">
            <b>当前正文证据：</b>
            <div
              class="evidence-content"
              v-html="highlightEvidence(selected.original_content, item.evidence_text)"
            />
            <el-alert
              v-if="evidenceMissing(selected.original_content, item.evidence_text)"
              title="证据校验失败：当前证据不在用户正文中"
              type="error"
              :closable="false"
            />
          </div>
          <div v-if="item.context_dependent" class="evidence-block">
            <b>上下文证据（Review {{ item.context_evidence_review_id }}）：</b>
            <div
              class="evidence-content"
              v-html="highlightEvidence(selected.context_text, item.context_evidence_text)"
            />
            <el-alert
              v-if="evidenceMissing(selected.context_text, item.context_evidence_text)"
              title="证据校验失败：上下文证据不在父帖/上下文中"
              type="error"
              :closable="false"
            />
          </div>
        </div>
        <h3>人工评价</h3>
        <div class="evaluation-actions">
          <el-button type="success" plain @click="markAllCorrect">标记全部正确</el-button>
          <el-button plain @click="markHasError">清空并逐项审核</el-button>
        </div>
        <div class="evaluation-grid">
          <div class="evaluation-item">
            <span>Aspect</span>
            <el-radio-group v-model="evaluation.aspect_correct">
              <el-radio-button :value="true">正确</el-radio-button>
              <el-radio-button :value="false">错误</el-radio-button>
            </el-radio-group>
          </div>
          <div class="evaluation-item">
            <span>Sentiment</span>
            <el-radio-group v-model="evaluation.sentiment_correct">
              <el-radio-button :value="true">正确</el-radio-button>
              <el-radio-button :value="false">错误</el-radio-button>
            </el-radio-group>
          </div>
          <div class="evaluation-item">
            <span>Issue</span>
            <el-radio-group v-model="evaluation.issue_correct">
              <el-radio-button :value="true">正确</el-radio-button>
              <el-radio-button :value="false">错误</el-radio-button>
            </el-radio-group>
          </div>
          <div class="evaluation-item">
            <span>Scenario</span>
            <el-radio-group v-model="evaluation.scenario_correct">
              <el-radio-button :value="true">正确</el-radio-button>
              <el-radio-button :value="false">错误</el-radio-button>
            </el-radio-group>
          </div>
          <div class="evaluation-item">
            <span>Evidence</span>
            <el-radio-group v-model="evaluation.evidence_correct">
              <el-radio-button :value="true">正确</el-radio-button>
              <el-radio-button :value="false">错误</el-radio-button>
            </el-radio-group>
          </div>
          <div class="evaluation-item">
            <span>Hallucination</span>
            <el-radio-group v-model="evaluation.hallucination">
              <el-radio-button :value="true">有</el-radio-button>
              <el-radio-button :value="false">无</el-radio-button>
            </el-radio-group>
          </div>
        </div>
        <el-input
          v-model="evaluation.reviewer_notes"
          type="textarea"
          :rows="3"
          placeholder="审核备注（可选）"
        />
        <el-button type="primary" class="save-button" @click="saveEvaluation"
          >保存人工评价</el-button
        >
      </template>
    </el-drawer>
  </div>
</template>

<style scoped>
.config-alert {
  margin-bottom: 18px;
}
.metric-grid {
  display: grid;
  grid-template-columns: repeat(6, minmax(130px, 1fr));
  gap: 14px;
  margin-bottom: 18px;
}
.metric-card {
  background: #fff;
  border: 1px solid #e5e9f0;
  border-radius: 10px;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.metric-card strong {
  font-size: 24px;
}
.metric-card.success strong {
  color: #16845b;
}
.metric-card.danger strong {
  color: #c84444;
}
.filters {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 16px;
}
.batch-panel {
  margin-bottom: 16px;
}
.batch-panel h2 {
  margin: 0 0 12px;
  font-size: 17px;
}
.preview-panel {
  margin-bottom: 16px;
}
.preview-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 14px;
}
.preview-heading h2,
.preview-heading p {
  margin: 0;
}
.preview-heading p {
  margin-top: 6px;
  color: #667085;
}
.preview-text {
  white-space: pre-wrap;
  line-height: 1.6;
}
.filters > * {
  width: 180px;
}
.el-pagination {
  margin-top: 16px;
  justify-content: flex-end;
}
.el-tag + .el-tag {
  margin-left: 4px;
}
.detail-grid {
  display: grid;
  grid-template-columns: 110px 1fr;
  gap: 10px 16px;
}
.detail-grid dt {
  color: #667085;
}
.detail-grid dd {
  margin: 0;
}
.pre {
  white-space: pre-wrap;
  line-height: 1.65;
}
.aspect-card {
  border: 1px solid #e5e9f0;
  border-radius: 8px;
  padding: 14px;
  margin: 12px 0;
}
.evidence-block {
  margin-top: 12px;
}
.evidence-content {
  margin-top: 6px;
  padding: 10px;
  white-space: pre-wrap;
  line-height: 1.65;
  background: #f8fafc;
  border-radius: 6px;
}
.evidence-content :deep(mark) {
  padding: 1px 2px;
  background: #fff176;
  color: #1f2937;
}
.evaluation-actions {
  margin-bottom: 12px;
}
.evaluation-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
  margin-bottom: 14px;
}
.evaluation-item {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 6px;
}
.save-button {
  margin-top: 12px;
}
@media (max-width: 1100px) {
  .metric-grid {
    grid-template-columns: repeat(3, 1fr);
  }
}
</style>
