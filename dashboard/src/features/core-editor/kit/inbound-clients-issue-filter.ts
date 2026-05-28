import type { CoreKitValidationIssue } from '@pasarguard/core-kit'
import type { Issue } from '@pasarguard/xray-config-kit'

/** Hide only empty-client noise from default inbounds; malformed user-managed client objects should still surface. */
export function filterXrayInboundDraftIssuesForEditor(issues: Issue[]): Issue[] {
  return issues.filter(i => !isHiddenInboundClientsXrayIssue(i))
}

export function filterCoreKitIssuesHidingInboundClients(issues: CoreKitValidationIssue[]): CoreKitValidationIssue[] {
  return issues.filter(i => !isHiddenInboundClientsCoreKitIssue(i) && !isStaleHysteriaUdpmasksCoreKitIssue(i))
}

function isHiddenInboundClientsXrayIssue(issue: Issue): boolean {
  const msg = issue.message.toLowerCase()
  if (msg.includes('enabled clients') || msg.includes('no enabled client')) return true
  return false
}

function isHiddenInboundClientsCoreKitIssue(issue: CoreKitValidationIssue): boolean {
  const msg = (issue.message ?? '').toLowerCase()
  if (msg.includes('enabled clients') || msg.includes('no enabled client')) return true
  return false
}

function isStaleHysteriaUdpmasksCoreKitIssue(issue: CoreKitValidationIssue): boolean {
  return issue.code === 'XCK_XRAY_STRICT_UNKNOWN_FIELD' && issue.path.endsWith('/streamSettings/hysteriaSettings/udpmasks')
}
