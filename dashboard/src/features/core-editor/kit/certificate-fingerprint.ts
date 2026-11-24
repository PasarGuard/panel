import type { Outbound } from '@pasarguard/xray-config-kit'
import type { CertificateFingerprintRequest } from '@/service/api'
import { flattenOutboundSettings } from './outbound-editor-json'

export function inboundCertificateFingerprintRequest(certificates: unknown): CertificateFingerprintRequest | undefined {
  if (!Array.isArray(certificates)) return undefined
  for (const certificate of certificates) {
    if (!certificate || typeof certificate !== 'object') continue
    const pem = Array.isArray(certificate.certificate) ? certificate.certificate.join('\n') : certificate.certificate
    if (typeof pem === 'string' && pem.trim()) return { pem }
    if (typeof certificate.certificateFile === 'string' && certificate.certificateFile.trim()) return { file_path: certificate.certificateFile.trim() }
  }
  return undefined
}

export function outboundCertificateFingerprintRequest(outbound: Outbound): CertificateFingerprintRequest | undefined {
  const endpoint = flattenOutboundSettings(outbound)
  const port = Number(endpoint.port)
  if (typeof endpoint.address !== 'string' || !endpoint.address.trim() || !Number.isInteger(port) || port < 1 || port > 65535) return undefined
  const tls = (outbound as { streamSettings?: { tlsSettings?: { serverName?: unknown } } }).streamSettings?.tlsSettings
  const serverName = typeof tls?.serverName === 'string' ? tls.serverName.trim() : ''
  return { server: endpoint.address.trim(), port, ...(serverName ? { server_name: serverName } : {}) }
}
