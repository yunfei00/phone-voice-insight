<script setup lang="ts">
import { Delete, EditPen, Plus } from '@element-plus/icons-vue'
import type { AssistantConversation } from '@/types/api'

defineProps<{ conversations: AssistantConversation[]; activeId: string; loading: boolean }>()
const emit = defineEmits<{
  create: []
  select: [id: string]
  rename: [item: AssistantConversation]
  delete: [item: AssistantConversation]
}>()
</script>

<template>
  <aside class="conversation-sidebar">
    <el-button class="new-chat" type="primary" :icon="Plus" @click="emit('create')"
      >新建会话</el-button
    >
    <el-scrollbar v-loading="loading" class="conversation-list">
      <el-empty
        v-if="!conversations.length && !loading"
        description="暂无历史会话"
        :image-size="70"
      />
      <button
        v-for="item in conversations"
        :key="item.id"
        class="conversation-item"
        :class="{ active: item.id === activeId }"
        @click="emit('select', item.id)"
      >
        <span class="conversation-title">{{ item.title }}</span>
        <small>{{ item.model_display }} · {{ item.message_count }} 条消息</small>
        <span class="conversation-actions" @click.stop>
          <el-button text circle size="small" :icon="EditPen" @click="emit('rename', item)" />
          <el-button text circle size="small" :icon="Delete" @click="emit('delete', item)" />
        </span>
      </button>
    </el-scrollbar>
  </aside>
</template>

<style scoped>
.conversation-sidebar {
  display: flex;
  min-width: 0;
  flex-direction: column;
  border-right: 1px solid #29435c;
  background: #0a192a;
}
.new-chat {
  margin: 18px;
}
.conversation-list {
  min-height: 0;
  flex: 1;
  padding: 0 10px 18px;
}
.conversation-item {
  position: relative;
  width: 100%;
  margin-bottom: 8px;
  padding: 12px 72px 12px 12px;
  border: 1px solid transparent;
  border-radius: 10px;
  background: transparent;
  color: #edf5ff;
  text-align: left;
  cursor: pointer;
}
.conversation-item:hover,
.conversation-item.active {
  border-color: #29435c;
  background: #12283f;
}
.conversation-item.active {
  box-shadow: inset 3px 0 #35b9f0;
}
.conversation-title {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.conversation-item small {
  display: block;
  margin-top: 5px;
  overflow: hidden;
  color: #96adc6;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.conversation-actions {
  position: absolute;
  top: 12px;
  right: 8px;
  display: none;
}
.conversation-item:hover .conversation-actions,
.conversation-item.active .conversation-actions {
  display: flex;
}
</style>
