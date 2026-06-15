import { AdminDetails } from '@/service/api'
import { ColumnDef, Row, Table } from '@tanstack/react-table'
import { ChevronDown, MoreVertical, Pen, Power, PowerOff, RefreshCw, Trash2, Users, UserCheck, UserMinus, UserRound, UserRoundKey, UserX } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { AdminStatusBadge } from './admin-status-badge'
import UsageSliderCompact from '@/components/common/usage-slider-compact'
import { Checkbox } from '@/components/ui/checkbox'
import { cn } from '@/lib/utils'
import { isOwner } from '@/utils/rbac'

interface ColumnSetupProps {
  t: (key: string) => string
  handleSort: (column: string) => void
  filters: { sort?: string }
  currentAdminUsername?: string
  onEdit?: (admin: AdminDetails) => void
  onDelete?: (admin: AdminDetails) => void
  toggleStatus?: (admin: AdminDetails) => void
  onResetUsage?: (admin: AdminDetails) => void
  onDisableAllActiveUsers?: (admin: AdminDetails) => void
  onActivateAllDisabledUsers?: (admin: AdminDetails) => void
  onRemoveAllUsers?: (admin: AdminDetails) => void
}

const createSortButton = (
  column: string,
  label: string,
  t: (key: string) => string,
  handleSort: (column: string) => void,
  filters: {
    sort?: string
  },
  className?: string,
  desktopLabel?: string,
) => {
  const handleClick = (e: React.MouseEvent) => {
    e.preventDefault()
    e.stopPropagation()
    handleSort(column)
  }

  return (
    <button type="button" onClick={handleClick} className={cn('flex w-full items-center gap-1', className)}>
      <div className="text-xs">
        {desktopLabel ? (
          <>
            <span className="md:hidden">{t(label)}</span>
            <span className="hidden md:inline">{t(desktopLabel)}</span>
          </>
        ) : (
          t(label)
        )}
      </div>
      {filters.sort && (filters.sort === column || filters.sort === '-' + column) && (
        <ChevronDown size={16} className={`transition-transform duration-300 ${filters.sort === column ? 'rotate-180' : ''} ${filters.sort === '-' + column ? 'rotate-0' : ''} `} />
      )}
    </button>
  )
}

const getAdminStatus = (admin: AdminDetails) => admin.status || (admin.is_disabled ? 'disabled' : 'active')
const isAdminDisabled = (admin: AdminDetails) => getAdminStatus(admin) === 'disabled'
const getAdminRoleIcon = (owner: boolean) => (owner ? UserRoundKey : UserRound)

export const setupColumns = ({
  t,
  handleSort,
  filters,
  currentAdminUsername,
  onEdit,
  onDelete,
  toggleStatus,
  onResetUsage,
  onDisableAllActiveUsers,
  onActivateAllDisabledUsers,
  onRemoveAllUsers,
}: ColumnSetupProps): ColumnDef<AdminDetails>[] => [
  {
    id: 'select',
    header: ({ table }: { table: Table<AdminDetails> }) => (
      <div className="flex h-5 items-center justify-center">
        <Checkbox
          aria-label={t('selectAll')}
          className="border-muted-foreground/40 data-[state=checked]:border-primary h-3.5 w-3.5 rounded-[3px]"
          checked={table.getIsAllPageRowsSelected() || (table.getIsSomePageRowsSelected() && 'indeterminate')}
          onCheckedChange={value => table.toggleAllPageRowsSelected(!!value)}
          onClick={event => event.stopPropagation()}
          onPointerDown={event => event.stopPropagation()}
          onKeyDown={event => event.stopPropagation()}
        />
      </div>
    ),
    cell: ({ row }: { row: Row<AdminDetails> }) => (
      <div className="flex h-5 items-center justify-center">
        {row.getCanSelect() ? (
          <Checkbox
            aria-label={t('select')}
            className="border-muted-foreground/40 bg-background data-[state=checked]:border-primary data-[state=indeterminate]:border-primary data-[state=checked]:bg-primary data-[state=indeterminate]:bg-primary data-[state=checked]:text-primary-foreground data-[state=indeterminate]:text-primary-foreground h-3.5 w-3.5 rounded-[3px]"
            checked={row.getIsSelected()}
            onCheckedChange={value => row.toggleSelected(!!value)}
            onClick={event => event.stopPropagation()}
            onPointerDown={event => event.stopPropagation()}
            onKeyDown={event => event.stopPropagation()}
          />
        ) : (
          <div className="h-3.5 w-3.5" />
        )}
      </div>
    ),
    enableSorting: false,
    enableHiding: false,
    size: 40,
  },
  {
    accessorKey: 'username',
    header: () => createSortButton('username', 'username', t, handleSort, filters),
    cell: ({ row }) => {
      const RoleIcon = getAdminRoleIcon(isOwner(row.original))

      return (
        <div className="overflow-hidden pl-0 font-medium text-ellipsis whitespace-nowrap md:pl-1">
          <div className="flex items-start gap-x-2 px-0.5 py-1">
            <div className="pt-0.5">
              <RoleIcon className={getAdminStatus(row.original) === 'disabled' ? 'text-muted-foreground/60 h-4 w-4' : cn('h-4 w-4', isOwner(row.original) ? 'text-violet-500' : 'text-primary')} />
            </div>
            <div className="flex min-w-0 flex-1 flex-col gap-y-0.5 overflow-hidden text-ellipsis whitespace-nowrap">
              <div className="flex items-center gap-x-1.5 overflow-hidden">
                <span className="overflow-hidden text-sm font-medium text-ellipsis whitespace-nowrap">{row.getValue('username')}</span>
              </div>
            </div>
          </div>
        </div>
      )
    },
  },
  {
    id: 'status',
    header: () => <div className="flex items-center text-xs capitalize">{t('usersTable.status')}</div>,
    cell: ({ row }) => {
      const status = getAdminStatus(row.original)
      return (
        <div className="flex flex-col gap-y-2 py-1">
          <div className="hidden md:block">
            <AdminStatusBadge isSudo={isOwner(row.original)} status={status} label={t(`status.${status}`)} />
          </div>
          <div className="md:hidden">
            <AdminStatusBadge compact isSudo={isOwner(row.original)} status={status} />
          </div>
        </div>
      )
    },
  },
  {
    accessorKey: 'total_users',
    header: () => <div className="flex items-center text-xs capitalize">{t('admins.total.users')}</div>,
    cell: ({ row }) => {
      const total = (row.getValue('total_users') as number | null) || 0
      const overrideMax = row.original.permission_overrides?.max_users
      const roleMax = row.original.role?.limits?.max_users
      const effectiveMax = typeof overrideMax === 'number' && overrideMax > 0 ? overrideMax : typeof roleMax === 'number' && roleMax > 0 ? roleMax : null
      return (
        <div className="flex items-center gap-2 whitespace-nowrap">
          <Users className="h-4 w-4" />
          <span dir="ltr" className="text-xs">
            {total}
            {effectiveMax != null ? ` / ${effectiveMax}` : ''}
          </span>
        </div>
      )
    },
  },
  {
    accessorKey: 'used_traffic',
    header: () => createSortButton('used_traffic', 'dataUsage', t, handleSort, filters, 'justify-start', 'admins.used.traffic'),
    cell: ({ row }) => (
      <div className="flex w-full items-center justify-between gap-1 py-1">
        <UsageSliderCompact
          total={row.original.data_limit}
          used={row.original.used_traffic || 0}
          totalUsedTraffic={row.original.lifetime_used_traffic ?? undefined}
          status={getAdminStatus(row.original)}
        />
      </div>
    ),
  },
  {
    id: 'actions',
    cell: ({ row }) => {
      const isOwnerTarget = isOwner(row.original)
      const nonDestructiveActionCount =
        (onEdit ? 1 : 0) +
        (onResetUsage ? 1 : 0) +
        (!isOwnerTarget && toggleStatus ? 1 : 0) +
        (!isOwnerTarget && onDisableAllActiveUsers ? 1 : 0) +
        (!isOwnerTarget && onActivateAllDisabledUsers ? 1 : 0) +
        (!isOwnerTarget && onRemoveAllUsers ? 1 : 0)
      const canDeleteAdmin = !isOwnerTarget && row.original.username !== currentAdminUsername && !!onDelete
      const hasActions = nonDestructiveActionCount > 0 || canDeleteAdmin

      if (!hasActions) return null

      return (
        <div className="flex items-center justify-center gap-2">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button type="button" variant="ghost" size="icon">
                <MoreVertical className="h-4 w-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              {onEdit && (
                <DropdownMenuItem
                  onSelect={e => {
                    e.preventDefault()
                    e.stopPropagation()
                    onEdit(row.original)
                  }}
                >
                  <Pen className="mr-2 h-4 w-4" />
                  {t('edit')}
                </DropdownMenuItem>
              )}
              {onResetUsage && (
                <DropdownMenuItem
                  onSelect={e => {
                    e.preventDefault()
                    e.stopPropagation()
                    onResetUsage(row.original)
                  }}
                >
                  <RefreshCw className="mr-2 h-4 w-4" />
                  {t('admins.reset')}
                </DropdownMenuItem>
              )}
              {!isOwnerTarget && toggleStatus && (
                <DropdownMenuItem
                  onSelect={e => {
                    e.preventDefault()
                    e.stopPropagation()
                    toggleStatus(row.original)
                  }}
                >
                  {isAdminDisabled(row.original) ? <Power className="mr-2 h-4 w-4" /> : <PowerOff className="mr-2 h-4 w-4" />}
                  {isAdminDisabled(row.original) ? t('enable') : t('disable')}
                </DropdownMenuItem>
              )}
              {!isOwnerTarget && onDisableAllActiveUsers && (
                <DropdownMenuItem
                  onSelect={e => {
                    e.preventDefault()
                    e.stopPropagation()
                    onDisableAllActiveUsers(row.original)
                  }}
                >
                  <UserMinus className="mr-2 h-4 w-4" />
                  {t('admins.disableAllActiveUsers')}
                </DropdownMenuItem>
              )}
              {!isOwnerTarget && onActivateAllDisabledUsers && (
                <DropdownMenuItem
                  onSelect={e => {
                    e.preventDefault()
                    e.stopPropagation()
                    onActivateAllDisabledUsers(row.original)
                  }}
                >
                  <UserCheck className="mr-2 h-4 w-4" />
                  {t('admins.activateAllDisabledUsers')}
                </DropdownMenuItem>
              )}
              {!isOwnerTarget && onRemoveAllUsers && (
                <DropdownMenuItem
                  className="text-destructive"
                  onSelect={e => {
                    e.preventDefault()
                    e.stopPropagation()
                    onRemoveAllUsers(row.original)
                  }}
                >
                  <UserX className="mr-2 h-4 w-4" />
                  {t('admins.removeAllUsers')}
                </DropdownMenuItem>
              )}
              {canDeleteAdmin && (
                <>
                  {nonDestructiveActionCount > 0 && <DropdownMenuSeparator />}
                  <DropdownMenuItem
                    className="text-destructive"
                    onSelect={e => {
                      e.preventDefault()
                      e.stopPropagation()
                      onDelete(row.original)
                    }}
                  >
                    <Trash2 className="mr-2 h-4 w-4" />
                    {t('delete')}
                  </DropdownMenuItem>
                </>
              )}
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      )
    },
  },
  {
    id: 'chevron',
    cell: () => <div className="flex flex-wrap justify-between"></div>,
  },
]
