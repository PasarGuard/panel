import { describe, expect, it } from 'bun:test'
import type { Outbound } from '@pasarguard/xray-config-kit'
import { inboundCertificateFingerprintRequest, outboundCertificateFingerprintRequest } from './certificate-fingerprint'

describe('certificate fingerprint sources', () => {
  it('reads the inbound certificate lines, without sending private key data', () => {
    expect(inboundCertificateFingerprintRequest([{ certificate: ['-----BEGIN CERTIFICATE-----', 'cert', '-----END CERTIFICATE-----'], key: ['secret'], certificateFile: '/missing.pem' }])).toEqual({
      pem: '-----BEGIN CERTIFICATE-----\ncert\n-----END CERTIFICATE-----',
    })
  })

  it('uses a configured path when there is no inline certificate', () => {
    expect(inboundCertificateFingerprintRequest([{ certificateFile: '/on-node/cert.pem', keyFile: '/on-node/key.pem', serveOnNode: true }])).toEqual({ file_path: '/on-node/cert.pem' })
  })

  it('keeps the first certificate rather than silently pinning a different one', () => {
    expect(inboundCertificateFingerprintRequest([{ certificateFile: '/missing.pem' }, { certificate: ['other cert'] }])).toEqual({ file_path: '/missing.pem' })
    expect(inboundCertificateFingerprintRequest([{ certificate: 'first cert' }, { certificate: 'other cert' }])).toEqual({ pem: 'first cert' })
  })

  it('has no request when inbound certificate data is missing', () => {
    for (const certificates of [undefined, [], [{}], [{ certificate: [], certificateFile: '' }]]) {
      expect(inboundCertificateFingerprintRequest(certificates)).toBeUndefined()
    }
  })

  it('probes the VLESS outbound IP and port, with TLS serverName only used as SNI', () => {
    const outbound = {
      protocol: 'vless',
      settings: { vnext: [{ address: '192.0.2.4', port: 8443, users: [] }] },
      streamSettings: { security: 'tls', tlsSettings: { serverName: 'sni.example.com', certificates: [{ certificateFile: '/missing.pem' }] } },
    } as unknown as Outbound
    expect(outboundCertificateFingerprintRequest(outbound)).toEqual({ server: '192.0.2.4', port: 8443, server_name: 'sni.example.com' })
  })

  it('reads nested servers and flat endpoint settings, including IPv6', () => {
    const trojan = { protocol: 'trojan', settings: { servers: [{ address: '2001:db8::1', port: 9443 }] } } as unknown as Outbound
    expect(outboundCertificateFingerprintRequest(trojan)).toEqual({ server: '2001:db8::1', port: 9443 })
    const flat = { protocol: 'http', settings: { address: 'proxy.example.com', port: 10443 } } as unknown as Outbound
    expect(outboundCertificateFingerprintRequest(flat)).toEqual({ server: 'proxy.example.com', port: 10443 })
  })

  it('does not substitute SNI or a default port for an incomplete outbound endpoint', () => {
    for (const settings of [{}, { address: 'example.com' }, { address: '', port: 443 }, { address: 'example.com', port: 0 }, { address: 'example.com', port: 65536 }]) {
      const outbound = { protocol: 'vless', settings, streamSettings: { security: 'tls', tlsSettings: { serverName: 'sni.example.com' } } } as unknown as Outbound
      expect(outboundCertificateFingerprintRequest(outbound)).toBeUndefined()
    }
  })
})
