<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { onMounted } from 'vue'

import { useSystemStore } from '@/stores/system'

const store = useSystemStore()
const { health, metrics, loading, error } = storeToRefs(store)

onMounted(() => store.fetchDashboardData())

const cards = [
  { key: 'products', label: '产品总数' },
  { key: 'sources', label: '数据来源' },
  { key: 'reviews', label: '反馈总数' },
  { key: 'collectionTasks', label: '采集任务' },
] as const
</script>

<template>
  <div>
    <div class="page-header">
      <div>
        <h1 class="page-title">数据总览</h1>
        <p class="page-description">所有数字直接来自后端 API；没有数据时显示 0。</p>
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
  </div>
</template>

<style scoped>
.notice {
  margin-bottom: 16px;
}

.metric-grid {
  min-height: 130px;
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
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
