/** @file 验证本组件或状态模块的交互、异常和资源清理；不调用真实模型。 */
import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import FieldReviewPanel from '../components/FieldReviewPanel.vue'

/**
 * 创建独立字段测试夹具，避免把服务端任务当作共享可变对象。
 * @param {string} name 夹具使用的字段名称。
 * @param {string} value 当前候选或输入值。
 */
const makeField = (name, value) => ({
  name,
  value,
  extracted_value: value,
  status: 'extracted',
  evidence: [{ line_number: 1, quote: '协商原文' }],
  alternatives: [],
  review_issues: [],
  context: `合同字段：{${name}}`,
  note: '',
  user_note: '',
})

describe('field review', () => {
  it('does not bulk-confirm conflicts or values carrying review warnings', async () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true)
    const wrapper = mount(FieldReviewPanel, {
      props: {
        fields: [
          makeField('可核对值', '公司'),
          { ...makeField('日期错误', '2026'), status: 'conflict' },
          { ...makeField('选项错误', '否'), review_issues: ['原件角色有歧义'] },
          { ...makeField('依据不足', '3000'), status: 'unverified' },
        ],
      },
    })
    const button = wrapper.findAll('button').find((item) => item.text().startsWith('确认所有已填写项'))
    expect(button.text()).toContain('1')
    await button.trigger('click')
    expect(wrapper.emitted('save')[0][0].map((decision) => decision.name)).toEqual(['可核对值'])
    wrapper.unmount()
    confirm.mockRestore()
  })
  it('ignores unknown blanks across pages and filters without overwriting values, reviewed fields or local changes', async () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true)
    const fields = Array.from({ length: 25 }, (_, index) => ({
      ...makeField(`字段${index}`, ''),
      status: 'missing',
    }))
    fields.push(
      makeField('有内容的分歧', '尚待核对'),
      { ...makeField('已确认', '确认值'), status: 'confirmed' },
      { ...makeField('已留空', ''), status: 'omitted' }
    )
    const wrapper = mount(FieldReviewPanel, { props: { fields } })
    await wrapper.find('textarea').setValue('我的未保存内容')
    await wrapper.findAll('.field-decision input:not([type=checkbox])')[1].setValue('我的未保存备注')
    await wrapper.find('[aria-label="查找字段"]').setValue('有内容的分歧')
    await wrapper.find('.ignore-unknown-tools button').trigger('click')
    const decisions = wrapper.emitted('save')[0][0]
    expect(decisions).toHaveLength(23)
    expect(
      decisions.every((decision) => decision.action === 'omit' && decision.note.includes('首轮纪要'))
    ).toBe(true)
    expect(decisions.map((decision) => decision.name)).toContain('字段24')
    expect(decisions.map((decision) => decision.name)).not.toContain('字段0')
    expect(decisions.map((decision) => decision.name)).not.toContain('字段1')
    expect(wrapper.find('textarea').element.value).toBe('尚待核对')
    await wrapper.setProps({
      fields: fields.map((field) =>
        decisions.some((decision) => decision.name === field.name)
          ? { ...field, status: 'omitted', user_note: decisions[0].note }
          : field
      ),
    })
    await wrapper.find('[aria-label="查找字段"]').setValue('')
    expect(wrapper.find('textarea').element.value).toBe('我的未保存内容')
    expect(wrapper.findAll('.field-decision input:not([type=checkbox])')[1].element.value).toBe(
      '我的未保存备注'
    )
    wrapper.unmount()
    confirm.mockRestore()
  })

  it('can cancel global ignore and requires a shared reason', async () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    const wrapper = mount(FieldReviewPanel, { props: { fields: [makeField('未确定', '')] } })
    await wrapper.find('.ignore-unknown-tools button').trigger('click')
    expect(wrapper.emitted('save')).toBeUndefined()
    expect(wrapper.find('.field-decision input[type=checkbox]').element.checked).toBe(false)
    await wrapper.find('.ignore-unknown-tools input').setValue(' ')
    expect(wrapper.find('.ignore-unknown-tools button').attributes('disabled')).toBeDefined()
    wrapper.unmount()
    confirm.mockRestore()
  })
  it('shows human names and explicitly groups selected unused blanks without clearing filled values', async () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true)
    const fields = [
      { ...makeField('表格空白·位置36', ''), display_name: '第2行 · 数量', kind: 'table', status: 'missing' },
      { ...makeField('金额·位置37', '80000元'), display_name: '合同总价' },
    ]
    const wrapper = mount(FieldReviewPanel, { props: { fields } })
    expect(wrapper.text()).not.toContain('·位置')
    expect(wrapper.text()).toContain('第2行 · 数量')
    await wrapper.find('.bulk-blank-tools button').trigger('click')
    await wrapper.findAll('.bulk-blank-tools button').at(-1).trigger('click')
    expect(wrapper.emitted('save')[0][0]).toEqual([
      expect.objectContaining({ name: '表格空白·位置36', action: 'omit', value: '' }),
    ])
    expect(wrapper.findAll('textarea')[1].element.value).toBe('80000元')
    wrapper.unmount()
    confirm.mockRestore()
  })
  it('keeps unsaved values when paging through a large template', async () => {
    const fields = Array.from({ length: 21 }, (_, index) => makeField(`字段${index}`, ''))
    const wrapper = mount(FieldReviewPanel, { props: { fields } })
    expect(wrapper.findAll('.field-card')).toHaveLength(20)
    await wrapper.find('textarea').setValue('第一页待保存的值')
    await wrapper.findAll('.pagination button')[1].trigger('click')
    expect(wrapper.findAll('.field-card')).toHaveLength(1)
    await wrapper.find('textarea').setValue('第二页待保存的值')
    await wrapper.findAll('.pagination button')[0].trigger('click')
    expect(wrapper.find('textarea').element.value).toBe('第一页待保存的值')
    wrapper.unmount()
  })
  it('preserves other unsaved edits after confirming one field', async () => {
    const fields = [makeField('甲方', '原公司'), makeField('金额', '9000元')]
    const wrapper = mount(FieldReviewPanel, { props: { fields, busy: false } })
    const inputs = wrapper.findAll('textarea')
    await inputs[0].setValue('确认公司')
    await inputs[1].setValue('8000元')
    await wrapper.findAll('.field-decision button')[0].trigger('click')
    expect(wrapper.emitted('save')[0][0]).toEqual([
      { name: '甲方', value: '确认公司', action: 'confirm', note: '' },
    ])
    await wrapper.setProps({
      fields: [
        { ...fields[0], value: '确认公司', status: 'confirmed', value_origin: 'user_edit' },
        fields[1],
      ],
    })
    expect(wrapper.findAll('textarea')[1].element.value).toBe('8000元')
    expect(wrapper.emitted('dirty').at(-1)[0]).toBe(true)
    wrapper.unmount()
  })

  it('requires a reason before explicitly leaving a field blank', async () => {
    const wrapper = mount(FieldReviewPanel, { props: { fields: [makeField('签字', '')] } })
    await wrapper.find('.field-decision input[type=checkbox]').setValue(true)
    expect(wrapper.find('.field-decision button').attributes('disabled')).toBeDefined()
    await wrapper.find('.field-decision input:not([type=checkbox])').setValue('线下手写签名')
    await wrapper.find('.field-decision button').trigger('click')
    expect(wrapper.emitted('save')[0][0][0]).toMatchObject({
      name: '签字',
      action: 'omit',
      note: '线下手写签名',
    })
    wrapper.unmount()
  })

  it('shows saving and saved states, disables duplicate submissions and re-enables changed fields', async () => {
    const fields = [makeField('公司', '甲公司')]
    const wrapper = mount(FieldReviewPanel, { props: { fields } })
    /** Read the current per-field action after each state update. */
    const button = () => wrapper.find('.field-decision button')
    await button().trigger('click')
    await wrapper.setProps({ busy: true })
    expect(button().text()).toBe('正在保存…')
    await wrapper.setProps({ fields: [{ ...fields[0], status: 'confirmed' }] })
    await wrapper.setProps({ busy: false })
    expect(button().text()).toBe('已保存 · 已确认')
    expect(button().attributes('disabled')).toBeDefined()
    expect(wrapper.find('[role="status"]').text()).toContain('已保存 1 项')
    await wrapper.find('textarea').setValue('乙公司')
    expect(button().attributes('disabled')).toBeUndefined()
    expect(button().text()).toBe('保存并确认')
    wrapper.unmount()
  })

  it('does not claim success after a failed save and recognizes already omitted fields', async () => {
    const fields = [{ ...makeField('签字', ''), status: 'omitted', user_note: '线下签署' }]
    const wrapper = mount(FieldReviewPanel, { props: { fields } })
    expect(wrapper.find('.field-decision button').text()).toBe('已保存 · 保留空白')
    expect(wrapper.find('.field-decision button').attributes('disabled')).toBeDefined()
    await wrapper.find('.field-decision input:not([type=checkbox])').setValue('待补充')
    await wrapper.find('.field-decision button').trigger('click')
    await wrapper.setProps({ busy: true })
    await wrapper.setProps({ busy: false })
    expect(wrapper.find('[role="status"]').exists()).toBe(false)
    expect(wrapper.find('.field-decision button').text()).toBe('确认保留空白')
    wrapper.unmount()
  })

  it('lets users locate the exact original evidence', async () => {
    const wrapper = mount(FieldReviewPanel, { props: { fields: [makeField('甲方', '公司')] } })
    await wrapper.find('blockquote button').trigger('click')
    expect(wrapper.emitted('source')[0]).toEqual([1])
    wrapper.unmount()
  })
})
