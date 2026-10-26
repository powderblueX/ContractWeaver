/** @file 验证本组件或状态模块的交互、异常和资源清理；不调用真实模型。 */
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import ContractPreviewPanel from '../components/ContractPreviewPanel.vue'

describe('contract preview gate', () => {
  it('never exposes internal placeholders before review and guides back to review', async () => {
    const wrapper = mount(ContractPreviewPanel, {
      props: {
        workspace: {
          stage: 'field_review',
          revision: 1,
          selected_template: { id: 'one' },
          fields: [{ status: 'missing' }],
          artifacts: [],
        },
        preview: { revision: 1, text: '总价：{复杂定位·位置145-7}' },
      },
    })
    expect(wrapper.text()).not.toContain('位置145')
    expect(wrapper.text()).toContain('还不能导出')
    await wrapper.find('.preview-blocked button').trigger('click')
    expect(wrapper.emitted('back-review')).toHaveLength(1)
    wrapper.unmount()
  })
  it('renders readable tables instead of a flattened placeholder dump', () => {
    const wrapper = mount(ContractPreviewPanel, {
      props: {
        workspace: {
          stage: 'ready_to_generate',
          revision: 1,
          selected_template: { id: 'one' },
          artifacts: [],
        },
        preview: {
          revision: 1,
          blocks: [
            {
              type: 'table',
              rows: [
                ['总价', '80000元'],
                ['签字', '{签字·位置1}'],
              ],
            },
          ],
        },
      },
    })
    expect(wrapper.findAll('td')).toHaveLength(4)
    expect(wrapper.text()).toContain('80000元')
    expect(wrapper.text()).not.toContain('·位置')
    wrapper.unmount()
  })
  it('requires a separate visual review approval and resets it after edits', async () => {
    const workspace = {
      stage: 'ready_to_generate',
      revision: 1,
      selected_template: { id: 'image', requires_visual_review: true },
      artifacts: [],
    }
    const wrapper = mount(ContractPreviewPanel, {
      props: { workspace, preview: { revision: 1, text: '预览', omitted_fields: [] } },
    })
    const checks = wrapper.findAll('input[type=checkbox]')
    await checks[0].setValue(true)
    expect(wrapper.find('.generate-button').attributes('disabled')).toBeDefined()
    await checks[1].setValue(true)
    expect(wrapper.find('.generate-button').attributes('disabled')).toBeUndefined()
    await wrapper.find('.generate-button').trigger('click')
    expect(wrapper.emitted('generate')[0][0]).toEqual({ visualReviewAcknowledged: true })
    await wrapper.setProps({ workspace: { ...workspace, revision: 2 } })
    expect(checks[1].element.checked).toBe(false)
    expect(wrapper.find('.generate-button').attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })
  it('requires complete review and current preview acknowledgement', async () => {
    const workspace = { stage: 'field_review', revision: 4, selected_template: { id: 'one' }, artifacts: [] }
    const wrapper = mount(ContractPreviewPanel, {
      props: { workspace, preview: { revision: 4, text: '合同预览', omitted_fields: [] } },
    })
    expect(wrapper.find('.generate-button').attributes('disabled')).toBeDefined()
    await wrapper.setProps({ workspace: { ...workspace, stage: 'ready_to_generate' } })
    await wrapper.find('input[type=checkbox]').setValue(true)
    expect(wrapper.find('.generate-button').attributes('disabled')).toBeUndefined()
    await wrapper.find('.generate-button').trigger('click')
    expect(wrapper.emitted('generate')).toHaveLength(1)
    await wrapper.setProps({ workspace: { ...workspace, stage: 'ready_to_generate', revision: 5 } })
    expect(wrapper.find('input[type=checkbox]').element.checked).toBe(false)
    expect(wrapper.find('.generate-button').attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })
})
