import { describe, expect, it } from 'bun:test'
import { serializeTransportSettings } from '../src/features/hosts/forms/host-payload'

describe('host transport serialization', () => {
  it('preserves chunk ranges and zero keep-alive without mutating the form', () => {
    const input = { xhttp_settings: { uplink_chunk_size: '1024-4096', xmux: { max_concurrency: '4-8', h_keep_alive_period: 0 } } }
    const before = JSON.stringify(input)
    const result = serializeTransportSettings(input)
    expect(result?.xhttp_settings?.uplink_chunk_size).toBe('1024-4096')
    expect(result?.xhttp_settings?.xmux).toEqual({
      maxConcurrency: '4-8', maxConnections: undefined, cMaxReuseTimes: undefined,
      hMaxReusableSecs: undefined, hMaxRequestTimes: undefined, hKeepAlivePeriod: 0,
    })
    expect(JSON.stringify(input)).toBe(before)
  })

  it('handles unset transport settings', () => {
    expect(serializeTransportSettings(undefined)).toBeUndefined()
  })
})
