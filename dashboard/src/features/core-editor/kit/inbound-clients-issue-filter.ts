import type { CoreKitValidationIssue } from '@pasarguard/core-kit'
import type { Issue } from '@pasarguard/xray-config-kit'

/**
 * Inbounds intentionally use empty `clients` in this editor until clients are managed in-product.
 * Use {@link filterXrayInboundDraftIssuesForEditor} for inbound draft UI and
 * {@link filterCoreKitIssuesHidingInboundClients} inside {@link validateProfileForPersist} for save.
 * Additional empty-JSON blockers from xray-config-kit strict compile are merged in `validateProfileForPersist` (see `xray-adapter.ts`).
 */
export function filterXrayInboundDraftIssuesForEditor(issues: Issue[]): Issue[] {
  return issues.filter(i => !isHiddenInboundClientsXrayIssue(i))
}

export function filterCoreKitIssuesHidingInboundClients(issues: CoreKitValidationIssue[]): CoreKitValidationIssue[] {
  return issues.filter(i => !isHiddenInboundClientsCoreKitIssue(i))
}

function isHiddenInboundClientsXrayIssue(issue: Issue): boolean {
  const path = issue.path.replace(/\\/g, '/').toLowerCase()
  if (path === '/clients' || path.includes('/clients')) return true
  const msg = issue.message.toLowerCase()
  if (msg.includes('enabled clients') || msg.includes('no enabled client')) return true
  return false
}

function isHiddenInboundClientsCoreKitIssue(issue: CoreKitValidationIssue): boolean {
  const path = (issue.path ?? '').toLowerCase()
  const msg = (issue.message ?? '').toLowerCase()
  if (path.includes('clients') && (path.includes('inbound') || path.includes('/inbounds'))) return true
  if (path.includes('/clients') || path.endsWith('clients')) return true
  if ((msg.includes('vless') || msg.includes('vmess') || msg.includes('trojan') || msg.includes('inbound')) && msg.includes('client')) return true
  if (msg.includes('enabled clients') || msg.includes('no enabled client')) return true
  return false
}
