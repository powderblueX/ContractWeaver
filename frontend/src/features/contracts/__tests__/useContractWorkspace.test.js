/** @file 验证本组件或状态模块的交互、异常和资源清理；不调用真实模型。 */
import { describe, expect, it, vi } from 'vitest'
import { useContractWorkspace } from '../useContractWorkspace'
import { contractApi } from '../contractApi'

vi.mock('../contractApi', () => ({
  contractApi: {
    create: vi.fn(),
    list: vi.fn(),
    review: vi.fn(),
    get: vi.fn(),
    activity: vi.fn(),
    analyze: vi.fn(),
  },
}))

describe('workspace state', () => {
  it('keeps observing a server operation when a later progress poll fails', async () => {
    vi.useFakeTimers()
    const workflow = useContractWorkspace()
    workflow.workspace.value = { id: 'network-task', revision: 1 }
    contractApi.analyze.mockRejectedValue(new TypeError('network lost'))
    contractApi.activity
      .mockResolvedValueOnce({ action: 'analyze', status: 'running' })
      .mockRejectedValue(new Error('poll offline'))
    contractApi.get.mockResolvedValue({ id: 'network-task', revision: 1 })
    contractApi.list.mockResolvedValue([])
    try {
      await workflow.analyze()
      await vi.advanceTimersByTimeAsync(1100)
      expect(workflow.activity.value.status).toBe('running')
      expect(workflow.progressWarning.value).toContain('暂时无法读取进度')
      expect(vi.getTimerCount()).toBeGreaterThan(0)
      contractApi.activity.mockResolvedValue({ action: 'analyze', status: 'completed' })
      await vi.advanceTimersByTimeAsync(1100)
      expect(vi.getTimerCount()).toBe(0)
    } finally {
      workflow.reset()
      vi.useRealTimers()
    }
  })
  it('refuses strict retry preparation when current execution status cannot be verified', async () => {
    const workflow = useContractWorkspace()
    const original = { id: 'strict-task', revision: 1 }
    workflow.workspace.value = original
    contractApi.get.mockResolvedValue({ ...original, revision: 2 })
    contractApi.activity.mockRejectedValue(new Error('status offline'))
    const result = await workflow.open(original.id, true)
    expect(result).toBeNull()
    expect(workflow.workspace.value).toEqual(original)
    expect(workflow.error.value).toContain('status offline')
    workflow.reset()
  })
  it('polls factual progress while a model request is pending and clears timers afterwards', async () => {
    vi.useFakeTimers()
    let resolve
    const workflow = useContractWorkspace()
    workflow.workspace.value = { id: 'live-task', revision: 1 }
    contractApi.analyze.mockImplementation(
      () =>
        new Promise((done) => {
          resolve = done
        })
    )
    contractApi.activity.mockResolvedValue({
      action: 'analyze',
      status: 'running',
      requests_started: 1,
      responses_received: 0,
    })
    contractApi.list.mockResolvedValue([])
    try {
      const pending = workflow.analyze()
      await vi.advanceTimersByTimeAsync(1100)
      expect(workflow.busyAction.value).toContain('分析')
      expect(workflow.elapsedSeconds.value).toBe(1)
      expect(workflow.activity.value.requests_started).toBe(1)
      resolve({
        id: 'live-task',
        revision: 2,
        last_run: { action: 'analyze', status: 'completed', requests_started: 1, responses_received: 1 },
      })
      await pending
      expect(workflow.busyAction.value).toBe('')
      expect(workflow.activity.value.responses_received).toBe(1)
      expect(vi.getTimerCount()).toBe(0)
    } finally {
      workflow.reset()
      vi.useRealTimers()
    }
  })
  it('retains a committed change if refreshing the task list fails', async () => {
    const workflow = useContractWorkspace()
    const saved = { id: 'task-one', revision: 2, fields: [] }
    contractApi.create.mockResolvedValue(saved)
    contractApi.list.mockRejectedValue(new Error('offline'))
    const result = await workflow.create({ source_text: 'record' })
    expect(result).toEqual(saved)
    expect(workflow.workspace.value).toEqual(saved)
    expect(workflow.error.value).toContain('操作已保存')
    expect(workflow.busyAction.value).toBe('')
  })

  it('keeps the current state when a stale edit is rejected', async () => {
    const workflow = useContractWorkspace()
    workflow.workspace.value = { id: 'task-one', revision: 5 }
    workflow.preview.value = { revision: 5, text: 'existing preview' }
    contractApi.review.mockRejectedValue(new Error('页面已过期'))
    await workflow.review([{ name: '金额', value: '8000元' }])
    expect(workflow.workspace.value.revision).toBe(5)
    expect(workflow.preview.value.revision).toBe(5)
    expect(workflow.error.value).toContain('页面已过期')
  })
})
