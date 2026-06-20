import { ColumnDef } from '@tanstack/react-table'
import { MoreVertical, Trash2, Edit2, RotateCcw, KeyRound, UserRound } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { Badge } from '@/components/ui/badge'
import { APIKeyResponse, AdminBase, RolePermissions } from '@/service/api'
import { dateUtils } from '@/utils/dateFormatter'
import { countEnabledPermissions } from '@/features/admin-roles/components/permission-editor'
import { RolePermissionFormMap } from '@/features/admin-roles/forms/admin-role-form'
import { AdminStatusBadge } from '@/features/admins/components/admin-status-badge'

interface ColumnsProps {
  t: any
  onEdit: (apiKey: APIKeyResponse) => void
  onDelete: (apiKey: APIKeyResponse) => void
  onRevoke: (apiKey: APIKeyResponse) => void
  admins: AdminBase[]
}

function countEnabledResources(permissions: RolePermissions | undefined): number {
  if (!permissions) return 0
  return Object.values(permissions).reduce((total, resource) => {
    if (!resource || typeof resource !== 'object') return total
    return Object.values(resource as Record<string, unknown>).some(value => {
      if (value === true) return true
      return !!value && typeof value === 'object' && Number((value as any).scope) > 0
    })
      ? total + 1
      : total
  }, 0)
}

export const setupColumns = ({ t, onEdit, onDelete, onRevoke, admins }: ColumnsProps): ColumnDef<APIKeyResponse>[] => {
  return [
    {
      accessorKey: 'name',
      header: t('apiKeys.name'),
      cell: ({ row }) => {
        const adminId = row.original.admin_id
        const admin = admins.find(a => a.id === adminId)
        return (
          <div className="flex min-w-0 items-start gap-x-2 px-0.5 py-1">
            <div className="pt-0.5">
              <KeyRound className={row.original.status === 'active' && !row.original.is_expired ? 'text-primary h-4 w-4 shrink-0' : 'text-muted-foreground/70 h-4 w-4 shrink-0'} />
            </div>
            <div className="flex min-w-0 flex-1 flex-col gap-y-1 overflow-hidden">
              <div className="flex min-w-0 items-center gap-x-1.5 overflow-hidden">
                <span className="overflow-hidden text-sm font-medium text-ellipsis whitespace-nowrap">{row.getValue('name')}</span>
                {admin && (
                  <Badge variant="outline" className="flex max-w-28 shrink-0 items-center gap-1 px-1.5 text-[10px] font-normal opacity-80">
                    <UserRound className="h-3 w-3 shrink-0" />
                    <span className="min-w-0 truncate">{admin.username}</span>
                  </Badge>
                )}
              </div>
              {row.original.api_key_trimmed ? (
                <code className="bg-muted/80 inline-block max-w-full truncate rounded px-1.5 py-0.5 font-mono text-xs md:hidden">{row.original.api_key_trimmed}</code>
              ) : null}
            </div>
          </div>
        )
      },
    },
    {
      accessorKey: 'api_key_trimmed',
      header: t('apiKeys.key', { defaultValue: 'API Key' }),
      cell: ({ row }) => {
        const trimmed = row.original.api_key_trimmed
        return trimmed ? <code className="bg-muted/80 inline-block max-w-full truncate rounded px-1.5 py-0.5 font-mono text-xs">{trimmed}</code> : <span className="text-muted-foreground">-</span>
      },
    },
    {
      accessorKey: 'permissions',
      header: t('adminRoles.permissions', { defaultValue: 'Permissions' }),
      cell: ({ row }) => {
        const permissions = row.original.permissions as RolePermissions | undefined
        const count = countEnabledPermissions(permissions as RolePermissionFormMap | undefined)
        const resourceCount = countEnabledResources(permissions)
        if (row.original.inherit_permissions) {
          return (
            <Badge variant="secondary" className="w-fit shrink-0 text-[10px] font-medium">
              {t('apiKeys.inherited', { defaultValue: 'Inherited' })}
            </Badge>
          )
        }
        return (
          <div className="flex min-w-0 flex-wrap items-center gap-1">
            <Badge variant="outline" className="h-5 shrink-0 px-1.5 text-[10px] font-normal">
              {resourceCount} {t('resources', { defaultValue: 'resources' })}
            </Badge>
            {count > 0 && (
              <Badge variant="secondary" className="h-5 shrink-0 px-1.5 text-[10px] font-normal">
                {count} {t('actions', { defaultValue: 'actions' })}
              </Badge>
            )}
          </div>
        )
      },
    },
    {
      accessorKey: 'status',
      header: t('apiKeys.status'),
      cell: ({ row }) => {
        const status = row.getValue('status') as string
        const isExpired = row.original.is_expired
        const resolvedStatus = isExpired ? 'expired' : status || 'active'
        return (
          <div className="flex flex-col gap-y-2 py-1">
            <div className="hidden md:block">
              <AdminStatusBadge isSudo={false} status={resolvedStatus} label={t(`status.${resolvedStatus}`, { defaultValue: resolvedStatus })} />
            </div>
            <div className="md:hidden">
              <AdminStatusBadge compact isSudo={false} status={resolvedStatus} />
            </div>
          </div>
        )
      },
    },
    {
      accessorKey: 'expire_date',
      header: t('apiKeys.expireDate'),
      cell: ({ row }) => {
        const date = row.getValue('expire_date') as string | null
        return <span className={row.original.is_expired ? 'font-medium text-amber-600 dark:text-amber-400' : 'text-muted-foreground'}>{date ? dateUtils.formatDate(date) : t('never')}</span>
      },
    },
    {
      id: 'actions',
      cell: ({ row }) => {
        const apiKey = row.original

        return (
          <DropdownMenu>
            <DropdownMenuTrigger asChild onClick={e => e.stopPropagation()}>
              <Button type="button" variant="ghost" size="icon" className="h-8 w-8">
                <span className="sr-only">Open menu</span>
                <MoreVertical className="!h-3.5 !w-3.5" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem
                onSelect={e => {
                  e.preventDefault()
                  e.stopPropagation()
                  onEdit(apiKey)
                }}
              >
                <Edit2 className="mr-2 h-4 w-4" />
                {t('edit')}
              </DropdownMenuItem>
              <DropdownMenuItem
                onSelect={e => {
                  e.preventDefault()
                  e.stopPropagation()
                  onRevoke(apiKey)
                }}
              >
                <RotateCcw className="mr-2 h-4 w-4" />
                {t('apiKeys.revoke')}
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                className="text-destructive focus:text-destructive"
                onSelect={e => {
                  e.preventDefault()
                  e.stopPropagation()
                  onDelete(apiKey)
                }}
              >
                <Trash2 className="mr-2 h-4 w-4" />
                {t('delete')}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        )
      },
    },
  ]
}
