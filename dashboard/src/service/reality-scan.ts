import { orvalFetcher } from './http'

export interface RealityScanRequest {
  target: string
  sni?: string | null
  timeout?: number | null
}

export interface RealityScanResult {
  target: string
  host: string
  ip: string | null
  port: number
  sni: string | null
  feasible: boolean
  tls13: boolean
  tls_version: string | null
  h2: boolean
  alpn: string | null
  x25519: boolean | null
  post_quantum: boolean | null
  curve: string | null
  h3: boolean
  cert_valid: boolean
  cert_subject: string | null
  cert_issuer: string | null
  not_after: string | null
  server_names: string[]
  latency_ms: number | null
  reason: string | null
}

export const scanRealityTarget = (data: RealityScanRequest, signal?: AbortSignal) => {
  return orvalFetcher<RealityScanResult>({ url: '/api/core/reality-scan', method: 'POST', data, signal })
}
