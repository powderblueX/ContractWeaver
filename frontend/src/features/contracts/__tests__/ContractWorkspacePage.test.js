/** @file 验证本组件或状态模块的交互、异常和资源清理；不调用真实模型。 */
import { mount, flushPromises } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import ContractWorkspacePage from '../ContractWorkspacePage.vue'
import { contractApi } from '../contractApi'

vi.mock('vue-router', () => ({ useRouter: () => ({ replace: vi.fn() }) }))
vi.mock('../../../shared/authSession', () => ({
  /**
   * 返回测试使用的登录会话。
   */
  getSession: () => ({ user: { username: '测试用户' } }),
  clearSession: vi.fn(),
}))
vi.mock('../contractApi', () => ({
  contractApi: Object.fromEntries(
    [
      'health',
      'list',
      'create',
      'get',
      'analyze',
      'selectTemplate',
      'extract',
      'review',
      'preview',
      'generate',
      'browseTemplates',
      'templateDetails',
    ].map((name) => [name, vi.fn()])
  ),
}))

/**
 * 按可见文字触发测试按钮并等待 Vue 异步更新。
 * @param {Object} wrapper Vue 组件测试包装器。
 * @param {string} label 向用户展示的等待状态名称。
 */
const clickButton = async (wrapper, label) => {
  const button = wrapper.findAll('button').find((item) => item.text() === label)
  expect(button, `button ${label}`).toBeDefined()
  await button.trigger('click')
  await flushPromises()
}

describe('record-to-contract user flow', () => {
  it('opens the manual template library after recommendation fails and offers explicit recovery', async () => {
    const task = {
      id: 'manual-fallback',
      title: '会议',
      source_name: '纪要',
      source_text: '双方协商保管物品，约定详细内容后另行确认。',
      revision: 1,
      stage: 'source_ready',
      analysis: null,
      recommendations: [],
      selected_template: null,
      fields: [],
      artifacts: [],
      events: [],
    }
    contractApi.health.mockResolvedValue({ model_configured: true })
    contractApi.list.mockResolvedValue([{ ...task }])
    contractApi.get.mockResolvedValue(task)
    contractApi.analyze.mockRejectedValue(
      Object.assign(new Error('模型连接超时'), {
        error: { code: 'model_timeout', message: '模型连接超时', hint: '检查网络后重试', retryable: true },
      })
    )
    contractApi.browseTemplates.mockResolvedValue({
      items: [{ id: 'manual', name: '保管合同', group: '部委' }],
      total: 1,
      limit: 24,
    })
    const wrapper = mount(ContractWorkspacePage)
    await flushPromises()
    await wrapper.find('.task-row button').trigger('click')
    await flushPromises()
    await clickButton(wrapper, '分析记录并推荐模板')
    expect(wrapper.find('[aria-label="操作恢复指引"]').text()).toContain('检查网络后重试')
    expect(wrapper.findAll('button').some((button) => button.text() === '去模板库手动选择')).toBe(true)
    expect(wrapper.findAll('button').some((button) => button.text() === '重新分析并推荐')).toBe(true)
    expect(wrapper.find('.workflow-tabs .active').text()).toContain('选择模板')
    expect(wrapper.find('.template-library').text()).toContain('保管合同')
    wrapper.unmount()
  })
  it('imports a record, selects a library template, reviews a correction, previews and generates', async () => {
    const field = {
      name: '金额',
      value: '',
      extracted_value: '',
      status: 'missing',
      evidence: [],
      alternatives: [],
      context: '总价：{金额}',
      note: '',
      user_note: '',
      review_issues: [],
    }
    const base = {
      id: 'task',
      title: '采购会议',
      source_name: '协商记录',
      source_text: '双方最终确认金额8000元。',
      revision: 1,
      stage: 'source_ready',
      analysis: null,
      recommendations: [],
      selected_template: null,
      fields: [],
      extraction_failures: [],
      artifacts: [],
      events: [],
    }
    const selected = {
      ...base,
      revision: 2,
      stage: 'template_selected',
      selected_template: { id: 'manual', name: '设备采购合同', field_count: 1 },
      fields: [field],
    }
    const extracted = {
      ...selected,
      revision: 3,
      stage: 'field_review',
      agent_questions: ['请核对金额；未知内容可暂留空。'],
      coordination_warnings: ['定向修正服务暂不可用，已有候选已保留。'],
      fields: [
        {
          ...field,
          value: '9000元',
          extracted_value: '9000元',
          status: 'conflict',
          evidence: [{ line_number: 1, quote: '最终确认金额8000元' }],
          review_issues: ['报价与最终约定不同'],
        },
      ],
    }
    const reviewed = {
      ...extracted,
      revision: 4,
      stage: 'ready_to_generate',
      fields: [{ ...extracted.fields[0], value: '8000元', status: 'confirmed' }],
    }
    const generated = {
      ...reviewed,
      revision: 5,
      stage: 'generated',
      artifacts: [
        {
          id: 'doc-one',
          template: { name: '设备采购合同' },
          source_revision: 4,
          created_at: '2026-01-01T00:00:00Z',
        },
      ],
    }
    contractApi.health.mockResolvedValue({
      model_configured: true,
      model: 'test-model',
      fields_per_batch: 30,
    })
    contractApi.list.mockResolvedValue([])
    contractApi.create.mockResolvedValue(base)
    contractApi.browseTemplates.mockResolvedValue({
      items: [{ id: 'manual', name: '设备采购合同', group: '部委' }],
      total: 1,
      limit: 24,
    })
    contractApi.selectTemplate.mockResolvedValue(selected)
    contractApi.extract.mockResolvedValue(extracted)
    contractApi.review.mockResolvedValue(reviewed)
    contractApi.preview.mockResolvedValue({ revision: 4, text: '总价：8000元', omitted_fields: [] })
    contractApi.generate.mockResolvedValue(generated)
    const wrapper = mount(ContractWorkspacePage)
    await flushPromises()
    await wrapper.find('.source-import input:not([type=file])').setValue('采购会议')
    await wrapper.find('.source-import textarea').setValue(base.source_text)
    await wrapper.find('.source-import form').trigger('submit')
    await flushPromises()
    await clickButton(wrapper, '2 · 选择模板')
    await wrapper.find('.template-card .primary').trigger('click')
    await flushPromises()
    await clickButton(wrapper, '按模板提取并复核字段')
    expect(contractApi.extract).toHaveBeenCalledWith(selected, false, false)
    expect(wrapper.find('.agent-guidance').text()).toContain('请核对金额；未知内容可暂留空。')
    expect(wrapper.find('.agent-guidance').text()).toContain('已有候选已保留')
    await wrapper.find('.field-card textarea').setValue('8000元')
    await wrapper.find('.field-decision button').trigger('click')
    await flushPromises()
    expect(contractApi.review.mock.calls[0][1][0]).toMatchObject({
      name: '金额',
      value: '8000元',
      action: 'confirm',
    })
    await clickButton(wrapper, '4 · 预览与导出')
    await clickButton(wrapper, '载入预览')
    await wrapper.find('.preview-panel input[type=checkbox]').setValue(true)
    await clickButton(wrapper, '生成 DOCX 合同')
    expect(contractApi.generate).toHaveBeenCalledWith(reviewed, false)
    expect(wrapper.find('.generated-files').text()).toContain('设备采购合同')
    wrapper.unmount()
  })
})
