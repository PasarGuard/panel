import { expect, test } from 'bun:test'
import { mapSubscriptionRulesForForm, prepareSubscriptionRulesForPayload, subscriptionSchema } from './subscription-settings-schema'

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
