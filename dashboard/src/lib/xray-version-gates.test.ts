import { describe, expect, it } from 'vitest'
import { isXrayVersionAtLeast, parseXrayVersion, XRAY_FEATURE_GATES } from '@/lib/xray-version-gates'

describe('parseXrayVersion', () => {
  it('parses a bare version', () => {
    expect(parseXrayVersion('26.6.27')).toEqual({ major: 26, minor: 6, patch: 27 })
  })

  it('parses a v-prefixed version', () => {
    expect(parseXrayVersion('v26.6.27')).toEqual({ major: 26, minor: 6, patch: 27 })
  })

  it('returns null for "latest"', () => {
    expect(parseXrayVersion('latest')).toBeNull()
  })

  it('returns null for null, undefined, and empty string', () => {
    expect(parseXrayVersion(null)).toBeNull()
    expect(parseXrayVersion(undefined)).toBeNull()
    expect(parseXrayVersion('')).toBeNull()
  })

  it('returns null for malformed strings', () => {
    expect(parseXrayVersion('not-a-version')).toBeNull()
    expect(parseXrayVersion('26.6')).toBeNull()
  })
})

describe('isXrayVersionAtLeast', () => {
  it('is true when version is above cutoff', () => {
    expect(isXrayVersionAtLeast('26.6.27', '26.5.3')).toBe(true)
  })

  it('is true when version equals cutoff', () => {
    expect(isXrayVersionAtLeast('26.5.3', '26.5.3')).toBe(true)
  })

  it('is false when version is below cutoff', () => {
    expect(isXrayVersionAtLeast('26.4.25', '26.5.3')).toBe(false)
  })

  it('is false (fail-open) when version is unknown', () => {
    expect(isXrayVersionAtLeast(null, '26.5.3')).toBe(false)
    expect(isXrayVersionAtLeast('latest', '26.5.3')).toBe(false)
  })

  it('compares minor/patch correctly, not lexicographically', () => {
    // lexicographic "26.10.0" < "26.5.3" would be wrong; numeric compare must get this right
    expect(isXrayVersionAtLeast('26.10.0', '26.5.3')).toBe(true)
  })
})

describe('XRAY_FEATURE_GATES', () => {
  it('has all gate versions defined as parseable version strings', () => {
    expect(parseXrayVersion(XRAY_FEATURE_GATES.allowInsecureHardError)).not.toBeNull()
    expect(parseXrayVersion(XRAY_FEATURE_GATES.sessionIdFieldsRenamed)).not.toBeNull()
  })
})
