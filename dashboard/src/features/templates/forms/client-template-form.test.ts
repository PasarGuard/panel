import { describe, expect, it } from 'bun:test'
import { ClientTemplateType } from '@/service/api'
import { supportsDefaultSelection } from './client-template-form'

describe('client template form behavior', () => {
  it('offers automatic default selection only to template types consumed implicitly', () => {
    expect(supportsDefaultSelection(ClientTemplateType.xray_subscription)).toBe(true)
    expect(supportsDefaultSelection(ClientTemplateType.singbox_subscription)).toBe(true)
    expect(supportsDefaultSelection(ClientTemplateType.xray_profile)).toBe(false)
    expect(supportsDefaultSelection(ClientTemplateType.singbox_profile)).toBe(false)
  })
})
