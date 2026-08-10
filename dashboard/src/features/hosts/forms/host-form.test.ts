import { describe, expect, it } from 'bun:test'
import { mapHostSubscriptionTemplatesForForm } from './host-form'

describe('host form API normalization', () => {
  it('normalizes nullable subscription profile fields', () => {
    expect(
      mapHostSubscriptionTemplatesForForm({
        xray: null,
        profile: { pool: null, country: null, priority: null, exclude_from_auto: null },
      }),
    ).toEqual({
      xray: undefined,
      profile: { pool: 'primary', country: undefined, priority: undefined, exclude_from_auto: undefined },
    })
  })

  it('drops an empty subscription template object', () => {
    expect(mapHostSubscriptionTemplatesForForm({ xray: null, profile: null })).toBeUndefined()
  })
})
