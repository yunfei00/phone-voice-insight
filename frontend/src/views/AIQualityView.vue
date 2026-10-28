<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { getStructuredQuality } from '@/api'
import type { StructuredQuality } from '@/types/api'
const loading = ref(false)
const error = ref('')
const quality = ref<StructuredQuality>()
async function load() {
  loading.value = true
  error.value = ''
  try {
    quality.value = await getStructuredQuality()
  } catch {
    error.value = '质量指标加载失败'
  } finally {
    loading.value = false
  }
}
const percent = (value: number | null) =>
  value === null ? '尚无数据' : `${(value * 100).toFixed(1)}%`
onMounted(load)
</script>
<template>
  <section class="quality-page">
    <header>
      <h1>AI 质量中心</h1>
      <p>区分工程合法率与需要真实人工真值的模型准确率</p>
    </header>
    <el-alert v-if="error" :title="error" type="error" show-icon />
    <div v-loading="loading" class="metrics">
      <el-card
        ><span>分析成功率</span
        ><strong>{{ percent(quality?.success_rate ?? null) }}</strong></el-card
      ><el-card
        ><span>Schema 合法率</span
        ><strong>{{ percent(quality?.schema_valid_rate ?? null) }}</strong></el-card
      ><el-card
        ><span>待复核</span><strong>{{ quality?.review_required ?? 0 }}</strong></el-card
      ><el-card><span>人工准确率</span><strong>尚未评测</strong></el-card>
    </div>
    <el-alert
      title="尚无 ≥300 条人工审核金标集，因此 Macro-F1、观点抽取 F1、情感准确率等不得宣称达标。"
      type="warning"
      :closable="false"
      show-icon
    /><el-empty v-if="!loading && !quality?.total_runs" description="暂无 V1 分析运行" />
  </section>
</template>
<style scoped>
.quality-page {
  display: grid;
  gap: 20px;
}
.quality-page h1 {
  margin: 0;
}
.quality-page p {
  color: #6b7280;
}
.metrics {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 14px;
}
.metrics span,
.metrics strong {
  display: block;
}
.metrics span {
  color: #6b7280;
}
.metrics strong {
  margin-top: 10px;
  font-size: 26px;
}
@media (max-width: 800px) {
  .metrics {
    grid-template-columns: 1fr 1fr;
  }
}
</style>
