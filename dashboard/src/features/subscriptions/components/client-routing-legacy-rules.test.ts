import { expect, test } from 'bun:test'
import { changeSubscriptionRuleTarget, selectSubscriptionRuleProfile, mapSubscriptionRulesForForm, prepareSubscriptionRulesForPayload, subscriptionSchema } from './subscription-settings-schema'

test('legacy settings validation and reordering retain native and Happ bindings', () => {
  const rules = mapSubscriptionRulesForForm([
    { pattern: '^Xray', target: 'xray', template_id: 7, ui_application: 'xray', response_headers: { custom: 'keep' } },
    { pattern: '^Happ', target: 'links_base64', ui_application: 'happ', happ_routing: { template_id: 9, transport: 'header', action: 'add', enabled: false } },
  ])
  const parsed = subscriptionSchema.parse({ rules: [...rules].reverse(), custom_variables: [] })
  const payload = prepareSubscriptionRulesForPayload(parsed.rules)
  expect(payload[0]).toMatchObject({ pattern: '^Happ', target: 'links_base64', happ_routing: { template_id: 9, transport: 'header', action: 'add', enabled: false } })
  expect(payload[1]).toMatchObject({ template_id: 7, ui_application: 'xray', response_headers: { custom: 'keep' } })
})

test('legacy schema round trip preserves generator IDs, app ownership and delivery metadata', () => {
  const rules = mapSubscriptionRulesForForm([
    { pattern: '^SFA', target: 'sing_box', profile_id: 12, ui_application: 'sing_box', response_headers: { 'x-client': 'keep' } },
    { pattern: '^Happ', target: 'links_base64', template_id: null, profile_id: null, ui_application: 'happ', happ_routing: { template_id: 9, transport: 'header', action: 'add', enabled: false } },
  ])
  const parsed = subscriptionSchema.parse({ rules, custom_variables: [] })
  const payload = prepareSubscriptionRulesForPayload(parsed.rules)
  expect(payload[0]).toMatchObject({ profile_id: 12, ui_application: 'sing_box', response_headers: { 'x-client': 'keep' } })
  expect(payload[1]).toMatchObject({ ui_application: 'happ', happ_routing: { template_id: 9, transport: 'header', action: 'add', enabled: false } })
})

test('explicit legacy source and format edits remove only incompatible bindings', () => {
  const native = { pattern: '^Xray', target: 'xray' as const, template_id: 7, ui_application: 'xray', response_headers: { custom: 'keep' } }
  expect(selectSubscriptionRuleProfile(native, 12)).toMatchObject({ profile_id: 12, template_id: undefined, ui_application: 'xray', response_headers: { custom: 'keep' } })
  expect(selectSubscriptionRuleProfile(native).template_id).toBe(7)
  expect(changeSubscriptionRuleTarget(native, 'sing_box').template_id).toBeUndefined()
  expect(changeSubscriptionRuleTarget(native, 'xray').template_id).toBe(7)
  expect(changeSubscriptionRuleTarget({ ...native, target: 'clash' }, 'clash_meta').template_id).toBe(7)
  const happ = { pattern: '^Happ', target: 'links' as const, happ_routing: { template_id: 9, transport: 'header' as const } }
  expect(changeSubscriptionRuleTarget(happ, 'links_base64').happ_routing?.template_id).toBe(9)
  expect(changeSubscriptionRuleTarget(happ, 'xray').happ_routing).toBeUndefined()
})
