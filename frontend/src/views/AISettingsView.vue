<script setup lang="ts">
import type { FormInstance, FormRules } from 'element-plus'
import { ElMessage } from 'element-plus'
import { onMounted, reactive, ref } from 'vue'

import {
  getPersonalAIConfiguration,
  getAssistantModels,
  createAssistantModel,
  updateAssistantModel,
  testAssistantModel,
  selectAssistantModel,
  getOllamaModels,
  savePersonalAIConfiguration,
  testPersonalAIConfiguration,
} from '@/api'
import type { AIConfigurationPayload, AssistantModelList, AssistantModelProfile } from '@/types/api'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const assistantModels = ref<AssistantModelList>()
const selectedProfileId = ref<number | null>(null)
const assistantSelection = ref<number | null>(null)
const assigning = ref(false)
const loading = ref(false)
const saving = ref(false)
const testing = ref(false)
const discovering = ref(false)
const ollamaModels = ref<string[]>([])
const configured = ref(false)
const maskedKey = ref('')
const updatedAt = ref<string | null>(null)
const formRef = ref<FormInstance>()
const form = reactive<AIConfigurationPayload>({
  provider: 'openai_compatible',
  base_url: '',
  api_key: '',
  model: '',
  thinking_mode: '',
  timeout_seconds: 60,
  temperature: 0,
  max_output_tokens: 1500,
  is_active: true,
})
const rules: FormRules = {
  base_url: [
    { required: true, message: '请输入服务地址', trigger: 'blur' },
    { type: 'url', message: '请输入完整 URL，例如 https://api.deepseek.com', trigger: 'blur' },
  ],
  api_key: [
    {
      validator: (_rule, value: string, callback: (error?: Error) => void) => {
        callback(
          form.provider === 'ollama' || (configured.value && maskedKey.value) || value
            ? undefined
            : new Error('首次配置必须填写 API Key'),
        )
      },
      trigger: 'blur',
    },
  ],
  model: [{ required: true, message: '请输入模型名称', trigger: 'blur' }],
}

async function loadConfiguration(): Promise<void> {
  loading.value = true
  try {
    const configuration = await getPersonalAIConfiguration()
    Object.assign(form, {
      provider: configuration.provider === 'ollama' ? 'ollama' : 'openai_compatible',
      base_url: configuration.base_url,
      api_key: '',
      model: configuration.model === 'NOT_CONFIGURED' ? '' : configuration.model,
      thinking_mode: configuration.thinking_mode,
      timeout_seconds: configuration.timeout_seconds,
      temperature: Number(configuration.temperature),
      max_output_tokens: configuration.max_output_tokens,
      is_active: configuration.is_active,
    })
    configured.value = configuration.configured
    maskedKey.value = configuration.api_key_masked
    updatedAt.value = configuration.updated_at
  } finally {
    loading.value = false
  }
}

function editProfile(profile: AssistantModelProfile): void {
  selectedProfileId.value = profile.id
  configured.value = profile.api_key_configured
  maskedKey.value = profile.api_key_masked
  Object.assign(form, {
    provider: profile.provider,
    base_url: profile.base_url,
    api_key: '',
    model: profile.model,
    thinking_mode: profile.thinking_mode,
    timeout_seconds: profile.timeout_seconds,
    temperature: Number(profile.temperature),
    max_output_tokens: profile.max_output_tokens,
    is_active: profile.is_active,
  })
}

function newProfile(): void {
  selectedProfileId.value = 0
  configured.value = false
  maskedKey.value = ''
  Object.assign(form, {
    provider: 'openai_compatible',
    base_url: '',
    api_key: '',
    model: '',
    thinking_mode: '',
    timeout_seconds: 60,
    temperature: 0,
    max_output_tokens: 1500,
    is_active: true,
  })
}

async function choosePersonal(): Promise<void> {
  selectedProfileId.value = null
  await loadConfiguration()
}

async function assignAssistantModel(): Promise<void> {
  if (assistantSelection.value === null) return
  assigning.value = true
  try {
    await selectAssistantModel(assistantSelection.value)
    await loadAssistantModels()
    ElMessage.success('智能助手模型已更新，客户下次提问即使用此模型')
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '分配模型失败')
  } finally {
    assigning.value = false
  }
}

async function saveConfiguration(): Promise<boolean> {
  if (!(await formRef.value?.validate().catch(() => false))) return false
  saving.value = true
  try {
    const payload = { ...form }
    if (!payload.api_key) delete payload.api_key
    if (selectedProfileId.value !== null) {
      const profilePayload = {
        ...payload,
        name: selectedProfileId.value
          ? assistantModels.value?.results.find((item) => item.id === selectedProfileId.value)?.name ||
            payload.model
          : `${payload.provider} · ${payload.model}`,
      }
      const saved = selectedProfileId.value
        ? await updateAssistantModel(selectedProfileId.value, profilePayload)
        : await createAssistantModel(profilePayload)
      selectedProfileId.value = saved.id
      configured.value = saved.api_key_configured
      maskedKey.value = saved.api_key_masked
      form.api_key = ''
      await loadAssistantModels()
      ElMessage.success('模型已保存到统一模型库')
    } else {
      const saved = await savePersonalAIConfiguration(payload)
      configured.value = saved.configured
      maskedKey.value = saved.api_key_masked
      updatedAt.value = saved.updated_at
      form.api_key = ''
      ElMessage.success('个人默认模型已保存')
    }
    return true
  } finally {
    saving.value = false
  }
}

async function discoverOllamaModels(): Promise<void> {
  if (form.provider !== 'ollama') return
  if (selectedProfileId.value !== null) {
    ElMessage.info('请先保存该模型，再使用连接测试验证本地 Ollama 服务')
    return
  }
  if (!form.base_url) {
    ElMessage.warning('请先填写 Ollama 服务地址')
    return
  }
  discovering.value = true
  try {
    await savePersonalAIConfiguration({ ...form, api_key: undefined } as AIConfigurationPayload)
    ollamaModels.value = (await getOllamaModels()).models
    if (!ollamaModels.value.length) ElMessage.warning('Ollama 可访问，但没有已安装的模型')
  } catch {
    ElMessage.error('无法读取 Ollama 模型，请确认服务地址可从 Docker 后端访问')
  } finally {
    discovering.value = false
  }
}

async function saveAndTest(): Promise<void> {
  if (!(await saveConfiguration())) return
  testing.value = true
  try {
    const result = selectedProfileId.value
      ? await testAssistantModel(selectedProfileId.value)
      : await testPersonalAIConfiguration()
    ElMessage.success(`连接成功：${result.model}，耗时 ${result.latency_ms} ms`)
  } finally {
    testing.value = false
  }
}

async function loadAssistantModels(): Promise<void> {
  if (auth.isAdmin) {
    assistantModels.value = await getAssistantModels()
    assistantSelection.value = assistantModels.value.assistant_model_id
  }
}

onMounted(() => {
  void loadConfiguration()
  void loadAssistantModels()
})
</script>

<template>
  <div v-loading="loading">
    <header class="page-header">
      <div>
        <h1 class="page-title">AI 配置 · 模型管理</h1>
        <p class="page-description">
          统一管理模型连接参数；个人默认模型供分析任务使用，智能助手模型由管理员在下方指定。
        </p>
      </div>
      <el-tag :type="configured ? 'success' : 'warning'">
        {{ configured ? '已配置' : '未配置' }}
      </el-tag>
    </header>

    <el-alert
      title="API Key 会加密保存，页面和接口只显示末四位；留空表示保留已保存的密钥。"
      type="info"
      show-icon
      :closable="false"
      class="notice"
    />

    <section v-if="auth.isAdmin" class="panel settings-panel model-library">
      <h2>统一模型库</h2>
      <p>在下方同一表单中配置或编辑模型，保存后可分配给智能助手，无需重复填写。</p>
      <div class="model-actions">
        <el-button :type="selectedProfileId === null ? 'primary' : 'default'" @click="choosePersonal"
          >个人默认模型</el-button
        >
        <el-button
          v-for="item in assistantModels?.results"
          :key="item.id"
          :type="selectedProfileId === item.id ? 'primary' : 'default'"
          @click="editProfile(item)"
          >{{ item.model }}</el-button
        >
        <el-button type="success" plain @click="newProfile">+ 新增模型</el-button>
      </div>
      <el-divider />
      <h3>智能助手使用模型</h3>
      <div class="model-actions">
        <el-select
          v-model="assistantSelection"
          placeholder="选择已保存的模型"
          style="width: 300px"
        >
          <el-option
            v-for="item in assistantModels?.results.filter((profile) => profile.is_active)"
            :key="item.id"
            :label="`${item.model}（${item.provider}）`"
            :value="item.id"
          />
        </el-select>
        <el-button type="primary" :loading="assigning" @click="assignAssistantModel"
          >设为智能助手模型</el-button
        >
      </div>
    </section>
    <section class="panel settings-panel">
      <h2>
        {{
          selectedProfileId === null
            ? '个人默认模型'
            : selectedProfileId === 0
              ? '新增模型'
              : '编辑模型'
        }}
      </h2>
      <el-form ref="formRef" :model="form" :rules="rules" label-position="top">
        <el-form-item label="接口类型">
          <el-select v-model="form.provider">
            <el-option label="OpenAI 兼容接口" value="openai_compatible" />
            <el-option label="本地 Ollama" value="ollama" />
          </el-select>
        </el-form-item>
        <el-form-item label="API 地址" prop="base_url">
          <el-input
            v-model="form.base_url"
            :placeholder="
              form.provider === 'ollama'
                ? 'http://host.docker.internal:11434'
                : 'https://api.deepseek.com'
            "
          />
        </el-form-item>
        <el-form-item v-if="form.provider !== 'ollama'" label="API Key" prop="api_key">
          <el-input
            v-model="form.api_key"
            type="password"
            show-password
            autocomplete="new-password"
            :placeholder="maskedKey || '请输入 API Key'"
          />
        </el-form-item>
        <el-form-item label="模型名称" prop="model">
          <el-select
            v-if="form.provider === 'ollama'"
            v-model="form.model"
            filterable
            allow-create
            default-first-option
            placeholder="选择已安装模型或输入模型名称"
          >
            <el-option v-for="name in ollamaModels" :key="name" :label="name" :value="name" />
          </el-select>
          <el-input v-else v-model="form.model" placeholder="例如 deepseek-flash" />
          <el-button
            v-if="form.provider === 'ollama'"
            :loading="discovering"
            @click="discoverOllamaModels"
            >保存并获取本地模型列表</el-button
          >
        </el-form-item>
        <div class="advanced-grid">
          <el-form-item label="思考模式">
            <el-select v-model="form.thinking_mode">
              <el-option label="跟随模型默认" value="" />
              <el-option label="启用" value="enabled" />
              <el-option label="禁用" value="disabled" />
            </el-select>
          </el-form-item>
          <el-form-item label="请求超时（秒）">
            <el-input-number v-model="form.timeout_seconds" :min="10" :max="300" />
          </el-form-item>
          <el-form-item label="Temperature">
            <el-input-number v-model="form.temperature" :min="0" :max="2" :step="0.1" />
          </el-form-item>
          <el-form-item label="最大输出 Tokens">
            <el-input-number v-model="form.max_output_tokens" :min="128" :max="32768" :step="128" />
          </el-form-item>
        </div>
        <el-form-item label="启用配置">
          <el-switch v-model="form.is_active" />
        </el-form-item>
        <div class="actions">
          <el-button type="primary" :loading="saving" @click="saveConfiguration"
            >保存配置</el-button
          >
          <el-button :loading="testing" @click="saveAndTest">保存并测试连接</el-button>
        </div>
      </el-form>
      <p v-if="updatedAt && selectedProfileId === null" class="updated-at">
        最后更新：{{ new Date(updatedAt).toLocaleString() }}
      </p>
    </section>
  </div>
</template>

<style scoped>
.model-library {
  margin-bottom: 18px;
}
.model-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
}
.notice {
  margin-bottom: 18px;
}
.settings-panel {
  max-width: 760px;
}
.advanced-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0 22px;
}
.actions {
  display: flex;
  gap: 10px;
  margin-top: 10px;
}
.updated-at {
  margin: 20px 0 0;
  color: #8a93a5;
  font-size: 13px;
}
@media (max-width: 640px) {
  .advanced-grid {
    grid-template-columns: 1fr;
  }
  .actions {
    align-items: stretch;
    flex-direction: column;
  }
}
</style>
