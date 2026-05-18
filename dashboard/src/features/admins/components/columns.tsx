import { AdminDetails } from '@/service/api'
import { ColumnDef, Row, Table } from '@tanstack/react-table'
import { ChevronDown, MoreVertical, Pen, Power, PowerOff, RefreshCw, Trash2, Users, UserCheck, UserMinus, UserRound, UserRoundKey, UserX } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { formatBytes } from '@/utils/formatByte.ts'
import { AdminStatusBadge } from './admin-status-badge'
import { Checkbox } from '@/components/ui/checkbox'
import { cn } from '@/lib/utils'
import { isOwner, roleLabel } from '@/utils/rbac'

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
const getAdminStatusDotClassName = (admin: AdminDetails) => {
  if (isAdminDisabled(admin)) return 'border border-gray-400 shadow-sm dark:border-gray-600'
  if (getAdminStatus(admin) === 'limited') return 'bg-red-500 shadow-sm'
  return 'bg-green-500 shadow-sm'
}
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
            className="h-3.5 w-3.5 rounded-[3px] border-muted-foreground/40 data-[state=checked]:border-primary"
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
              className="h-3.5 w-3.5 rounded-[3px] border-muted-foreground/40 bg-background data-[state=checked]:border-primary data-[state=indeterminate]:border-primary data-[state=checked]:bg-primary data-[state=indeterminate]:bg-primary data-[state=checked]:text-primary-foreground data-[state=indeterminate]:text-primary-foreground"
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
          <div className="overflow-hidden text-ellipsis whitespace-nowrap pl-0 font-medium md:pl-1">
            <div className="flex items-start gap-x-2 px-0.5 py-1">
              <div className="pt-0.5 md:hidden">
                <RoleIcon className={getAdminStatus(row.original) === 'disabled' ? 'h-4 w-4 text-muted-foreground/60' : cn('h-4 w-4', isOwner(row.original) ? 'text-violet-500' : 'text-primary')} />
              </div>
              <div className="hidden pt-1 md:block">
                <div className={cn('min-h-[10px] min-w-[10px] rounded-full', getAdminStatusDotClassName(row.original))} />
              </div>
              <div className="flex min-w-0 flex-1 flex-col gap-y-0.5 overflow-hidden text-ellipsis whitespace-nowrap">
                <div className="flex items-center gap-x-1.5 overflow-hidden">
                  <span className="overflow-hidden text-ellipsis whitespace-nowrap text-sm font-medium">{row.getValue('username')}</span>
                </div>
              </div>
            </div>
          </div>
        )
      },
    },
    {
      id: 'status',
      header: () => <div className="flex items-center justify-center text-xs capitalize">{t('usersTable.status')}</div>,
      cell: ({ row }) => (
        <div className="flex items-center justify-center">
          <AdminStatusBadge compact isSudo={isOwner(row.original)} status={getAdminStatus(row.original)} />
        </div>
      ),
    },
    {
      accessorKey: 'used_traffic',
      header: () => createSortButton('used_traffic', 'dataUsage', t, handleSort, filters, 'justify-start', 'admins.used.traffic'),
      cell: ({ row }) => {
        const traffic = row.getValue('used_traffic') as number | null
        const dataLimit = row.original.data_limit
        const isUnlimited = !dataLimit || dataLimit === 0
        return (
          <div className="flex w-full items-center text-left text-xs font-medium text-foreground">
            <span dir="ltr" className="whitespace-nowrap">
              {formatBytes(traffic || 0)}
              {!isUnlimited ? ` / ${formatBytes(dataLimit)}` : ''}
            </span>
          </div>
        )
      },
    },
    {
      accessorKey: 'lifetime_used_traffic',
      header: () => <div className="flex items-center text-xs capitalize">{t('statistics.totalUsage')}</div>,
      cell: ({ row }) => {
        const total = row.getValue('lifetime_used_traffic') as number | null

        return (
          <div className="flex items-center justify-start gap-2 whitespace-nowrap text-left">
            <span dir="ltr" className="text-xs">
              {formatBytes(total || 0)}
            </span>
          </div>
        )
      },
    },
    {
      id: 'role',
      header: () => <div className="flex items-center text-xs capitalize">{t('admins.role')}</div>,
      cell: ({ row }) => {
        const status = getAdminStatus(row.original)
        return (
          <div className="flex min-w-0 items-center gap-2">
            <AdminStatusBadge isSudo={isOwner(row.original)} status={status} label={status === 'active' ? roleLabel(row.original) : undefined} />
            {status !== 'active' && <span className="hidden truncate text-xs text-muted-foreground md:inline">{roleLabel(row.original)}</span>}
          </div>
        )
      },
    },
    {
      accessorKey: 'total_users',
      header: () => <div className="flex items-center text-xs capitalize">{t('admins.total.users')}</div>,
      cell: ({ row }) => (
        <div className="flex items-center gap-2">
          <Users className="h-4 w-4" />
          <span>{row.getValue('total_users') || 0}</span>
        </div>
      ),
    },
    {
      id: 'actions',
      cell: ({ row }) => {
        const isOwnerTarget = isOwner(row.original)
        const hasActions =
          !!onEdit ||
          !!onResetUsage ||
          (!isOwnerTarget && !!toggleStatus) ||
          (!isOwnerTarget && !!onDisableAllActiveUsers) ||
          (!isOwnerTarget && !!onActivateAllDisabledUsers) ||
          (!isOwnerTarget && !!onRemoveAllUsers) ||
          (!isOwnerTarget && row.original.username !== currentAdminUsername && !!onDelete)

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
                {onEdit && <DropdownMenuItem
                  onSelect={e => {
                    e.preventDefault()
                    e.stopPropagation()
                    onEdit(row.original)
                  }}
                >
                  <Pen className="mr-2 h-4 w-4" />
                  {t('edit')}
                </DropdownMenuItem>}
                {onResetUsage && <DropdownMenuItem
                  onSelect={e => {
                    e.preventDefault()
                    e.stopPropagation()
                    onResetUsage(row.original)
                  }}
                >
                  <RefreshCw className="mr-2 h-4 w-4" />
                  {t('admins.reset')}
                </DropdownMenuItem>}
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
                {!isOwnerTarget && row.original.username !== currentAdminUsername && onDelete && (
                  <>
                    <DropdownMenuSeparator />
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
