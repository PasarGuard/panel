import { describe, expect, it } from 'bun:test'
import { HostFormSchema, mapHostSubscriptionTemplatesForForm, shouldShowProfileClassification } from './host-form'

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

  it('lets the operator clear a country the backend treats as unset', () => {
    const parse = (country: string) => {
      const result = HostFormSchema.safeParse({
        remark: 'h',
        address: ['1.1.1.1'],
        inbound_tag: 'VLESS-A',
        subscription_templates: { profile: { pool: 'primary', country } },
      })
      return result.success || !result.error.issues.some(issue => issue.path.join('.').endsWith('country'))
    }

    // The input holds '' the instant the two letters are deleted, and
    // HostProfileClassification.validate_country maps '' to None. Rejecting it
    // here leaves no way to remove a country short of abandoning the dialog.
    expect(parse('')).toBe(true)
    expect(parse('DE')).toBe(true)
    expect(parse('12')).toBe(false)
    expect(parse('D')).toBe(false)
  })

  it('drops an empty subscription template object', () => {
    expect(mapHostSubscriptionTemplatesForForm({ xray: null, profile: null })).toBeUndefined()
  })
})

describe('profile classification visibility', () => {
  it('stays out of the way of a deployment that uses no profiles', () => {
    // Every operator was being asked to classify every host into a pool that
    // nothing declared, in a dialog where all other advanced settings are
    // already behind an accordion.
    expect(shouldShowProfileClassification(0, undefined)).toBe(false)
    expect(shouldShowProfileClassification(0, { pool: 'primary' })).toBe(false)
    expect(shouldShowProfileClassification(1, undefined)).toBe(true)
  })

  it('keeps showing a classification the host already carries', () => {
    // Otherwise a value set before the last profile was deleted -- or while a
    // role could still read the template list -- becomes invisible and
    // unclearable while still affecting output.
    expect(shouldShowProfileClassification(0, { country: 'SE' })).toBe(true)
    expect(shouldShowProfileClassification(0, { pool: 'europe' })).toBe(true)
    expect(shouldShowProfileClassification(0, { priority: 0 })).toBe(true)
    expect(shouldShowProfileClassification(0, { exclude_from_auto: true })).toBe(true)
  })
})
