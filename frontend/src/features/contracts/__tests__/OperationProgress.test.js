/** @file 验证本组件或状态模块的交互、异常和资源清理；不调用真实模型。 */
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import OperationProgress from '../components/OperationProgress.vue'

describe('factual operation progress', () => {
  it('keeps all-failed progress at zero and displays the public failure reason', () => {
    const wrapper = mount(OperationProgress, {
      props: {
        activity: {
          status: 'partial',
          batches: [{ index: 1, status: 'failed' }],
          harness: {
            plan: [],
            limits: { requests: 10 },
            steps: [
              {
                index: 1,
                label: '字段提取',
                status: 'failed',
                error_type: 'ModelUnavailable',
                error: { message: '模型返回结构无效', hint: '重试失败批次' },
              },
            ],
          },
        },
      },
    })
    expect(wrapper.find('progress').attributes('value')).toBe('0')
    expect(wrapper.text()).toContain('自动填写未完成')
    expect(wrapper.text()).toContain('模型返回结构无效')
    expect(wrapper.text()).not.toContain('ModelUnavailable')
    wrapper.unmount()
  })
  it('shows actual main-agent tool choice rather than presenting capabilities as a fixed plan', () => {
    const wrapper = mount(OperationProgress, {
      props: {
        activity: {
          status: 'running',
          harness: {
            plan_kind: 'capability_catalog',
            plan: [],
            thinking_mode: 'disabled',
            reasoning_effort: 'provider_default',
            model_requests: 3,
            limits: { requests: 512 },
            steps: [
              {
                index: 1,
                label: '主控规划',
                status: 'completed',
                chosen_action: 'repair_fields',
                target_count: 2,
                decision_summary: '原文已有最终金额，修正两个旧报价字段。',
              },
            ],
          },
        },
      },
    })
    expect(wrapper.text()).toContain('不是固定执行顺序')
    expect(wrapper.text()).toContain('主控选择：定向修正')
    expect(wrapper.text()).toContain('2 个目标字段')
    wrapper.unmount()
  })
  it('distinguishes durable execution summaries from internal chain of thought', () => {
    const wrapper = mount(OperationProgress, {
      props: {
        activity: {
          status: 'interrupted',
          harness: {
            plan: [{ name: 'extract_fields', label: '字段提取' }],
            thinking_mode: 'enabled',
            reasoning_effort: 'high',
            model_requests: 1,
            limits: { requests: 10 },
            token_usage: { total_tokens: 42 },
            steps: [
              {
                index: 1,
                label: '字段提取',
                status: 'completed',
                decision_summary: '原文未确定日期，等待补充。',
                elapsed_seconds: 2,
              },
            ],
          },
        },
      },
    })
    expect(wrapper.text()).toContain('处理未完成')
    expect(wrapper.text()).toContain('不是内部完整思维链')
    expect(wrapper.text()).toContain('原文未确定日期，等待补充。')
    expect(wrapper.text()).toContain('42')
    expect(wrapper.find('.loading-spinner').exists()).toBe(false)
    wrapper.unmount()
  })
  it('shows a spinner, elapsed time, actual calls and terminal batch counts', () => {
    const wrapper = mount(OperationProgress, {
      props: {
        label: '提取并复核',
        elapsed: 12,
        activity: {
          requests_started: 3,
          responses_received: 2,
          requests_failed: 0,
          model: 'test-model',
          batches: [
            { index: 1, status: 'completed' },
            { index: 2, status: 'failed' },
            { index: 3, status: 'extracting' },
          ],
        },
      },
    })
    expect(wrapper.find('.loading-spinner').exists()).toBe(true)
    expect(wrapper.text()).toContain('12 秒')
    expect(wrapper.text()).toContain('实际模型请求 3 次')
    expect(wrapper.find('progress').attributes('value')).toBe('1')
    expect(wrapper.text()).toContain('成功 1 批 · 失败 1 批')
    wrapper.unmount()
  })
  it('does not invent a percentage while waiting for the server', () => {
    const wrapper = mount(OperationProgress, { props: { label: '分析记录', elapsed: 3 } })
    expect(wrapper.find('progress').exists()).toBe(false)
    expect(wrapper.find('.indeterminate-track').exists()).toBe(true)
    expect(wrapper.text()).not.toContain('100%')
    wrapper.unmount()
  })
})
