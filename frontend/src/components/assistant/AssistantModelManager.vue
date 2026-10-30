<script setup lang="ts">
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, reactive, ref, watch } from 'vue'
import axios from 'axios'

import {
  createAssistantModel,
  deleteAssistantModel,
  testAssistantModel,
  updateAssistantModel,
} from '@/api'
import type {
  AssistantModelList,
  AssistantModelProfile,
  AssistantModelProfilePayload,
} from '@/types/api'

const props = defineProps<{ modelValue: boolean; models?: AssistantModelList }>()
const emit = defineEmits<{ 'update:modelValue': [value: boolean]; refresh: [] }>()
const editing = ref<AssistantModelProfile>()
const saving = ref(false)
const testingId = ref<number>()
const form = reactive<AssistantModelProfilePayload>({
  name: '',
  provider: 'openai_compatible',
  base_url: '',
  model: '',
  api_key: '',
  thinking_mode: '',
  temperature: 0,
  timeout_seconds: 60,
  max_output_tokens: 1500,
  is_active: true,
})
const title = computed(() => (editing.value ? '编辑模型配置' : '新增模型配置'))

function reset(item?: AssistantModelProfile) {
  editing.value = item
  Object.assign(form, {
    name: item?.name || '平台智能助手',
    provider: item?.provider || 'openai_compatible',
    base_url: item?.base_url || '',
    model: item?.model || '',
    api_key: '',
    thinking_mode: item?.thinking_mode || '',
    temperature: Number(item?.temperature ?? 0),
    timeout_seconds: item?.timeout_seconds ?? 60,
    max_output_tokens: item?.max_output_tokens ?? 1500,
    is_active: item?.is_active ?? true,
  })
}

function describeError(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const data = error.response?.data
    if (data) return JSON.stringify(data)
    return error.message
  }
  return error instanceof Error ? error.message : '请求失败，请检查服务配置'
}

async function save() {
  if (!form.name.trim() || !form.model.trim()) return ElMessage.warning('请填写配置名称和模型名称')
  saving.value = true
  try {
    const payload = { ...form }
    if (!payload.api_key) delete payload.api_key
    if (editing.value) await updateAssistantModel(editing.value.id, payload)
    else await createAssistantModel(payload)
    ElMessage.success('模型配置已保存')
    reset()
    emit('refresh')
  } catch (error) {
    ElMessage.error(`保存失败：${describeError(error)}`)
  } finally {
    saving.value = false
  }
}

async function test(item: AssistantModelProfile) {
  testingId.value = item.id
  try {
    const result = await testAssistantModel(item.id)
    ElMessage.success(`连接成功，耗时 ${result.latency_ms}ms`)
  } catch (error) {
    ElMessage.error(`模型连接失败：${describeError(error)}`)
  } finally {
    testingId.value = undefined
  }
}

async function remove(item: AssistantModelProfile) {
  await ElMessageBox.confirm(
    `确认删除模型配置“${item.name}”？历史会话仍会保留模型名称。`,
    '删除确认',
    {
      type: 'warning',
    },
  )
  await deleteAssistantModel(item.id)
  if (editing.value?.id === item.id) reset()
  emit('refresh')
}

watch(
  () => props.modelValue,
  (value) => {
    if (value) reset()
  },
)
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    title="助手模型管理"
    width="min(920px, 94vw)"
    @close="emit('update:modelValue', false)"
  >
    <div class="manager-layout">
      <section class="profile-list">
        <div class="default-profile">
          <strong>个人默认模型</strong>
          <span>{{
            models?.default_model.configured ? models.default_model.model : '尚未配置'
          }}</span>
        </div>
        <button
          v-for="item in models?.results"
          :key="item.id"
          class="profile-row"
          @click="reset(item)"
        >
          <span
            ><strong>{{ item.name }}</strong
            ><small>{{ item.provider }} · {{ item.model }}</small></span
          >
          <span class="row-actions" @click.stop>
            <el-button size="small" :loading="testingId === item.id" @click="test(item)"
              >测试</el-button
            >
            <el-button size="small" type="danger" plain @click="remove(item)">删除</el-button>
          </span>
        </button>
        <el-button plain @click="reset()">新增配置</el-button>
      </section>
      <el-form label-position="top" class="profile-form">
        <h3>{{ title }}</h3>
        <div class="form-grid">
          <el-form-item label="配置名称"
            ><el-input v-model="form.name" maxlength="80"
          /></el-form-item>
          <el-form-item label="Provider">
            <el-select v-model="form.provider"
              ><el-option label="OpenAI 兼容接口" value="openai_compatible" /><el-option
                label="本地 Ollama"
                value="ollama"
            /></el-select>
          </el-form-item>
          <el-form-item label="服务地址" class="full"
            ><el-input v-model="form.base_url" placeholder="https://example.com/v1"
          /></el-form-item>
          <el-form-item label="模型名称"><el-input v-model="form.model" /></el-form-item>
          <el-form-item label="API Key">
            <el-input
              v-model="form.api_key"
              type="password"
              show-password
              :placeholder="editing?.api_key_configured ? '留空则保持现有密钥' : '请输入 API Key'"
            />
          </el-form-item>
          <el-form-item label="温度"
            ><el-input-number v-model="form.temperature" :min="0" :max="2" :step="0.1"
          /></el-form-item>
          <el-form-item label="超时（秒）"
            ><el-input-number v-model="form.timeout_seconds" :min="10" :max="300"
          /></el-form-item>
          <el-form-item label="最大输出 Token"
            ><el-input-number v-model="form.max_output_tokens" :min="128" :max="32768"
          /></el-form-item>
          <el-form-item label="思考模式"
            ><el-select v-model="form.thinking_mode"
              ><el-option label="跟随模型" value="" /><el-option
                label="启用"
                value="enabled" /><el-option label="禁用" value="disabled" /></el-select
          ></el-form-item>
        </div>
        <el-alert
          title="模型地址会经过 SSRF 安全校验；本地 Ollama 必须由管理员加入受信任白名单。"
          type="info"
          :closable="false"
        />
        <el-button type="primary" :loading="saving" @click="save">保存配置</el-button>
      </el-form>
    </div>
  </el-dialog>
</template>

<style scoped>
.manager-layout {
  display: grid;
  grid-template-columns: 310px 1fr;
  gap: 22px;
}
.profile-list {
  display: flex;
  flex-direction: column;
  gap: 9px;
}
.default-profile,
.profile-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 12px;
  border: 1px solid #29435c;
  border-radius: 9px;
  background: #0a192a;
  color: #edf5ff;
  text-align: left;
}
.profile-row {
  width: 100%;
  cursor: pointer;
}
.profile-row:hover {
  border-color: #35b9f0;
}
.profile-row span:first-child {
  min-width: 0;
}
.profile-row strong,
.profile-row small,
.default-profile span {
  display: block;
}
.profile-row small,
.default-profile span {
  margin-top: 4px;
  color: #96adc6;
}
.row-actions {
  display: flex;
}
.profile-form {
  padding: 0 4px;
}
.profile-form h3 {
  margin-top: 0;
}
.form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0 14px;
}
.form-grid .full {
  grid-column: 1 / -1;
}
.profile-form .el-alert {
  margin: 4px 0 18px;
}
@media (max-width: 760px) {
  .manager-layout {
    grid-template-columns: 1fr;
  }
  .form-grid {
    grid-template-columns: 1fr;
  }
  .form-grid .full {
    grid-column: auto;
  }
}
</style>
