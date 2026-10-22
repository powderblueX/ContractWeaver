import { mount, flushPromises } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import AuthPage from '../AuthPage.vue'
import { postJson } from '../../../shared/httpClient'

vi.mock('vue-router', () => ({ useRouter: () => ({ replace: vi.fn() }) }))
vi.mock('../../../shared/httpClient', () => ({ postJson: vi.fn() }))
vi.mock('../../../shared/authSession', () => ({ saveSession: vi.fn() }))

describe('email-only account flow', () => {
  it('blocks repeated submissions while waiting and shows a loading indicator', async () => {
    let resolve
    postJson.mockClear()
    postJson.mockImplementation(
      () =>
        new Promise((done) => {
          resolve = done
        })
    )
    const wrapper = mount(AuthPage)
    await wrapper.find('input[type=email]').setValue('test@example.org')
    await wrapper.find('input[type=password]').setValue('safe-password-123')
    await wrapper.find('form').trigger('submit')
    await wrapper.find('form').trigger('submit')
    expect(postJson).toHaveBeenCalledTimes(1)
    expect(wrapper.find('.loading-spinner').exists()).toBe(true)
    expect(wrapper.find('.primary').attributes('disabled')).toBeDefined()
    expect(
      wrapper.findAll('.segmented button').every((button) => button.attributes('disabled') !== undefined)
    ).toBe(true)
    resolve({ access_token: 'test', user: { email: 'test@example.org' } })
    await flushPromises()
    expect(wrapper.find('.loading-spinner').exists()).toBe(false)
    wrapper.unmount()
  })
  it('registers and signs in with email/password, never asks for a username', async () => {
    postJson.mockResolvedValue({ access_token: 'test', user: { email: 'test@example.org' } })
    const wrapper = mount(AuthPage)
    await wrapper.findAll('.segmented button')[1].trigger('click')
    expect(wrapper.findAll('input')).toHaveLength(2)
    expect(wrapper.text()).not.toContain('用户名')
    await wrapper.find('input[type=email]').setValue('test@example.org')
    await wrapper.find('input[type=password]').setValue('safe-password-123')
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect(postJson).toHaveBeenCalledWith('/auth/register', {
      email: 'test@example.org',
      password: 'safe-password-123',
    })
    expect(postJson).toHaveBeenCalledWith('/auth/login', {
      email: 'test@example.org',
      password: 'safe-password-123',
    })
    wrapper.unmount()
  })
})
