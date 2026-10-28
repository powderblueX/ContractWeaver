/** @file 验证网络错误提示、服务端故障分类和内部错误脱敏。 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { requestJson } from '../../../shared/httpClient'

vi.mock('../../../shared/authSession', () => ({ getSession: () => null, clearSession: vi.fn() }))
afterEach(() => vi.unstubAllGlobals())

describe('HTTP recovery information', () => {
  it('classifies browser network failures and suggests refreshing before resubmission', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    await expect(requestJson('/workspaces')).rejects.toMatchObject({
      code: 'browser_network',
      hint: expect.stringContaining('刷新任务状态'),
    })
  })
  it('preserves a safe structured model error', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValue(
          new Response(
            JSON.stringify({
              error: { code: 'model_schema', message: '模型格式错误', hint: '重试失败批次', retryable: true },
            }),
            { status: 503 }
          )
        )
    )
    await expect(requestJson('/workspaces')).rejects.toMatchObject({
      status: 503,
      error: { code: 'model_schema' },
      message: '模型格式错误',
    })
  })
  it('hides unclassified internal server details', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValue(
          new Response(JSON.stringify({ detail: 'private database path and stack trace' }), { status: 500 })
        )
    )
    await expect(requestJson('/workspaces')).rejects.toThrow('服务暂时无法完成请求')
  })
  it('preserves deliberate cancellation', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new DOMException('cancelled', 'AbortError')))
    await expect(requestJson('/workspaces')).rejects.toMatchObject({ name: 'AbortError' })
  })
})
