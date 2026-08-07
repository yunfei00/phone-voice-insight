<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { onMounted } from 'vue'

import { useSystemStore } from '@/stores/system'

const store = useSystemStore()
const { health, loading, error } = storeToRefs(store)
const appVersion = __APP_VERSION__
onMounted(() => store.fetchDashboardData())
</script>

<template>
  <div>
    <div class="page-header">
      <div>
        <h1 class="page-title">系统状态</h1>
        <p class="page-description">前端版本、API 连接与基础设施健康状态。</p>
      </div>
      <el-button :loading="loading" @click="store.fetchDashboardData()">重新检查</el-button>
    </div>
    <el-alert v-if="error" :title="error" type="error" :closable="false" class="notice" />
    <div class="panel">
      <el-descriptions :column="1" border>
        <el-descriptions-item label="前端版本">{{ appVersion }}</el-descriptions-item>
        <el-descriptions-item label="API 连接">
          <el-tag :type="health ? 'success' : 'danger'">{{ health ? '已连接' : '未连接' }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="后端服务">{{
          health?.service || '未知'
        }}</el-descriptions-item>
        <el-descriptions-item label="数据库">{{ health?.database || '未知' }}</el-descriptions-item>
        <el-descriptions-item label="Redis">{{ health?.redis || '未知' }}</el-descriptions-item>
      </el-descriptions>
    </div>
  </div>
</template>

<style scoped>
.notice {
  margin-bottom: 16px;
}
</style>
