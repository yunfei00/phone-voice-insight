<script setup lang="ts">
import { Promotion, VideoPause } from '@element-plus/icons-vue'

defineProps<{ modelValue: string; generating: boolean; disabled?: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [value: string]; send: []; stop: [] }>()

function keydown(event: KeyboardEvent) {
  if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
    event.preventDefault()
    emit('send')
  }
}
</script>

<template>
  <div class="composer">
    <el-input
      :model-value="modelValue"
      type="textarea"
      :rows="3"
      maxlength="4000"
      show-word-limit
      resize="none"
      placeholder="询问产品问题、趋势、对比或原始证据，Enter 发送，Shift+Enter 换行"
      :disabled="disabled"
      @update:model-value="emit('update:modelValue', $event)"
      @keydown="keydown"
    />
    <el-button v-if="generating" type="danger" :icon="VideoPause" @click="emit('stop')"
      >停止生成</el-button
    >
    <el-button
      v-else
      type="primary"
      :icon="Promotion"
      :disabled="disabled || !modelValue.trim()"
      @click="emit('send')"
      >发送</el-button
    >
  </div>
</template>

<style scoped>
.composer {
  display: grid;
  grid-template-columns: 1fr auto;
  align-items: end;
  gap: 12px;
  padding: 14px 18px 18px;
  border-top: 1px solid #29435c;
  background: #0a192ae8;
}
.composer :deep(.el-textarea__inner) {
  color: #edf5ff;
  border: 1px solid #29435c;
  background: #071524;
  box-shadow: none;
}
@media (max-width: 680px) {
  .composer {
    grid-template-columns: 1fr;
  }
  .composer .el-button {
    width: 100%;
  }
}
</style>
