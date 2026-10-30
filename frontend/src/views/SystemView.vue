<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { getHealth, getOperationsStatus, getSystemResources } from '@/api'
import type { HealthStatus, OperationsStatus } from '@/types/api'

interface ResourceMetric { total: number; used: number; percent: number | null }
interface SystemResources {
  scope: string
  cpu: { cores: number; load_percent: number | null; metric: string }
  memory: ResourceMetric
  disk: ResourceMetric | null
  online: { count: number; definition: string }
  sampled_at: string
}
const appVersion = __APP_VERSION__
const health = ref<HealthStatus | null>(null)
const operations = ref<OperationsStatus | null>(null)
const resources = ref<SystemResources | null>(null)
const business = ref<OperationsStatus | null>(null)
const loading = ref(false)
const error = ref('')
const checkedAt = ref('')
let timer: number | undefined
const serviceNames: Record<string, string> = {
  backend: '后端 API', database: '数据库', redis: 'Redis',
  celery_worker: 'Celery Worker', celery_beat: 'Celery Beat',
}
const statusNames: Record<string, string> = {
  online: '在线', offline: '离线', stale: '心跳过期',
  unknown: '无法确认', ok: '正常', error: '异常',
}
function statusText(value: string | undefined): string { return statusNames[value || ''] || value || '未知' }
function statusType(value: string | undefined): 'success' | 'danger' | 'warning' {
  if (value === 'online' || value === 'ok') return 'success'
  if (value === 'offline' || value === 'error' || value === 'stale') return 'danger'
  return 'warning'
}
function size(bytes: number | undefined): string {
  if (bytes === undefined) return '—'
  return bytes >= 1073741824 ? (bytes / 1073741824).toFixed(1) + ' GB' : (bytes / 1048576).toFixed(1) + ' MB'
}
async function load(): Promise<void> {
  if (loading.value) return
  loading.value = true
  error.value = ''
  const [base, detail, runtime] = await Promise.allSettled([
    getHealth(), getOperationsStatus(), getSystemResources(),
  ])
  health.value = base.status === 'fulfilled' ? base.value : null
  operations.value = detail.status === 'fulfilled' ? detail.value : null
  business.value = operations.value
  resources.value = runtime.status === 'fulfilled' ? runtime.value : null
  if (base.status === 'rejected' || detail.status === 'rejected' || runtime.status === 'rejected') {
    error.value = '部分监控数据获取失败，请检查后端服务或权限。'
  }
  checkedAt.value = new Date().toLocaleString('zh-CN')
  loading.value = false
}
onMounted(() => {
  void load()
  timer = window.setInterval(() => {
    if (document.visibilityState === 'visible') void load()
  }, 10_000)
})
onBeforeUnmount(() => window.clearInterval(timer))
</script>

<template>
  <div class="system-status-page">
    <div class="page-header">
      <div>
        <h1 class="page-title">运行监控</h1>
        <p class="page-description">数据采集、治理、AI 分析及系统资源 · 每10秒自动刷新</p>
      </div>
      <el-button :loading="loading" @click="load">立即刷新</el-button>
    </div>
    <el-alert v-if="error" :title="error" type="warning" :closable="false" class="notice" />
    <el-alert
      title="资源指标来自后端容器视角，不等于宿主机整体使用率；CPU 显示一分钟负载比例，不是瞬时使用率。"
      type="info" :closable="false" show-icon class="notice"
    />
    <div class="resource-grid">
      <section class="panel metric-card">
        <h3>CPU 负载</h3>
        <div class="metric-value">{{ resources?.cpu.load_percent ?? '—' }}<small v-if="resources?.cpu.load_percent != null">%</small></div>
        <el-progress :percentage="Math.min(100, Math.max(0, resources?.cpu.load_percent ?? 0))" :show-text="false" />
        <p>逻辑核心：{{ resources?.cpu.cores ?? '—' }} · 一分钟负载/核心数</p>
      </section>
      <section class="panel metric-card">
        <h3>内存</h3>
        <div class="metric-value">{{ resources?.memory.percent ?? '—' }}<small v-if="resources?.memory.percent != null">%</small></div>
        <el-progress :percentage="Math.min(100, Math.max(0, resources?.memory.percent ?? 0))" :show-text="false" />
        <p>{{ size(resources?.memory.used) }} / {{ size(resources?.memory.total) }}</p>
      </section>
      <section class="panel metric-card">
        <h3>磁盘</h3>
        <div class="metric-value">{{ resources?.disk?.percent ?? '—' }}<small v-if="resources?.disk?.percent != null">%</small></div>
        <el-progress :percentage="Math.min(100, Math.max(0, resources?.disk?.percent ?? 0))" :show-text="false" />
        <p>{{ size(resources?.disk?.used) }} / {{ size(resources?.disk?.total) }}</p>
      </section>
      <section class="panel metric-card">
        <h3>当前在线用户</h3>
        <div class="metric-value">{{ resources?.online.count ?? '—' }}<small>人</small></div>
        <p>最近120秒有活动心跳的独立账号数</p>
      </section>
    </div>
    <section class="panel">
      <h3>业务运行状态</h3>
      <div v-if="business" class="business-grid">
        <div class="business-item"><h4>数据采集</h4><p>状态：{{ business.business_status.collection }}</p><p>最近采集：{{ business.latest.collection_at ? new Date(business.latest.collection_at).toLocaleString('zh-CN') : '暂无' }}</p><p v-for="(value, key) in business.collection || {}" :key="key">{{ key }}：{{ value }}</p></div>
        <div class="business-item"><h4>数据治理</h4><p>数据更新：{{ business.business_status.data_update }}</p><p v-for="(value, key) in business.governance || {}" :key="key">{{ key }}：{{ value }}</p></div>
        <div class="business-item"><h4>AI 分析</h4><p>{{ business.business_status.ai_message }}</p><p>Token 使用：{{ business.ai.today_tokens.toLocaleString() }} / {{ business.ai.daily_budget.toLocaleString() }}</p><p v-for="(value, key) in business.analysis || {}" :key="key">{{ key }}：{{ value }}</p></div>
      </div>
      <el-empty v-else description="业务监控数据暂不可用" />
    </section>
    <section class="panel">
      <h3>基础服务健康</h3>
      <div class="service-grid">
        <div class="service-item"><span>前端版本</span><strong>{{ appVersion }}</strong></div>
        <div class="service-item"><span>API 连接</span><el-tag :type="health ? 'success' : 'danger'">{{ health ? '在线' : '离线' }}</el-tag></div>
        <div v-for="(value, key) in operations?.system || {}" :key="key" class="service-item">
          <span>{{ serviceNames[key] || key }}</span>
          <el-tag :type="statusType(value)">{{ statusText(value) }}</el-tag>
        </div>
        <template v-if="!operations">
          <div class="service-item"><span>数据库</span><el-tag :type="statusType(health?.database)">{{ statusText(health?.database) }}</el-tag></div>
          <div class="service-item"><span>Redis</span><el-tag :type="statusType(health?.redis)">{{ statusText(health?.redis) }}</el-tag></div>
        </template>
      </div>
    </section>
    <p class="checked-at">最近检查：{{ checkedAt || '尚未检查' }}</p>
  </div>
</template>

<style scoped>
.notice { margin-bottom: 16px; }
.business-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
.business-item { padding: 16px; border: 1px solid var(--el-border-color-lighter); border-radius: 8px; overflow-wrap: anywhere; }
.business-item h4 { margin: 0 0 12px; }
.business-item p { margin: 8px 0; color: var(--pvi-muted); }
.panel { margin-bottom: 16px; }
.panel h3 { margin: 0 0 18px; }
.resource-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 16px; }
.metric-card { min-width: 0; padding: 22px; }
.metric-value { font-size: clamp(28px, 3vw, 42px); font-weight: 700; line-height: 1.3; margin: 8px 0 16px; font-variant-numeric: tabular-nums; }
.metric-value small { font-size: 16px; margin-left: 4px; font-weight: 500; }
.metric-card p { margin: 16px 0 0; color: var(--pvi-muted); font-size: 13px; }
.service-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
.service-item { display: flex; justify-content: space-between; align-items: center; gap: 10px; padding: 14px; border: 1px solid var(--el-border-color-lighter); border-radius: 8px; }
.checked-at { color: var(--pvi-muted); font-size: 12px; }
@media (max-width: 1100px) { .resource-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } .service-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 600px) { .resource-grid, .service-grid, .business-grid { grid-template-columns: 1fr; } }
</style>
