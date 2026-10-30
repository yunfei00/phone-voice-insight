<script setup lang="ts">
import { ChatDotRound, Clock } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, nextTick, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import {
  cancelAssistantChat,
  createAssistantConversation,
  deleteAssistantConversation,
  getAssistantConversations,
  getAssistantMessages,
  getProducts,
  getSources,
  streamAssistantChat,
  updateAssistantConversation,
} from '@/api'
import AssistantComposer from '@/components/assistant/AssistantComposer.vue'
import AssistantEvidence from '@/components/assistant/AssistantEvidence.vue'
import AssistantMarkdown from '@/components/assistant/AssistantMarkdown.vue'
import AssistantSidebar from '@/components/assistant/AssistantSidebar.vue'
import type {
  AssistantConversation,
  AssistantMessage,
  DataSource,
  Product,
} from '@/types/api'

const route = useRoute()
const conversations = ref<AssistantConversation[]>([])
const activeId = ref('')
const messages = ref<AssistantMessage[]>([])
const products = ref<Product[]>([])
const sources = ref<DataSource[]>([])
const productId = ref<number>()
const sourceId = ref<number>()
const dateRange = ref<[string, string]>()
const draft = ref('')
const loading = ref(false)
const messagesLoading = ref(false)
const generating = ref(false)
const chatScroll = ref<HTMLElement>()
let controller: AbortController | undefined

const activeConversation = computed(() =>
  conversations.value.find((item) => item.id === activeId.value),
)
const quickQuestions = [
  '最近七天新增了哪些问题？',
  '哪些问题值得重点关注？',
  '给我总结当前产品的主要用户声音。',
  '荣耀 Power 和荣耀 Power2 哪个用户反馈更好？',
]

function queryString(name: string): string | undefined {
  const value = route.query[name]
  return Array.isArray(value) ? value[0] : value ? String(value) : undefined
}

async function loadBase() {
  loading.value = true
  try {
    const [conversationData, productData, sourceData] = await Promise.all([
      getAssistantConversations(),
      getProducts({ page_size: 100 }),
      getSources({ page_size: 100 }),
    ])
    conversations.value = conversationData
    products.value = productData.results
    sources.value = sourceData.results
    productId.value = queryString('product_id') ? Number(queryString('product_id')) : undefined
    sourceId.value = queryString('source_id') ? Number(queryString('source_id')) : undefined
    const start = queryString('start_date')
    const end = queryString('end_date')
    if (start && end) dateRange.value = [start, end]
    if (queryString('question')) draft.value = queryString('question') || ''
    if (conversationData.length) await selectConversation(conversationData[0].id)
    else await newConversation()
  } finally {
    loading.value = false
  }
}

async function refreshConversations() {
  conversations.value = await getAssistantConversations()
}

async function newConversation() {
  const item = await createAssistantConversation({
    title: '新对话',
    use_default_model: true,
    context: { product_id: productId.value, source_id: sourceId.value },
  })
  conversations.value.unshift(item)
  await selectConversation(item.id)
}

async function selectConversation(id: string) {
  activeId.value = id
  messagesLoading.value = true
  try {
    messages.value = await getAssistantMessages(id)
    await scrollToBottom()
  } finally {
    messagesLoading.value = false
  }
}

async function renameConversation(item: AssistantConversation) {
  const { value } = await ElMessageBox.prompt('请输入新的会话名称', '重命名会话', {
    inputValue: item.title,
    inputValidator: (text) => Boolean(text.trim()) || '名称不能为空',
  })
  await updateAssistantConversation(item.id, { title: value.trim() })
  await refreshConversations()
}

async function removeConversation(item: AssistantConversation) {
  await ElMessageBox.confirm(`确认删除会话“${item.title}”？`, '删除确认', { type: 'warning' })
  await deleteAssistantConversation(item.id)
  conversations.value = conversations.value.filter((current) => current.id !== item.id)
  if (activeId.value === item.id) {
    if (conversations.value.length) await selectConversation(conversations.value[0].id)
    else await newConversation()
  }
}

function optimisticMessage(
  role: 'USER' | 'ASSISTANT',
  content: string,
  requestId: string | null,
): AssistantMessage {
  return {
    id: crypto.randomUUID(),
    role,
    content,
    request_id: requestId,
    status: role === 'ASSISTANT' ? 'RUNNING' : 'COMPLETED',
    model_name_snapshot: activeConversation.value?.model_display || '',
    provider_snapshot: '',
    evidence: [],
    prompt_tokens: null,
    completion_tokens: null,
    total_tokens: null,
    latency_ms: null,
    error_code: '',
    error_message: '',
    created_at: new Date().toISOString(),
  }
}

async function send() {
  const content = draft.value.trim()
  if (!content || !activeId.value || generating.value) return
  const requestId = crypto.randomUUID()
  const user = optimisticMessage('USER', content, null)
  const answer = optimisticMessage('ASSISTANT', '', requestId)
  messages.value.push(user, answer)
  draft.value = ''
  generating.value = true
  controller = new AbortController()
  await scrollToBottom()
  try {
    await streamAssistantChat(
      activeId.value,
      {
        request_id: requestId,
        content,
        product_id: productId.value,
        source_id: sourceId.value,
        start_date: dateRange.value?.[0],
        end_date: dateRange.value?.[1],
      },
      (event) => {
        if (event.type === 'delta') answer.content += event.content || ''
        if (event.type === 'tool' && event.evidence) answer.evidence = event.evidence
        if (event.type === 'error') {
          answer.status = 'FAILED'
          answer.error_code = event.code || 'ASSISTANT_ERROR'
          answer.error_message = event.message || '助手处理失败'
          ElMessage.error(answer.error_message)
        }
        if (event.type === 'cancelled') answer.status = 'CANCELLED'
        if (event.type === 'done') answer.status = 'COMPLETED'
        void scrollToBottom()
      },
      controller.signal,
    )
  } catch (error) {
    if (!(error instanceof DOMException && error.name === 'AbortError')) {
      answer.status = 'FAILED'
      answer.error_message = error instanceof Error ? error.message : '助手请求失败'
      ElMessage.error(answer.error_message)
    }
  } finally {
    generating.value = false
    controller = undefined
    try {
      await Promise.all([selectConversation(activeId.value), refreshConversations()])
    } catch {
      // Keep the visible local error when refreshing conversation history fails.
    }
  }
}

async function stop() {
  if (!activeId.value) return
  try {
    await cancelAssistantChat(activeId.value)
  } finally {
    controller?.abort()
    generating.value = false
  }
}

async function scrollToBottom() {
  await nextTick()
  if (chatScroll.value) chatScroll.value.scrollTop = chatScroll.value.scrollHeight
}

function useQuestion(question: string) {
  draft.value = question
}

onMounted(loadBase)
</script>

<template>
  <div class="assistant-page">
    <AssistantSidebar
      :conversations="conversations"
      :active-id="activeId"
      :loading="loading"
      @create="newConversation"
      @select="selectConversation"
      @rename="renameConversation"
      @delete="removeConversation"
    />
    <main class="assistant-workspace">
      <header class="assistant-header">
        <div>
          <h1>
            <el-icon><ChatDotRound /></el-icon>AI 智能助手
          </h1>
          <p>基于真实用户声音数据回答，统计结论均可追溯</p>
        </div>
      </header>
      <section class="assistant-filters">
        <el-select v-model="productId" clearable placeholder="全部产品"
          ><el-option v-for="item in products" :key="item.id" :label="item.name" :value="item.id"
        /></el-select>
        <el-select v-model="sourceId" clearable placeholder="全部来源"
          ><el-option v-for="item in sources" :key="item.id" :label="item.name" :value="item.id"
        /></el-select>
        <el-date-picker
          v-model="dateRange"
          type="daterange"
          value-format="YYYY-MM-DD"
          range-separator="至"
          start-placeholder="开始日期"
          end-placeholder="结束日期"
        />
        <span class="scope-note"
          ><el-icon><Clock /></el-icon>未选择时间时默认最近 30 天</span
        >
      </section>
      <section ref="chatScroll" class="chat-scroll" v-loading="messagesLoading">
        <div v-if="!messages.length && !messagesLoading" class="empty-chat">
          <div class="assistant-orb">
            <el-icon><ChatDotRound /></el-icon>
          </div>
          <h2>从真实用户声音中获得答案</h2>
          <p>可以询问主要问题、产品对比、近期趋势或要求查看原始证据。</p>
          <div class="quick-grid">
            <button v-for="item in quickQuestions" :key="item" @click="useQuestion(item)">
              {{ item }}
            </button>
          </div>
        </div>
        <article
          v-for="item in messages"
          :key="item.id"
          class="message"
          :class="item.role.toLowerCase()"
        >
          <div class="message-avatar">{{ item.role === 'USER' ? '我' : 'AI' }}</div>
          <div class="message-body">
            <AssistantMarkdown
              :content="item.content || (item.status === 'RUNNING' ? '正在查询真实数据…' : '')"
            />
            <el-alert
              v-if="item.status === 'FAILED'"
              :title="item.error_message || '回答生成失败'"
              type="error"
              :closable="false"
            />
            <el-tag v-if="item.status === 'CANCELLED'" type="info">已停止生成</el-tag>
            <AssistantEvidence :items="item.evidence" />
            <small v-if="item.role === 'ASSISTANT' && item.model_name_snapshot"
              >{{ item.model_name_snapshot
              }}<span v-if="item.total_tokens"> · {{ item.total_tokens }} Token</span></small
            >
          </div>
        </article>
      </section>
      <div v-if="messages.length" class="quick-row">
        <button v-for="item in quickQuestions.slice(0, 3)" :key="item" @click="useQuestion(item)">
          {{ item }}
        </button>
      </div>
      <AssistantComposer
        v-model="draft"
        :generating="generating"
        :disabled="loading || !activeId"
        @send="send"
        @stop="stop"
      />
    </main>
  </div>
</template>

<style scoped>
.assistant-page {
  display: grid;
  grid-template-columns: 270px minmax(0, 1fr);
  height: calc(100vh - 104px);
  min-height: 660px;
  overflow: hidden;
  border: 1px solid #29435c;
  border-radius: 14px;
  background: #071524;
  box-shadow: 0 18px 50px #020a1373;
}
.assistant-workspace {
  display: flex;
  min-width: 0;
  flex-direction: column;
}
.assistant-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  padding: 18px 22px;
  border-bottom: 1px solid #29435c;
  background: #0a192a;
}
.assistant-header h1 {
  display: flex;
  align-items: center;
  gap: 9px;
  margin: 0;
  color: #edf5ff;
  font-size: 22px;
}
.assistant-header h1 .el-icon {
  color: #35b9f0;
}
.assistant-header p {
  margin: 5px 0 0;
  color: #96adc6;
  font-size: 13px;
}
.assistant-filters {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 22px;
  border-bottom: 1px solid #29435c;
  background: #0a192a;
}
.assistant-filters .el-select {
  width: 170px;
}
.scope-note {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: #96adc6;
  font-size: 12px;
}
.chat-scroll {
  min-height: 0;
  flex: 1;
  overflow: auto;
  padding: 24px max(22px, calc((100% - 900px) / 2));
}
.empty-chat {
  display: flex;
  max-width: 760px;
  min-height: 100%;
  margin: auto;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
}
.assistant-orb {
  display: grid;
  width: 72px;
  height: 72px;
  place-items: center;
  border: 1px solid #35b9f0;
  border-radius: 22px;
  background: #12283f;
  color: #42d6c6;
  box-shadow: 0 0 34px #35b9f036;
  font-size: 32px;
}
.empty-chat h2 {
  margin: 20px 0 6px;
  color: #edf5ff;
}
.empty-chat p {
  color: #96adc6;
}
.quick-grid {
  display: grid;
  width: 100%;
  margin-top: 18px;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}
.quick-grid button,
.quick-row button {
  padding: 10px 13px;
  border: 1px solid #29435c;
  border-radius: 9px;
  background: #12283f;
  color: #cfe2f5;
  cursor: pointer;
}
.quick-grid button:hover,
.quick-row button:hover {
  border-color: #35b9f0;
  color: #fff;
}
.message {
  display: flex;
  gap: 12px;
  margin-bottom: 20px;
}
.message.user {
  flex-direction: row-reverse;
}
.message-avatar {
  display: grid;
  width: 36px;
  height: 36px;
  flex: 0 0 36px;
  place-items: center;
  border-radius: 11px;
  background: #12283f;
  color: #42d6c6;
  font-weight: 700;
}
.message.user .message-avatar {
  background: #35b9f0;
  color: #071524;
}
.message-body {
  max-width: min(780px, calc(100% - 50px));
  padding: 14px 17px;
  border: 1px solid #29435c;
  border-radius: 4px 14px 14px;
  background: #12283f;
  color: #cfe2f5;
}
.message.user .message-body {
  border-color: #35b9f066;
  border-radius: 14px 4px 14px 14px;
  background: #123654;
}
.message-body small {
  display: block;
  margin-top: 10px;
  color: #7893ad;
}
.quick-row {
  display: flex;
  gap: 8px;
  overflow-x: auto;
  padding: 7px 18px;
  border-top: 1px solid #29435c;
  background: #0a192a;
}
.quick-row button {
  flex: 0 0 auto;
  padding: 7px 11px;
  font-size: 12px;
}
@media (max-width: 900px) {
  .assistant-page {
    grid-template-columns: 1fr;
    height: auto;
    min-height: calc(100vh - 90px);
    overflow: visible;
  }
  .assistant-page :deep(.conversation-sidebar) {
    max-height: 220px;
    border-right: 0;
    border-bottom: 1px solid #29435c;
  }
  .assistant-workspace {
    min-height: 720px;
  }
  .assistant-header,
  .assistant-filters {
    align-items: stretch;
    flex-direction: column;
  }
  .assistant-filters .el-select,
  .assistant-filters :deep(.el-date-editor) {
    width: 100%;
  }
  .chat-scroll {
    padding: 18px 12px;
  }
}
@media (max-width: 560px) {
  .quick-grid {
    grid-template-columns: 1fr;
  }
  .assistant-header {
    padding: 14px;
  }
}
</style>
