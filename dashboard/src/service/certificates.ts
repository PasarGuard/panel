import { fetcher } from '@/service/http'

export type CertificateTimeStatus = 'valid' | 'expiring' | 'expired' | 'not_yet_valid'

export interface CertificateDetails {
  subject: string
  issuer: string
  domains: string[]
  common_name: string | null
  not_before: string
  not_after: string
  fingerprint: string
  serial_number: string
  public_key_algorithm: string
  is_ca: boolean
  self_signed: boolean
  status: CertificateTimeStatus
}

export interface CertificateInspection {
  status: CertificateTimeStatus | 'invalid' | 'unavailable' | 'empty'
  certificates: CertificateDetails[]
  key_status: 'matched' | 'mismatch' | 'missing' | 'invalid' | 'unavailable'
  error: string | null
  key_error: string | null
  server_name_matches: boolean | null
  chain_linked: boolean | null
  checked_at: string
}

export interface CertificateInspectionRequest {
  certificate?: string
  key?: string
  certificate_file?: string
  key_file?: string
  serve_on_node: boolean
  server_name: string
}

export function inspectCertificate(body: CertificateInspectionRequest, signal: AbortSignal) {
  return fetcher<CertificateInspection>('/api/core/certificate-info', { method: 'POST', body, signal, retry: 0 })
}
