import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { cn } from '@/lib/utils'
import type { CoreKitValidationIssue } from '@pasarguard/core-kit'
import type { Issue } from '@pasarguard/xray-config-kit'
import type { WireGuardValidationIssue } from '@pasarguard/wireguard-config-kit'
import { useTranslation } from 'react-i18next'

export type ValidationListItem =
  | { source: 'core-kit'; issue: CoreKitValidationIssue }
  | { source: 'xray'; issue: Issue }
  | { source: 'wireguard'; issue: WireGuardValidationIssue }

export function validationListItemPath(item: ValidationListItem): string {
  const p = item.issue.path
  return typeof p === 'string' ? p : ''
}

/** Same semantics as the “Validation errors” list (not warnings / info-only). */
export function filterValidationListBlockingErrors(items: ValidationListItem[]): ValidationListItem[] {
  return items.filter(i => {
    if (i.source === 'core-kit') return i.issue.severity !== 'warning' && i.issue.severity !== 'info'
    if (i.source === 'xray') return i.issue.severity !== 'warning' && i.issue.severity !== 'info'
    return true
  })
}

export function formatValidationListItemLine(row: ValidationListItem): string {
  if (row.source === 'core-kit') return `${row.issue.path}: ${row.issue.message}`
  if (row.source === 'xray') {
    const code = row.issue.code ? ` [${row.issue.code}]` : ''
    return `${row.issue.path}: ${row.issue.message}${code}`
  }
  return `${row.issue.path}: ${row.issue.message}`
}

export function formatValidationListItemsToastLines(items: ValidationListItem[], limit = 8): string {
  return items.slice(0, limit).map(formatValidationListItemLine).join('\n')
}

/** Keep only issues under a JSON-pointer prefix (e.g. `/inbounds/3` for the third inbound; kit paths are 1-based). */
export function filterValidationListItemsByPathPrefix(
  items: ValidationListItem[],
  prefix: string | undefined,
): ValidationListItem[] {
  if (prefix == null || prefix.trim() === '') return items
  const base = prefix.replace(/\/$/, '')
  return items.filter(item => {
    const p = validationListItemPath(item)
    if (p === '') return false
    return p === base || p.startsWith(`${base}/`)
  })
}

interface ValidationSummaryProps {
  items: ValidationListItem[]
  className?: string
}

const DISPLAY_LIMIT = 48

/** Lists blocking issues from the Xray config kit (strict compile), core-kit, WireGuard, etc. */
export function ValidationSummary({ items, className }: ValidationSummaryProps) {
  const { t } = useTranslation()
  if (items.length === 0) return null
  const errors = filterValidationListBlockingErrors(items)
  const list = errors.length > 0 ? errors : items
  const tone = errors.length > 0 ? 'destructive' : 'default'
  const displayed = list.slice(0, DISPLAY_LIMIT)
  const rest = list.length - displayed.length

  return (
    <Alert variant={tone === 'destructive' ? 'destructive' : 'default'} className={cn(className)}>
      <AlertTitle>{errors.length > 0 ? 'Validation errors' : 'Warnings'}</AlertTitle>
      <AlertDescription className="space-y-2">
        <ul className="mt-1 list-inside list-disc space-y-1 text-sm">
          {displayed.map((row, idx) => (
            <li key={idx}>
              {row.source === 'core-kit' && (
                <>
                  {row.issue.path}: {row.issue.message}
                </>
              )}
              {row.source === 'xray' && (
                <>
                  {row.issue.path}: {row.issue.message}
                  {row.issue.code ? (
                    <span className="ml-1 text-[0.8em] opacity-80">[{row.issue.code}]</span>
                  ) : null}
                  {row.issue.suggestion ? <span className="block pl-4 text-xs opacity-90">→ {row.issue.suggestion}</span> : null}
                </>
              )}
              {row.source === 'wireguard' && (
                <>
                  {row.issue.path}: {row.issue.message}
                </>
              )}
            </li>
          ))}
        </ul>
        {rest > 0 ? (
          <p className="text-xs opacity-90">
            {t('coreEditor.validationMore', { count: rest, defaultValue: `…and ${rest} more` })}
          </p>
        ) : null}
      </AlertDescription>
    </Alert>
  )
}
