import { afterEach, describe, expect, it, vi } from 'vitest'

import { streamAssistantChat } from '@/api'

describe('AI 助手 SSE 客户端', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('解析跨数据块 SSE 并携带认证信息', async () => {
    window.localStorage.setItem('pvi.auth.token', 'test-token')
    const encoder = new TextEncoder()
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode('data: {"type":"start"}\n'))
        controller.enqueue(encoder.encode('\ndata: {"type":"delta","content":"你好"}\n\n'))
        controller.enqueue(encoder.encode('data: {"type":"done"}\n\n'))
        controller.close()
      },
    })
    const fetchMock = vi
      .fn()
      .mockResolvedValue(
        new Response(stream, { status: 200, headers: { 'Content-Type': 'text/event-stream' } }),
      )
    vi.stubGlobal('fetch', fetchMock)
    const events: string[] = []
    await streamAssistantChat(
      'conversation-1',
      { request_id: 'request-1', content: '你好' },
      (event) => events.push(event.type),
    )
    expect(events).toEqual(['start', 'delta', 'done'])
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/assistant/conversations/conversation-1/chat/'),
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({ Authorization: 'Token test-token' }),
      }),
    )
  })

  it('接口错误返回中文安全信息', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: '当前账号已有助手请求正在执行。' }), {
          status: 429,
          headers: { 'Content-Type': 'application/json' },
        }),
      ),
    )
    await expect(
      streamAssistantChat('conversation-1', { request_id: 'request-2', content: '问题' }, vi.fn()),
    ).rejects.toThrow('当前账号已有助手请求正在执行')
  })
})
