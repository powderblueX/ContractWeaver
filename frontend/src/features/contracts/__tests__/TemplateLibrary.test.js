/** @file 验证本组件或状态模块的交互、异常和资源清理；不调用真实模型。 */
import { mount, flushPromises } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import TemplateLibrary from '../components/TemplateLibrary.vue'
import { contractApi } from '../contractApi'

vi.mock('../contractApi', () => ({ contractApi: { browseTemplates: vi.fn(), templateDetails: vi.fn() } }))

describe('manual template choice', () => {
  it('shows a named but unsupported template without allowing selection', async () => {
    contractApi.browseTemplates.mockResolvedValue({ items: [], total: 0, limit: 24 })
    const wrapper = mount(TemplateLibrary, {
      props: {
        recommendations: [
          {
            id: 'named',
            name: '点名合同',
            group: '部委',
            fillable: false,
            match_score: 1,
            match_reasons: ['已找到原件，但暂不能自动填写：内容控件'],
          },
        ],
      },
    })
    await flushPromises()
    expect(wrapper.text()).toContain('内容控件')
    expect(wrapper.find('.template-card button.primary').attributes('disabled')).toBeDefined()
    expect(wrapper.find('.template-card button.secondary').attributes('disabled')).toBeUndefined()
    wrapper.unmount()
  })

  it('shows unsupported structures and disables selection in template details', async () => {
    contractApi.browseTemplates.mockResolvedValue({
      items: [{ id: 'blocked', name: '复杂原件', group: '地方' }],
      total: 1,
      limit: 24,
    })
    contractApi.templateDetails.mockResolvedValue({
      id: 'blocked',
      name: '复杂原件',
      group: '地方',
      fields: [{ name: '候选位置' }],
      fillable: false,
      warnings: ['存在不支持的内容控件'],
      preview_text: '原始内容',
    })
    const wrapper = mount(TemplateLibrary)
    await flushPromises()
    await wrapper.find('.template-card button.secondary').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('存在不支持的内容控件')
    expect(wrapper.find('.template-modal button.primary').attributes('disabled')).toBeDefined()
    expect(wrapper.emitted('select')).toBeUndefined()
    wrapper.unmount()
  })

  it('can select a library template outside the Agent recommendations', async () => {
    contractApi.browseTemplates.mockResolvedValue({
      items: [{ id: 'manual', name: '用户选定模板', group: '地方' }],
      total: 1,
      limit: 24,
    })
    const wrapper = mount(TemplateLibrary, {
      props: {
        recommendations: [
          {
            id: 'recommended',
            name: '推荐模板',
            group: '部委',
            match_score: 0.5,
            match_reasons: ['关键词匹配'],
          },
        ],
      },
    })
    await flushPromises()
    const manualCard = wrapper.findAll('.template-card').find((card) => card.text().includes('用户选定模板'))
    await manualCard.find('button.primary').trigger('click')
    expect(wrapper.emitted('select')[0][0].id).toBe('manual')
    wrapper.unmount()
  })
})
