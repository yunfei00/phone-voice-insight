<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { onMounted } from 'vue'

import { useSystemStore } from '@/stores/system'

const store = useSystemStore()
const { health, metrics, sources, loading, error } = storeToRefs(store)

onMounted(() => store.fetchDashboardData())

const cards = [
  { key: 'threads', label: '已采集帖子' },
  { key: 'replies', label: '已采集回复' },
  { key: 'rawRecords', label: '原始反馈' },
  { key: 'eligibleCorpus', label: 'AI 可用语料' },
  { key: 'excludedRecords', label: '排除数据' },
] as const
</script>

<template>
  <div>
    <div class="page-header">
      <div>
        <h1 class="page-title">数据总览</h1>
        <p class="page-description">基于荣耀俱乐部公开用户讨论的荣耀 Power2 用户口碑洞察。</p>
      </div>
      <el-button :loading="loading" @click="store.fetchDashboardData()">刷新</el-button>
    </div>

    <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" class="notice" />

    <div v-loading="loading" class="metric-grid">
      <div v-for="card in cards" :key="card.key" class="metric-card">
        <span>{{ card.label }}</span>
        <strong>{{ metrics[card.key] }}</strong>
      </div>
    </div>

    <section class="panel source-panel">
      <div>
        <h2>来源状态</h2>
        <p>系统保留扩展能力，但第一版正式数据只依赖荣耀俱乐部。</p>
      </div>
      <div class="status-items">
        <span>荣耀俱乐部 <el-tag type="success">已启用</el-tag></span>
        <span>京东 <el-tag type="warning">暂缓</el-tag></span>
        <span>已配置来源 {{ sources.length }}</span>
      </div>
    </section>

    <section class="panel status-panel">
      <div>
        <h2>基础设施状态</h2>
        <p>健康检查只返回状态，不暴露主机、密码或连接字符串。</p>
      </div>
      <div class="status-items">
        <span
          >后端
          <el-tag :type="health ? 'success' : 'danger'">{{
            health ? '已连接' : '不可用'
          }}</el-tag></span
        >
        <span
          >数据库
          <el-tag :type="health?.database === 'ok' ? 'success' : 'danger'">{{
            health?.database || '未知'
          }}</el-tag></span
        >
        <span
          >Redis
          <el-tag :type="health?.redis === 'ok' ? 'success' : 'danger'">{{
            health?.redis || '未知'
          }}</el-tag></span
        >
      </div>
    </section>
    <p class="latest">最近采集时间：{{ metrics.latestCollection || '暂无' }}</p>
  </div>
</template>

<style scoped>
.notice {
  margin-bottom: 16px;
}

.metric-grid {
  min-height: 130px;
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 16px;
  margin-bottom: 20px;
}

.metric-card {
  padding: 22px;
  background: #fff;
  border: 1px solid #e7eaf0;
  border-radius: 12px;
}

.metric-card span {
  display: block;
  color: #6b7280;
}

.metric-card strong {
  display: block;
  margin-top: 12px;
  font-size: 32px;
}

.status-panel {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
}

.source-panel {
  margin-bottom: 20px;
}

.source-panel h2,
.source-panel p {
  margin-top: 0;
}

.latest {
  color: #6b7280;
  font-size: 13px;
  text-align: right;
}

.status-panel h2 {
  margin: 0 0 8px;
  font-size: 18px;
}

.status-panel p {
  margin: 0;
  color: #6b7280;
}

.status-items {
  display: flex;
  flex-wrap: wrap;
  gap: 20px;
}

@media (max-width: 900px) {
  .metric-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .status-panel {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
