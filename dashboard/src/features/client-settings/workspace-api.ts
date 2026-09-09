import { fetcher } from '@/service/http'
import type { WorkspaceChange, WorkspaceSnapshot } from './workspace-model'

export interface WorkspacePreview {
  diagnostics: { errors: string[]; exceptions: string[] }
  user_agent: string
  user_status: string
  matched_rule: { index: number; pattern: string; target: string } | null
  effective_format: string | null
  media_type: string | null
  source: { kind: string; id: number | null; name: string | null } | null
  app_headers: Record<string, string>
  content: string | null
  content_encoding: string | null
  happ: { name: string; transport: string; action: string; enabled: boolean | null; deeplink: string; decoded: Record<string, unknown> } | null
}
export const getWorkspace = (signal?: AbortSignal) => fetcher<WorkspaceSnapshot>('/api/client_template/workspace', { signal })
export const applyWorkspace = (body: WorkspaceChange) => fetcher<WorkspaceSnapshot>('/api/client_template/apply', { method: 'POST', body })
export const previewWorkspace = (body: WorkspaceChange & { user_id: number; user_agent: string }) => fetcher<WorkspacePreview>('/api/client_template/preview', { method: 'POST', body })
