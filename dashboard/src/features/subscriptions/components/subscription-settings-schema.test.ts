import { describe, expect, it } from 'bun:test'
import { mapSubscriptionRulesForForm, prepareSubscriptionRulesForPayload } from './subscription-settings-schema'

describe('subscription rule mapping', () => {
  it('preserves profile_id from API through the processed payload', () => {
    const formRules = mapSubscriptionRulesForForm([{ pattern: '^happ', target: 'xray', profile_id: 42, response_headers: { routing: 'enabled' } }])

    expect(formRules[0].profile_id).toBe(42)
    expect(prepareSubscriptionRulesForPayload(formRules)[0]).toEqual({
      pattern: '^happ',
      target: 'xray',
      profile_id: 42,
      response_headers: { routing: 'enabled' },
    })
  })
})
