import ElementPlus from 'element-plus'
import { createApp, nextTick } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  cancelAssistantChat,
  createAssistantConversation,
  getAssistantConversations,
  getAssistantMessages,
  getAssistantModels,
  streamAssistantChat,
  updateAssistantConversation,
} from '@/api'
import AIAssistantView from '@/views/AIAssistantView.vue'

vi.mock('vue-router', () => ({
  useRoute: () => ({
    query: { product_id: '1', start_date: '2026-10-01', end_date: '2026-10-29' },
  }),
}))
vi.mock('@/api', () => ({
  getAssistantModels: vi.fn(),
  getAssistantConversations: vi.fn(),
  getAssistantMessages: vi.fn(),
  createAssistantConversation: vi.fn(),
  updateAssistantConversation: vi.fn(),
  deleteAssistantConversation: vi.fn(),
  cancelAssistantChat: vi.fn(),
  streamAssistantChat: vi.fn(),
  getProducts: vi.fn(),
  getSources: vi.fn(),
  createAssistantModel: vi.fn(),
  updateAssistantModel: vi.fn(),
  deleteAssistantModel: vi.fn(),
  testAssistantModel: vi.fn(),
}))

const conversation = {
  id: 'conversation-1',
  title: '信号问题',
  model_profile: 8,
  use_default_model: false,
  model_display: '测试模型',
  status: 'IDLE' as const,
  context: {},
  last_message_at: null,
  message_count: 0,
  created_at: '2026-10-29T00:00:00Z',
  updated_at: '2026-10-29T00:00:00Z',
}
const product = {
  id: 1,
  brand: { id: 1, name: '荣耀', code: 'HONOR', is_active: true },
  name: '荣耀 Power2',
  normalized_name: 'HONOR_POWER2',
  series: 'Power',
  model_code: '',
  release_date: null,
  description: '',
  is_active: true,
  variants: [],
}

async function flush() {
  await new Promise((resolve) => setTimeout(resolve, 0))
  await nextTick()
  await new Promise((resolve) => setTimeout(resolve, 0))
}

function mount() {
  const container = document.createElement('div')
  document.body.appendChild(container)
  const app = createApp(AIAssistantView)
  app.use(ElementPlus)
  app.mount(container)
  return { app, container }
}

describe('AI 智能助手工作台', () => {
  beforeEach(async () => {
    document.body.innerHTML = ''
    vi.stubGlobal('crypto', { randomUUID: vi.fn(() => `request-${Math.random()}`) })
    vi.mocked(getAssistantModels).mockResolvedValue({
      default_model: {
        id: null,
        name: '使用个人默认模型',
        model: 'default-model',
        provider: 'openai_compatible',
        configured: true,
      },
      results: [
        {
          id: 8,
          name: '测试模型',
          provider: 'openai_compatible',
          base_url: 'https://example.com/v1',
          model: 'test-model',
          api_key_configured: true,
          api_key_masked: '••••1234',
          thinking_mode: '',
          temperature: '0.00',
          timeout_seconds: 60,
          max_output_tokens: 1500,
          is_active: true,
          created_at: '',
          updated_at: '',
        },
      ],
    })
    vi.mocked(getAssistantConversations).mockResolvedValue([conversation])
    vi.mocked(getAssistantMessages).mockResolvedValue([])
    vi.mocked(createAssistantConversation).mockResolvedValue(conversation)
    vi.mocked(updateAssistantConversation).mockResolvedValue(conversation)
    vi.mocked(cancelAssistantChat).mockResolvedValue({ status: 'CANCELLED' })
    const api = await import('@/api')
    vi.mocked(api.getProducts).mockResolvedValue({
      count: 1,
      next: null,
      previous: null,
      results: [product],
    })
    vi.mocked(api.getSources).mockResolvedValue({
      count: 0,
      next: null,
      previous: null,
      results: [],
    })
    vi.mocked(streamAssistantChat).mockImplementation(async (_id, _payload, onEvent) => {
      onEvent({ type: 'start', message_id: 'assistant-1' })
      onEvent({
        type: 'tool',
        tool: 'get_issue_statistics',
        evidence: [
          {
            review_id: 9,
            title: '真实反馈',
            content: '地下车库信号不稳定',
            source_url: 'https://example.com/thread/9',
            published_at: null,
          },
        ],
      })
      onEvent({ type: 'delta', content: '主要问题是信号。' })
      onEvent({ type: 'done', message_id: 'assistant-1' })
    })
  })

  it('加载会话、模型和筛选器', async () => {
    const { app, container } = mount()
    await flush()
    expect(container.textContent).toContain('AI 智能助手')
    expect(container.textContent).toContain('信号问题')
    expect(container.textContent).toContain('荣耀 Power2')
    expect(container.textContent).toContain('测试模型')
    app.unmount()
  })

  it('发送问题时携带驾驶舱筛选并展示流式证据', async () => {
    const { app, container } = mount()
    await flush()
    const textarea = container.querySelector('textarea') as HTMLTextAreaElement
    textarea.value = '最近有哪些主要问题？'
    textarea.dispatchEvent(new Event('input', { bubbles: true }))
    await nextTick()
    const send = [...container.querySelectorAll('button')].find((item) =>
      item.textContent?.includes('发送'),
    )
    send?.click()
    await flush()
    expect(streamAssistantChat).toHaveBeenCalledWith(
      'conversation-1',
      expect.objectContaining({
        content: '最近有哪些主要问题？',
        product_id: 1,
        start_date: '2026-10-01',
        end_date: '2026-10-29',
      }),
      expect.any(Function),
      expect.any(AbortSignal),
    )
    expect(container.textContent).toContain('主要问题是信号')
    expect(container.textContent).toContain('地下车库信号不稳定')
    app.unmount()
  })

  it('模型选择更新会话且模型管理器可打开', async () => {
    const { app, container } = mount()
    await flush()
    const manage = [...container.querySelectorAll('button')].find((item) =>
      item.textContent?.includes('模型管理'),
    )
    manage?.click()
    await nextTick()
    expect(document.body.textContent).toContain('助手模型管理')
    app.unmount()
  })
})
