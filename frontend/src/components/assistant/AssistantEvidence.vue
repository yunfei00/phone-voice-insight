<script setup lang="ts">
import { Link } from '@element-plus/icons-vue'
import type { AssistantEvidenceItem } from '@/types/api'

defineProps<{ items: AssistantEvidenceItem[] }>()
</script>

<template>
  <div v-if="items.length" class="evidence-list">
    <div class="evidence-heading">引用证据 · {{ items.length }}</div>
    <article
      v-for="item in items"
      :key="`${item.review_id}-${item.source_url}`"
      class="evidence-item"
    >
      <div class="evidence-title">{{ item.title || '用户反馈' }}</div>
      <p>{{ item.content }}</p>
      <a v-if="item.source_url" :href="item.source_url" target="_blank" rel="noopener noreferrer">
        <el-icon><Link /></el-icon>查看原始帖子
      </a>
      <span v-else>原帖链接不可用，展示系统已保存内容</span>
    </article>
  </div>
</template>

<style scoped>
.evidence-list {
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px solid #29435c;
}
.evidence-heading {
  margin-bottom: 8px;
  color: #42d6c6;
  font-size: 13px;
}
.evidence-item {
  margin: 8px 0;
  padding: 10px 12px;
  border: 1px solid #29435c;
  border-radius: 8px;
  background: #0a192a;
}
.evidence-title {
  color: #edf5ff;
  font-weight: 600;
}
.evidence-item p {
  display: -webkit-box;
  overflow: hidden;
  margin: 6px 0;
  color: #96adc6;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
}
.evidence-item a,
.evidence-item span {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: #35b9f0;
  font-size: 12px;
}
</style>
