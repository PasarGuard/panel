import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { Crown, Shield, ShieldCheck } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { ListColumn } from '@/components/common/list-generator'
import { cn } from '@/lib/utils'
import { AdminRoleResponse } from '@/service/api'

import { BUILT_IN_ROLE_IDS } from '@/features/admin-roles/forms/admin-role-form'
import AdminRoleActionsMenu from '@/features/admin-roles/components/admin-role-actions-menu'

interface UseAdminRolesListColumnsProps {
  onEdit: (role: AdminRoleResponse) => void
  onDuplicate: (role: AdminRoleResponse) => void
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

export const useAdminRolesListColumns = ({ onEdit, onDuplicate }: UseAdminRolesListColumnsProps) => {
  const { t } = useTranslation()

  return useMemo<ListColumn<AdminRoleResponse>[]>(
    () => [
      {
        id: 'name',
        header: t('name', { defaultValue: 'Name' }),
        width: '3fr',
        cell: role => {
          const builtIn = BUILT_IN_ROLE_IDS.has(role.id) && !role.is_owner
          const RoleIcon = role.is_owner ? Crown : builtIn ? ShieldCheck : Shield
          return (
            <div className="flex min-w-0 items-center gap-2">
              <div className={cn('flex h-7 w-7 shrink-0 items-center justify-center rounded-full', role.is_owner ? 'bg-violet-500/10 text-violet-500' : 'bg-primary/10 text-primary')}>
                <RoleIcon className="h-3.5 w-3.5" />
              </div>
              <span className="min-w-0 truncate font-medium">{t(`adminRoles.names.${role.name}`, { defaultValue: role.name })}</span>
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
          )
        },
      },
      {
        id: 'permissions',
        header: t('adminRoles.permissions', { defaultValue: 'Permissions' }),
        width: '1fr',
        cell: role => <span className="text-muted-foreground truncate text-xs">{countResourcePermissions(role)}</span>,
        hideOnMobile: true,
      },
      {
        id: 'limits',
        header: t('adminRoles.limits', { defaultValue: 'Limits' }),
        width: '1fr',
        cell: role => <span className="text-muted-foreground truncate text-xs">{Object.keys(role.limits || {}).length}</span>,
        hideOnMobile: true,
      },
      {
        id: 'actions',
        header: '',
        width: '64px',
        align: 'end',
        hideOnMobile: true,
        cell: role => <AdminRoleActionsMenu role={role} onEdit={onEdit} onDuplicate={onDuplicate} />,
      },
    ],
    [t, onEdit, onDuplicate],
  )
}
