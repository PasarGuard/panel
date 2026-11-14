import { describe, expect, it } from 'bun:test'

import { defaultSubscriptionRules, getRuleTemplateType, normalizeRuleTemplateId, subscriptionSchema, templateIdAfterTargetChange } from './subscription-settings-schema'

const matchDefaultRule = (userAgent: string) =>
  defaultSubscriptionRules.find(rule => new RegExp(rule.pattern).test(userAgent))?.target

describe('default subscription rules', () => {
  it('uses the first matching rule for built-in clients', () => {
    expect(matchDefaultRule('v2rayN/7.15')).toBe('links')
    expect(matchDefaultRule('v2rayNG/1.10')).toBe('links')
    expect(matchDefaultRule('Happ/2.0')).toBe('xray')
    expect(matchDefaultRule('Streisand/1.0')).toBe('xray')
    expect(matchDefaultRule('ktor-client/2.3')).toBe('xray')
  })

  it('keeps other clients on the catch-all and has no InHive rule', () => {
    expect(matchDefaultRule('InHive/1.0')).toBe('links_base64')
    expect(matchDefaultRule('unknown-client/1.0')).toBe('links_base64')
    expect(defaultSubscriptionRules.some(rule => /inhive/i.test(rule.pattern))).toBe(false)
  })
})

describe('rule template', () => {
  const parseRule = (rule: Record<string, unknown>) => subscriptionSchema.shape.rules.safeParse([{ pattern: '.*', target: 'xray', ...rule }])

  it('accepts a missing, null or numeric template_id', () => {
    expect(parseRule({}).success).toBe(true)
    expect(parseRule({ template_id: null }).success).toBe(true)
    const parsed = parseRule({ template_id: 7 })
    expect(parsed.success).toBe(true)
    expect(parsed.data?.[0].template_id).toBe(7)
  })

  it('rejects a template_id that is not a positive integer', () => {
    expect(parseRule({ template_id: '7' }).success).toBe(false)
    expect(parseRule({ template_id: 0 }).success).toBe(false)
    expect(parseRule({ template_id: 1.5 }).success).toBe(false)
  })

  it('maps rule targets to client template types', () => {
    expect(getRuleTemplateType('xray')).toBe('xray_subscription')
    expect(getRuleTemplateType('sing_box')).toBe('singbox_subscription')
    expect(getRuleTemplateType('clash')).toBe('clash_subscription')
    expect(getRuleTemplateType('clash_meta')).toBe('clash_subscription')
    expect(getRuleTemplateType('links')).toBeNull()
    expect(getRuleTemplateType('block')).toBeNull()
  })

  it('keeps the template only while the template type stays the same', () => {
    expect(templateIdAfterTargetChange(3, 'clash', 'clash_meta')).toBe(3)
    expect(templateIdAfterTargetChange(3, 'xray', 'xray')).toBe(3)
    expect(templateIdAfterTargetChange(3, 'xray', 'sing_box')).toBeNull()
    expect(templateIdAfterTargetChange(3, 'clash_meta', 'links')).toBeNull()
    expect(templateIdAfterTargetChange(undefined, 'xray', 'xray')).toBeNull()
  })

  it('sends null for targets without templates', () => {
    expect(normalizeRuleTemplateId('sing_box', 4)).toBe(4)
    expect(normalizeRuleTemplateId('sing_box', undefined)).toBeNull()
    expect(normalizeRuleTemplateId('links_base64', 4)).toBeNull()
  })
})
