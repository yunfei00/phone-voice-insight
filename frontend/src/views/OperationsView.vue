<script setup lang="ts">
import { Refresh } from '@element-plus/icons-vue'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

import { getOperationsStatus } from '@/api'
import type { OperationsStatus } from '@/types/api'

const data = ref<OperationsStatus>()
const loading = ref(false)
const error = ref('')
let timer: number | undefined
const systemItems = computed(() => (data.value ? Object.entries(data.value.system) : []))
async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    data.value = await getOperationsStatus()
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '运行状态加载失败'
  } finally {
    loading.value = false
  }
}
function label(key: string): string {
  return (
    {
      backend: 'Backend',
      database: 'PostgreSQL',
      redis: 'Redis',
      celery_worker: 'Celery Worker',
      celery_beat: 'Celery Beat',
    }[key] || key
  )
}
function metricLabel(key: string): string {
  return (
    {
      running: '运行中',
      waiting: '等待中',
      recent_success: '历史成功',
      recent_failed: '历史失败',
      active_leases: '有效来源租约',
      pending: '待治理',
      eligible: '可分析语料',
      rejected: '已拒绝',
      uncertain: '不确定',
      errors: '错误',
      running_batches: '运行中批次',
      ai_governance_running: 'AI 治理运行中',
      successful: '结构化成功',
      failed: '结构化失败',
    }[key] || key
  )
}
function statusLabel(value: string): string {
  return (
    {
      online: '在线',
      offline: '离线',
      stale: '心跳过期',
      unknown: '未知',
      idle: '空闲',
      running: '运行中',
      normal: '正常',
      no_success_record: '暂无成功记录',
      enabled: '已启用',
      disabled: '未启用',
    }[value] || value
  )
}
function format(value: string | null | undefined): string {
  return value ? new Date(value).toLocaleString('zh-CN') : '暂无'
}
onMounted(() => {
  load()
  timer = window.setInterval(() => {
    if (document.visibilityState === 'visible') load()
  }, 30_000)
})
onBeforeUnmount(() => window.clearInterval(timer))
</script>

<template>
  <div class="dashboard-page">
    <div class="page-header">
      <div>
        <p class="eyebrow">DATA OPERATIONS</p>
        <h1 class="page-title">数据运行监控</h1>
        <p class="page-description">区分基础服务在线、数据更新正常与 AI 自动化状态</p>
      </div>
      <el-button :icon="Refresh" :loading="loading" @click="load">刷新</el-button>
    </div>
    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon /><template
      v-if="data"
      ><section class="status-banner" :class="data.business_status.ai_automation">
        <div>
          <span>采集状态</span><strong>{{ statusLabel(data.business_status.collection) }}</strong>
        </div>
        <div>
          <span>数据更新</span><strong>{{ statusLabel(data.business_status.data_update) }}</strong>
        </div>
        <div>
          <span>AI 自动化</span><strong>{{ data.business_status.ai_message }}</strong>
        </div>
        <div>
          <span>最近采集</span><strong>{{ format(data.latest.collection_at) }}</strong>
        </div>
      </section>
      <section class="system-grid">
        <article v-for="[key, value] in systemItems" :key="key" class="tech-panel system-card">
          <span class="health-dot" :class="value" />
          <div>
            <small>{{ label(key) }}</small
            ><strong>{{ statusLabel(value) }}</strong>
          </div>
        </article>
      </section>
      <section class="monitor-grid">
        <article class="tech-panel">
          <h2>AI 预算</h2>
          <div class="budget-number">
            <strong>{{ data.ai.today_tokens.toLocaleString() }}</strong
            ><span>/ {{ data.ai.daily_budget.toLocaleString() }} Token</span>
          </div>
          <el-progress
            :percentage="Math.min((data.ai.budget_ratio || 0) * 100, 100)"
            :status="data.ai.budget_exhausted ? 'exception' : undefined"
          />
          <p>{{ data.ai.budget_exhausted ? '预算已耗尽，自动分析应暂停' : '预算范围内' }}</p>
        </article>
        <article v-if="data.collection" class="tech-panel">
          <h2>采集监控</h2>
          <dl>
            <template v-for="(value, key) in data.collection" :key="key"
              ><dt>{{ metricLabel(String(key)) }}</dt>
              <dd>{{ value }}</dd></template
            >
          </dl>
        </article>
        <article v-if="data.governance" class="tech-panel">
          <h2>治理监控</h2>
          <dl>
            <template v-for="(value, key) in data.governance" :key="key"
              ><dt>{{ metricLabel(String(key)) }}</dt>
              <dd>{{ value }}</dd></template
            >
          </dl>
        </article>
        <article v-if="data.analysis" class="tech-panel">
          <h2>AI 分析监控</h2>
          <dl>
            <template v-for="(value, key) in data.analysis" :key="key"
              ><dt>{{ metricLabel(String(key)) }}</dt>
              <dd>{{ value }}</dd></template
            >
          </dl>
        </article>
      </section></template
    >
    <div v-else v-loading="loading" class="loading-space" />
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
.status-banner {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 1px;
  margin-bottom: 16px;
  overflow: hidden;
  background: #29435c;
  border: 1px solid #29435c;
  border-radius: 14px;
}
.status-banner > div {
  padding: 18px;
  background: #12283f;
}
.status-banner span,
.system-card small {
  display: block;
  color: var(--pvi-muted);
  font-size: 12px;
}
.status-banner strong {
  display: block;
  margin-top: 8px;
}
.status-banner.disabled > div:nth-child(3) strong {
  color: var(--pvi-orange);
}
.system-grid {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 12px;
  margin-bottom: 16px;
}
.system-card {
  display: flex;
  align-items: center;
  gap: 12px;
}
.system-card strong {
  display: block;
  margin-top: 5px;
  text-transform: uppercase;
}
.health-dot {
  width: 12px;
  height: 12px;
  background: var(--pvi-orange);
  border-radius: 50%;
}
.health-dot.online {
  background: var(--pvi-green);
  box-shadow: 0 0 12px #42d6c6;
}
.health-dot.offline,
.health-dot.stale {
  background: var(--pvi-red);
}
.monitor-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}
.monitor-grid h2 {
  margin-top: 0;
}
.budget-number strong {
  font-size: 30px;
}
.budget-number span {
  color: var(--pvi-muted);
}
.monitor-grid dl {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 10px;
}
.monitor-grid dt {
  color: var(--pvi-muted);
}
.monitor-grid dd {
  margin: 0;
  color: var(--pvi-blue);
  font-weight: 700;
}
.loading-space {
  min-height: 360px;
}
@media (max-width: 950px) {
  .system-grid {
    grid-template-columns: repeat(2, 1fr);
  }
  .status-banner {
    grid-template-columns: 1fr 1fr;
  }
}
@media (max-width: 620px) {
  .monitor-grid,
  .system-grid,
  .status-banner {
    grid-template-columns: 1fr;
  }
}
</style>
