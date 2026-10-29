<script setup lang="ts">
import { Setting } from '@element-plus/icons-vue'
import type { AssistantModelList } from '@/types/api'

defineProps<{ modelValue: number | null; models?: AssistantModelList; disabled?: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [value: number | null]; manage: [] }>()
</script>

<template>
  <div class="model-selector">
    <el-select
      :model-value="modelValue"
      :disabled="disabled"
      placeholder="选择助手模型"
      @update:model-value="emit('update:modelValue', $event)"
    >
      <el-option
        :value="null"
        :label="
          models?.default_model.configured
            ? `个人默认 · ${models.default_model.model}`
            : '个人默认模型（未配置）'
        "
        :disabled="!models?.default_model.configured"
      />
      <el-option
        v-for="item in models?.results"
        :key="item.id"
        :value="item.id"
        :label="`${item.name} · ${item.model}`"
      />
    </el-select>
    <el-button :icon="Setting" @click="emit('manage')">模型管理</el-button>
  </div>
</template>

<style scoped>
.model-selector {
  display: flex;
  gap: 10px;
}
.model-selector .el-select {
  width: min(330px, 55vw);
}
</style>
