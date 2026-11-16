import { describe, expect, it } from 'bun:test'
import { inferNodeVerification, nodeFormDefaultValues, nodeFormSchema, nodeVerificationPayload } from './node-form'

const pin = 'ab'.repeat(32)

describe('node TLS verification', () => {
  it('infers fingerprint before PEM and defaults to system trust', () => {
    expect(inferNodeVerification({})).toBe('trusted')
    expect(inferNodeVerification({ server_ca: 'pem' })).toBe('pem')
    expect(inferNodeVerification({ server_ca: 'pem', certificate_sha256: pin })).toBe('fingerprint')
    expect(inferNodeVerification({ certificate_sha256: pin })).toBe('fingerprint')
  })

  it('clears both saved verification fields when selecting trusted certificates', () => {
    expect(nodeVerificationPayload({ verification: 'trusted', server_ca: 'old pem', certificate_sha256: pin })).toEqual({ server_ca: '', certificate_sha256: null })
  })

  it('normalizes pins and clears inactive PEM on save', () => {
    expect(nodeVerificationPayload({ verification: 'fingerprint', server_ca: 'old pem', certificate_sha256: Array(32).fill('AB').join(':') })).toEqual({ server_ca: '', certificate_sha256: pin })
    expect(nodeVerificationPayload({ verification: 'pem', server_ca: ' pem ', certificate_sha256: pin })).toEqual({ server_ca: 'pem', certificate_sha256: null })
  })

  it('requires verification input only for the selected policy', () => {
    const values = { ...nodeFormDefaultValues, name: 'node', address: 'node.example.com', api_key: 'key', core_config_id: 1 }
    expect(nodeFormSchema.safeParse(values).success).toBe(true)
    expect(nodeFormSchema.safeParse({ ...values, verification: 'pem' }).success).toBe(false)
    expect(nodeFormSchema.safeParse({ ...values, verification: 'fingerprint', certificate_sha256: 'bad' }).success).toBe(false)
    expect(nodeFormSchema.safeParse({ ...values, verification: 'fingerprint', certificate_sha256: pin }).success).toBe(true)
    expect(nodeFormSchema.safeParse({ ...values, verification: 'pem', server_ca: 'pem' }).success).toBe(true)
  })
})
