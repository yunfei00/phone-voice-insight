<script setup lang="ts">
import { CopyDocument } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { onMounted, ref } from 'vue'

import { generateInsightReport, getInsightReport, getInsightReports, getProducts } from '@/api'
import type { InsightReport, Product } from '@/types/api'

const products = ref<Product[]>([])
const reportType = ref<'DAILY' | 'WEEKLY'>('DAILY')
const productId = ref<number>()
const reports = ref<InsightReport[]>([])
const selected = ref<InsightReport>()
const loading = ref(false)
const generating = ref(false)
const error = ref('')
async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    const data = await getInsightReports({
      report_type: reportType.value,
      product_id: productId.value,
      page_size: 30,
    })
    reports.value = data.results
    selected.value = undefined
    if (data.results[0]) await select(data.results[0])
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '报告加载失败'
  } finally {
    loading.value = false
  }
}
async function generateNow(): Promise<void> {
  if (generating.value) return
  generating.value = true
  try {
    await generateInsightReport(reportType.value)
    ElMessage.success('报告生成任务已提交，完成后刷新列表即可查看')
  } catch {
    ElMessage.error('提交失败，请确认管理员权限及后台任务服务')
  } finally {
    generating.value = false
  }
}
async function select(item: InsightReport): Promise<void> {
  selected.value = await getInsightReport(item.id)
}
async function copySummary(): Promise<void> {
  if (!selected.value?.snapshot) return
  const text = [
    selected.value.title,
    ...selected.value.snapshot.top_issues.map(
      (item, index) => `${index + 1}. ${item.name}（${item.feedback_count} 条）`,
    ),
    selected.value.snapshot.disclaimer,
  ].join('\n')
  await navigator.clipboard.writeText(text)
  ElMessage.success('报告摘要已复制')
}
function format(value: string | null): string {
  return value ? new Date(value).toLocaleString('zh-CN') : '暂无'
}
onMounted(async () => {
  products.value = (await getProducts({ page_size: 100 })).results
  await load()
})
</script>

<template>
  <div class="dashboard-page">
    <div class="page-header">
      <div>
        <p class="eyebrow">AI INSIGHT REPORTS</p>
        <h1 class="page-title">AI 智能洞察报告</h1>
        <p class="page-description">确定性数据库聚合与模板生成，默认不额外调用付费模型</p>
      </div>
      <el-button type="primary" :loading="generating" @click="generateNow">立即生成报告</el-button>
      <el-button :icon="CopyDocument" :disabled="!selected" @click="copySummary"
        >复制摘要</el-button
      >
    </div>
    <section class="tech-panel report-filters">
      <el-radio-group v-model="reportType" @change="load"
        ><el-radio-button value="DAILY">每日摘要</el-radio-button
        ><el-radio-button value="WEEKLY">最近 7 日</el-radio-button></el-radio-group
      ><el-select v-model="productId" clearable placeholder="全部产品" @change="load"
        ><el-option v-for="item in products" :key="item.id" :label="item.name" :value="item.id"
      /></el-select>
    </section>
    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />
    <section class="report-grid" v-loading="loading">
      <aside class="tech-panel report-list">
        <button
          v-for="item in reports"
          :key="item.id"
          type="button"
          :class="{ active: selected?.id === item.id }"
          @click="select(item)"
        >
          <strong>{{ item.title }}</strong
          ><span>{{ format(item.period_end) }}</span
          ><el-tag size="small" :type="item.status === 'READY' ? 'success' : 'warning'">{{
            item.status
          }}</el-tag></button
        ><el-empty
          v-if="!reports.length"
          description="暂无报告，可点击立即生成报告（需管理员权限）"
        />
      </aside>
      <article class="tech-panel report-content">
        <template v-if="selected?.snapshot"
          ><header>
            <small>{{ selected.product_name }} · {{ selected.source_name }}</small>
            <h2>{{ selected.title }}</h2>
            <p>{{ format(selected.period_start) }} — {{ format(selected.period_end) }}</p>
          </header>
          <el-alert
            v-if="selected.snapshot.data_insufficient"
            title="当前分析样本不足，报告仅展示数据覆盖情况，不作产品优劣判断。"
            type="warning"
            :closable="false"
          />
          <div class="report-metrics">
            <span
              >原始反馈<strong>{{ selected.snapshot.overview.raw_feedback }}</strong></span
            ><span
              >有效反馈<strong>{{ selected.snapshot.overview.valid_feedback }}</strong></span
            ><span
              >AI 已分析<strong>{{ selected.snapshot.overview.ai_analyzed }}</strong></span
            ><span
              >明确问题<strong>{{
                selected.snapshot.overview.explicit_issue_feedback
              }}</strong></span
            >
          </div>
          <h3>TOP 3 问题</h3>
          <ol>
            <li v-for="item in selected.snapshot.top_issues" :key="item.id">
              <strong>{{ item.name }}</strong
              ><span
                >{{ item.product_name }} · {{ item.feedback_count }} 条 · {{ item.severity }}</span
              >
            </li>
          </ol>
          <h3>近期增长观察</h3>
          <div v-if="selected.snapshot.watchlist.length" class="watch-report">
            <p v-for="item in selected.snapshot.watchlist" :key="item.id">
              {{ item.name }}：{{ item.is_new ? '新出现' : `${item.growth_rate}%` }}
            </p>
          </div>
          <p v-else class="muted">当前没有达到最小样本与增长阈值的问题。</p>
          <footer>
            {{ selected.snapshot.disclaimer }}<br />统计截止：{{ format(selected.data_cutoff) }}
          </footer></template
        ><el-empty v-else description="请选择一份报告" />
      </article>
    </section>
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
.report-filters {
  display: flex;
  gap: 16px;
  margin-bottom: 16px;
}
.report-filters .el-select {
  width: 220px;
}
.report-grid {
  display: grid;
  grid-template-columns: 300px minmax(0, 1fr);
  gap: 16px;
}
.report-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.report-list button {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 7px;
  padding: 13px;
  color: inherit;
  text-align: left;
  background: #0a192a;
  border: 1px solid #29435c;
  border-radius: 10px;
  cursor: pointer;
}
.report-list button.active {
  border-color: var(--pvi-blue);
  box-shadow: 0 0 18px #35b9f022;
}
.report-list span {
  color: var(--pvi-muted);
  font-size: 11px;
}
.report-content header {
  padding-bottom: 18px;
  border-bottom: 1px solid #29435c;
}
.report-content header small,
.report-content header p,
.muted,
.report-content footer {
  color: var(--pvi-muted);
}
.report-content h2 {
  font-size: 28px;
}
.report-metrics {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  margin: 20px 0;
}
.report-metrics span {
  padding: 14px;
  color: var(--pvi-muted);
  background: #0a192a;
  border-radius: 9px;
}
.report-metrics strong {
  display: block;
  margin-top: 8px;
  color: var(--pvi-text);
  font-size: 24px;
}
.report-content li {
  margin: 12px 0;
}
.report-content li span {
  display: block;
  margin-top: 4px;
  color: var(--pvi-muted);
}
.report-content footer {
  margin-top: 28px;
  padding-top: 14px;
  border-top: 1px solid #29435c;
  font-size: 12px;
  line-height: 1.7;
}
@media (max-width: 850px) {
  .report-grid {
    grid-template-columns: 1fr;
  }
  .report-metrics {
    grid-template-columns: 1fr 1fr;
  }
}
@media (max-width: 520px) {
  .report-filters {
    flex-direction: column;
  }
  .report-filters .el-select {
    width: 100%;
  }
}
</style>
