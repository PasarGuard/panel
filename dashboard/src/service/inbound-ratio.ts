import { orvalFetcher } from './http'

/**
 * Handwritten counterpart of the orval client for the inbound usage-ratio endpoints
 * (`app/routers/inbound_ratio.py`). Kept out of the generated `api/index.ts` so a
 * regeneration cannot drop it.
 */
export interface InboundRatio {
  tag: string
  protocol?: string | null
  network?: string | null
  security?: string | null
  usage_coefficient: number
  hosts_count: number
  groups: string[]
  cores: string[]
}

export const getInboundRatios = async (): Promise<InboundRatio[]> => {
  return orvalFetcher<InboundRatio[]>('/api/inbound-ratio/usages', { method: 'GET' })
}

export const updateInboundRatio = async (tag: string, usage_coefficient: number): Promise<InboundRatio> => {
  return orvalFetcher<InboundRatio>(`/api/inbound-ratio/${encodeURIComponent(tag)}/usage`, {
    method: 'PATCH',
    body: JSON.stringify({ usage_coefficient }),
    headers: { 'Content-Type': 'application/json' },
  })
}

export const getGetInboundRatiosQueryKey = () => ['/api/inbound-ratio/usages'] as const
