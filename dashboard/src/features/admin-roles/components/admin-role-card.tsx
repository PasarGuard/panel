import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Crown, Shield, ShieldCheck } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Card } from '@/components/ui/card'
import { cn } from '@/lib/utils'
import { AdminRoleResponse } from '@/service/api'

import { BUILT_IN_ROLE_IDS } from '@/features/admin-roles/forms/admin-role-form'
import AdminRoleActionsMenu from './admin-role-actions-menu'

interface AdminRoleCardProps {
  role: AdminRoleResponse
  onEdit: (role: AdminRoleResponse) => void
  onDuplicate: (role: AdminRoleResponse) => void
  selectionControl?: ReactNode
  selected?: boolean
}

const countResourcePermissions = (role: AdminRoleResponse) => {
  const permissions = role.permissions || {}
  let total = 0
  for (const value of Object.values(permissions)) {
    if (!value || typeof value !== 'object') continue
    total += Object.keys(value as Record<string, unknown>).length
  }
  return total
}

export default function AdminRoleCard({ role, onEdit, onDuplicate, selectionControl, selected = false }: AdminRoleCardProps) {
  const { t } = useTranslation()
  const builtIn = BUILT_IN_ROLE_IDS.has(role.id) && !role.is_owner
  const RoleIcon = role.is_owner ? Crown : builtIn ? ShieldCheck : Shield
  const permissionCount = countResourcePermissions(role)
  const limitsCount = Object.keys(role.limits || {}).length
  const featureCount = Object.keys(role.features || {}).length + 2

  const localizedName = t(`adminRoles.names.${role.name}`, { defaultValue: role.name })

  return (
    <Card className={cn('group hover:bg-accent relative flex cursor-pointer flex-col gap-3 px-4 py-4 transition-colors', selected && 'border-primary/50 bg-accent/30')} onClick={() => onEdit(role)}>
      <div className="flex items-start gap-3">
        {selectionControl ? <div className="pt-1">{selectionControl}</div> : null}
        <div className={cn('flex h-9 w-9 shrink-0 items-center justify-center rounded-full', role.is_owner ? 'bg-violet-500/10 text-violet-500' : 'bg-primary/10 text-primary')}>
          <RoleIcon className="h-4 w-4" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex min-w-0 items-center gap-2">
            <span className="min-w-0 truncate font-medium">{localizedName}</span>
            {role.is_owner && (
              <Badge variant="secondary" className="shrink-0 text-[10px]">
                {t('adminRoles.ownerRole', { defaultValue: 'owner' })}
              </Badge>
            )}
            {builtIn && (
              <Badge variant="outline" className="shrink-0 text-[10px]">
                {t('adminRoles.builtInRole', { defaultValue: 'built-in' })}
              </Badge>
            )}
          </div>
          <div className="text-muted-foreground mt-0.5 truncate text-xs">
            {t('adminRoles.id', { defaultValue: 'ID' })} {role.id}
          </div>
        </div>
        <AdminRoleActionsMenu role={role} onEdit={onEdit} onDuplicate={onDuplicate} />
      </div>

      <div className="text-muted-foreground flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
        <span>{t('adminRoles.permissionCount', { count: permissionCount, defaultValue: '{{count}} permissions' })}</span>
        <span aria-hidden>·</span>
        <span>{t('adminRoles.limitFeatureCount', { limits: limitsCount, features: featureCount, defaultValue: '{{limits}} limits, {{features}} feature flags' })}</span>
      </div>
    </Card>
  )
}
