/** @file 验证服务配置、网络与并发错误的恢复建议。 */
import { describe, expect, it } from 'vitest'
import { failureGuidance } from '../failureGuidance'

describe('failure recovery guidance', () => {
  it('preserves safe provider guidance and sends configuration problems to the maintainer', () => {
    const result = failureGuidance({
      error: { code: 'model_auth', message: '模型认证失败', hint: '联系部署者', retryable: false },
    })
    expect(result.title).toContain('维护者')
    expect(result.hint).toBe('联系部署者')
    expect(result.retryable).toBe(false)
  })
  it('offers connection guidance without asserting that VPN caused the failure', () => {
    const result = failureGuidance({ code: 'browser_network', message: '连接失败', hint: '检查网络与代理' })
    expect(result.title).toContain('连接')
    expect(result.hint).toContain('检查')
  })
  it('requires refreshing conflicting state before retrying', () => {
    const result = failureGuidance({ status: 409, message: '操作冲突' })
    expect(result.retryable).toBe(false)
    expect(result.hint).toContain('刷新')
  })
})
