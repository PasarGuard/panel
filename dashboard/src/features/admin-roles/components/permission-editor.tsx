import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'

import { cn } from '@/lib/utils'

import { PERMISSION_GROUPS, PermissionAction, RolePermissionFormMap, RoleScope } from '@/features/admin-roles/forms/admin-role-form'

interface PermissionEditorProps {
  permissions?: RolePermissionFormMap
  onPermissionsChange: (permissions: RolePermissionFormMap) => void
  className?: string
}

export function countEnabledPermissions(permissions?: RolePermissionFormMap | null): number {
  let count = 0
  for (const value of Object.values(permissions || {})) {
    if (!value || typeof value !== 'object') continue
    for (const inner of Object.values(value as Record<string, unknown>)) {
      if (inner === true) count += 1
      else if (inner && typeof inner === 'object' && Number((inner as any).scope) > 0) count += 1
    }
  }
  return count
}

export function PermissionCountBadge({ permissions }: { permissions?: RolePermissionFormMap | null }) {
  const { t } = useTranslation()
  const total = useMemo(() => countEnabledPermissions(permissions), [permissions])

  if (!total) return null
  return (
    <Badge variant="secondary" className="ms-2 shrink-0 text-[10px]">
      {t('adminRoles.permissionCount', { count: total, defaultValue: '{{count}} permissions' })}
    </Badge>
  )
}

export function PermissionEditor({ permissions, onPermissionsChange, className }: PermissionEditorProps) {
  const { t } = useTranslation()

  const setPermission = (resource: string, action: string, value: boolean | { scope: RoleScope }) => {
    const next: RolePermissionFormMap = { ...(permissions || {}) }
    next[resource] = { ...(next[resource] || {}), [action]: value }
    onPermissionsChange(next)
  }

  const setGroupAll = (group: { actions: PermissionAction[] }, mode: 'all' | 'none') => {
    const next: RolePermissionFormMap = { ...(permissions || {}) }
    for (const item of group.actions) {
      const inner = { ...(next[item.resource] || {}) }
      if (item.scoped) inner[item.action] = { scope: mode === 'all' ? 2 : 0 }
      else inner[item.action] = mode === 'all'
      next[item.resource] = inner
    }
    onPermissionsChange(next)
  }

  const formatActionLabel = (item: PermissionAction) => {
    const resourceLabel = t(`adminRoles.resources.${item.resource}`, { defaultValue: humanizeKey(item.resource) })
    const actionLabel = t(`adminRoles.actions.${item.resource}.${item.action}`, {
      defaultValue: t(`adminRoles.actions.common.${item.action}`, { defaultValue: humanizeKey(item.action) }),
    })
    return { resourceLabel, actionLabel }
  }

  return (
    <div className={cn('space-y-3', className)}>
      <p className="text-muted-foreground text-xs">{t('adminRoles.roleFormHint', { defaultValue: 'Scoped actions use none, own, or all. Other actions are boolean toggles.' })}</p>
      {PERMISSION_GROUPS.map(group => {
        const enabledInGroup = group.actions.reduce((acc, item) => {
          const value = permissions?.[item.resource]?.[item.action]
          if (value === true) return acc + 1
          if (value && typeof value === 'object' && Number((value as any).scope) > 0) return acc + 1
          return acc
        }, 0)

        const groupLabel = t(`adminRoles.groups.${group.labelKey}`)
        const showResourcePrefix = group.actions.some((a, _, all) => all.some(b => b !== a && b.action === a.action && b.resource !== a.resource))

        return (
          <div key={group.labelKey} className="bg-background rounded-md border">
            <div className="flex items-center justify-between gap-2 border-b px-3 py-2">
              <div className="flex min-w-0 items-center gap-2">
                <span className="text-sm font-medium">{groupLabel}</span>
                <span className="text-muted-foreground text-[10px]">
                  {enabledInGroup}/{group.actions.length}
                </span>
              </div>
              <div className="flex items-center gap-1">
                <Button type="button" size="sm" variant="ghost" className="h-7 px-2 text-xs" onClick={() => setGroupAll(group, 'all')}>
                  {t('selectAll', { defaultValue: 'Select all' })}
                </Button>
                <Button type="button" size="sm" variant="ghost" className="h-7 px-2 text-xs" onClick={() => setGroupAll(group, 'none')}>
                  {t('deselectAll', { defaultValue: 'Clear' })}
                </Button>
              </div>
            </div>
            <div className="grid gap-2 p-2 sm:grid-cols-2">
              {group.actions.map(item => {
                const current = permissions?.[item.resource]?.[item.action]
                const isScope = current && typeof current === 'object'
                const scopeValue: RoleScope = isScope ? (Number((current as any).scope) as RoleScope) : current === true ? 2 : 0
                const boolValue = current === true
                const { resourceLabel, actionLabel } = formatActionLabel(item)

                return (
                  <div key={`${item.resource}.${item.action}`} className="bg-muted/40 flex min-h-10 items-center justify-between gap-3 rounded-md px-3 py-2">
                    <div className="flex min-w-0 flex-col gap-0.5">
                      <span className="truncate text-xs font-medium">{showResourcePrefix ? `${resourceLabel} - ${actionLabel}` : actionLabel}</span>
                      {item.scoped && <span className="text-muted-foreground text-[10px]">{t('adminRoles.scopedBadge', { defaultValue: 'Scoped' })}</span>}
                    </div>
                    {item.scoped ? (
                      <Select value={String(scopeValue)} onValueChange={next => setPermission(item.resource, item.action, { scope: Number(next) as RoleScope })}>
                        <SelectTrigger className="h-8 w-28">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="0">{t('adminRoles.scopes.none', { defaultValue: 'None' })}</SelectItem>
                          <SelectItem value="1">{t('adminRoles.scopes.own', { defaultValue: 'Own' })}</SelectItem>
                          <SelectItem value="2">{t('adminRoles.scopes.all', { defaultValue: 'All' })}</SelectItem>
                        </SelectContent>
                      </Select>
                    ) : (
                      <Switch checked={boolValue} onCheckedChange={checked => setPermission(item.resource, item.action, checked)} />
                    )}
                  </div>
                )
              })}
            </div>
          </div>
        )
      })}
    </div>
  )
}

function humanizeKey(key: string) {
  return key.replace(/_/g, ' ').replace(/\b\w/g, char => char.toUpperCase())
}
