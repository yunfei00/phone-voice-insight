<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { getHealth, getOperationsStatus } from '@/api'
import type { HealthStatus, OperationsStatus } from '@/types/api'

const appVersion = __APP_VERSION__
const health = ref<HealthStatus | null>(null)
const operations = ref<OperationsStatus | null>(null)
const loading = ref(false)
const error = ref('')
const checkedAt = ref('')
let timer: number | undefined

const serviceNames: Record<string, string> = {
  backend: '后端 API',
  database: '数据库',
  redis: 'Redis',
  celery_worker: 'Celery Worker',
  celery_beat: 'Celery Beat',
}
const metricNames: Record<string, string> = {
  running: '运行中',
  waiting: '等待中',
  recent_success: '累计成功',
  recent_failed: '累计失败',
  active_leases: '有效采集租约',
  pending: '待处理',
  eligible: '可分析语料',
  rejected: '已拒绝',
  uncertain: '待确认',
  errors: '错误',
  running_batches: '运行中批次',
  ai_governance_running: 'AI 治理运行中',
  successful: '累计成功',
  failed: '累计失败',
  completed: '累计完成',
  cancelled: '累计取消',
}
const statusNames: Record<string, string> = {
  online: '在线',
  offline: '离线',
  stale: '心跳过期',
  unknown: '无法确认',
  ok: '正常',
  error: '异常',
  running: '运行中',
  idle: '空闲',
  normal: '正常',
  no_success_record: '暂无成功记录',
  enabled: '已启用',
  disabled: '未启用',
}
function statusText(value: string | undefined): string {
  return statusNames[value || ''] || value || '未知'
}
function statusType(value: string | undefined): 'success' | 'danger' | 'warning' {
  if (value === 'online' || value === 'ok' || value === 'normal') return 'success'
  if (value === 'offline' || value === 'error' || value === 'stale') return 'danger'
  return 'warning'
}
function formatDate(value: string | null | undefined): string {
  return value ? new Date(value).toLocaleString('zh-CN') : '暂无记录'
}
async function load(): Promise<void> {
  if (loading.value) return
  loading.value = true
  error.value = ''
  const [base, detail] = await Promise.allSettled([getHealth(), getOperationsStatus()])
  if (base.status === 'fulfilled') health.value = base.value
  else health.value = null
  if (detail.status === 'fulfilled') operations.value = detail.value
  else operations.value = null
  if (base.status === 'rejected' || detail.status === 'rejected') {
    error.value = '部分监控数据获取失败，请检查网络、登录权限或后端服务。'
  }
  checkedAt.value = new Date().toLocaleString('zh-CN')
  loading.value = false
}
onMounted(() => {
  void load()
  timer = window.setInterval(() => {
    if (document.visibilityState === 'visible') void load()
  }, 30_000)
})
onBeforeUnmount(() => window.clearInterval(timer))
</script>

<template>
  <div class="system-status-page">
    <div class="page-header">
      <div>
        <h1 class="page-title">系统运行监控中心</h1>
        <p class="page-description">基础服务、后台任务、数据采集和 AI 运行状态 · 每30秒自动刷新</p>
      </div>
      <el-button :loading="loading" @click="load">刷新状态</el-button>
    </div>
    <el-alert v-if="error" :title="error" type="warning" :closable="false" class="notice" />
    <div class="panel">
      <h3>基础服务健康</h3>
      <el-descriptions :column="1" border>
        <el-descriptions-item label="前端版本">{{ appVersion }}</el-descriptions-item>
        <el-descriptions-item label="API 连接">
          <el-tag :type="health ? 'success' : 'danger'">{{ health ? '已连接' : '未连接' }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="后端服务">{{ health?.service || '未知' }}</el-descriptions-item>
        <el-descriptions-item v-for="(value, key) in operations?.system || {}" :key="key" :label="serviceNames[key] || key">
          <el-tag :type="statusType(value)">{{ statusText(value) }}</el-tag>
        </el-descriptions-item>
        <template v-if="!operations">
          <el-descriptions-item label="数据库">{{ statusText(health?.database) }}</el-descriptions-item>
          <el-descriptions-item label="Redis">{{ statusText(health?.redis) }}</el-descriptions-item>
        </template>
      </el-descriptions>
    </div>
    <template v-if="operations">
      <div class="monitor-grid">
        <section class="panel">
          <h3>数据采集</h3>
          <p>当前状态：<el-tag :type="operations.business_status.collection === 'running' ? 'warning' : 'info'">{{ statusText(operations.business_status.collection) }}</el-tag></p>
          <p>最近成功采集：{{ formatDate(operations.latest.collection_at) }}</p>
          <el-descriptions v-if="operations.collection" :column="1" border>
            <el-descriptions-item v-for="(value, key) in operations.collection" :key="key" :label="metricNames[key] || key">{{ value }}</el-descriptions-item>
          </el-descriptions>
        </section>
        <section class="panel">
          <h3>AI 分析</h3>
          <p>最近成功分析：{{ formatDate(operations.latest.analysis_at) }}</p>
          <p>自动分析：{{ operations.business_status.ai_message }}</p>
          <el-descriptions v-if="operations.analysis" :column="1" border>
            <el-descriptions-item v-for="(value, key) in operations.analysis" :key="key" :label="metricNames[key] || key">{{ value }}</el-descriptions-item>
          </el-descriptions>
        </section>
        <section class="panel">
          <h3>数据治理</h3>
          <el-descriptions v-if="operations.governance" :column="1" border>
            <el-descriptions-item v-for="(value, key) in operations.governance" :key="key" :label="metricNames[key] || key">{{ value }}</el-descriptions-item>
          </el-descriptions>
          <p v-else>详细统计仅管理员可见。</p>
        </section>
        <section class="panel">
          <h3>AI 智能助手</h3>
          <el-descriptions v-if="operations.assistant" :column="1" border>
            <el-descriptions-item v-for="(value, key) in operations.assistant" :key="key" :label="metricNames[key] || key">{{ value }}</el-descriptions-item>
          </el-descriptions>
          <p v-else>详细统计仅管理员可见，或后端尚未更新。</p>
        </section>
      </div>
      <section class="panel">
        <h3>异常关注</h3>
        <el-alert v-if="operations.system.celery_worker === 'offline'" title="Celery Worker 未响应，后台任务可能无法执行" type="error" :closable="false" class="notice" />
        <el-alert v-if="operations.system.celery_beat === 'stale'" title="Celery Beat 心跳过期，请检查定时调度" type="warning" :closable="false" class="notice" />
        <el-alert v-if="operations.collection?.recent_failed" :title="`采集任务累计失败 ${operations.collection.recent_failed} 次（历史累计，非当前告警）`" type="warning" :closable="false" class="notice" />
        <el-alert v-if="operations.assistant?.failed" :title="`AI 助手累计失败 ${operations.assistant.failed} 次（历史累计，非当前告警）`" type="warning" :closable="false" class="notice" />
        <p v-if="operations.system.celery_worker !== 'offline' && operations.system.celery_beat !== 'stale' && !operations.collection?.recent_failed && !operations.assistant?.failed">未发现以上监控规则匹配的异常；不代表所有业务均已通过健康检查。</p>
      </section>
    </template>
    <p class="checked-at">最近检查：{{ checkedAt || '尚未检查' }}</p>
  </div>
</template>

<style scoped>
.notice { margin-bottom: 12px; }
.panel { margin-bottom: 16px; }
.panel h3 { margin: 0 0 16px; }
.monitor-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
.monitor-grid .panel { min-width: 0; }
.checked-at { color: var(--pvi-muted); font-size: 12px; }
@media (max-width: 800px) { .monitor-grid { grid-template-columns: 1fr; } }
</style>
