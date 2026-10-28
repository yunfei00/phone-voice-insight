<script setup lang="ts">
import { Warning } from '@element-plus/icons-vue'

import HighlightText from '@/components/HighlightText.vue'
import type { ThreadReply } from '@/types/api'

defineOptions({ name: 'ReplyTreeNode' })
defineProps<{ reply: ThreadReply; keyword?: string; depth?: number }>()

function formatDate(value: string | null): string {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  const parts = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23' }).formatToParts(date)
  const part = (type: string) => parts.find(item => item.type === type)?.value || ''
  return `${part('year')}-${part('month')}-${part('day')} ${part('hour')}:${part('minute')}:${part('second')}`
}
</script>

<template>
  <div class="reply-node" :class="{ nested: (depth || 0) > 0 }">
    <div class="reply-meta">
      <span class="reply-role">{{ reply.is_official ? '官方账号' : '普通用户' }}</span>
      <el-tag v-if="reply.is_official" type="warning" size="small" effect="light">官方</el-tag>
      <el-tag v-if="reply.unresolved_parent" type="info" size="small" effect="plain">
        <el-icon><Warning /></el-icon>
        原父回复未采集
      </el-tag>
      <span>IP 属地：{{ reply.ip_location || '未提供' }}</span>
      <time>{{ formatDate(reply.published_at) }}</time>
    </div>
    <p class="reply-content">
      <HighlightText :text="reply.content || '（无文本内容）'" :keyword="keyword" />
    </p>
    <div v-if="reply.children.length" class="reply-children">
      <ReplyTreeNode
        v-for="child in reply.children"
        :key="child.id"
        :reply="child"
        :keyword="keyword"
        :depth="(depth || 0) + 1"
      />
    </div>
  </div>
</template>

<style scoped>
.reply-node {
  padding: 14px 0 0;
  border-top: 1px solid #edf0f5;
}

.reply-node.nested {
  padding: 12px 14px;
  background: #f7f9fc;
  border-top: 0;
  border-left: 3px solid #d7deea;
  border-radius: 0 8px 8px 0;
}

.reply-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #8a94a6;
  font-size: 12px;
}

.reply-role {
  color: #4a5568;
  font-weight: 600;
}

.reply-meta time {
  margin-left: auto;
}

.reply-content {
  margin: 8px 0 0;
  color: #2d3748;
  line-height: 1.75;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}

.reply-children {
  display: grid;
  gap: 10px;
  margin: 12px 0 0 22px;
}

@media (max-width: 540px) {
  .reply-children {
    margin-left: 10px;
  }

  .reply-meta {
    flex-wrap: wrap;
  }

  .reply-meta time {
    width: 100%;
    margin-left: 0;
  }
}
</style>
