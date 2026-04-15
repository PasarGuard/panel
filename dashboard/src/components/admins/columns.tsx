import { AdminDetails } from '@/service/api'
import { ColumnDef, Row, Table } from '@tanstack/react-table'
import { ChartPie, ChevronDown, MoreVertical, Pen, Power, PowerOff, RefreshCw, UserRoundKey, Trash2, Users, UserCheck, UserMinus, UserRound, UserX } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { formatBytes } from '@/utils/formatByte.ts'
import { AdminStatusBadge } from './admin-status-badge'
import { Checkbox } from '@/components/ui/checkbox'
import { cn } from '@/lib/utils'

interface ColumnSetupProps {
  t: (key: string) => string
  handleSort: (column: string) => void
  filters: { sort?: string }
  currentAdminUsername?: string
  onEdit: (admin: AdminDetails) => void
  onDelete: (admin: AdminDetails) => void
  toggleStatus: (admin: AdminDetails) => void
  onResetUsage: (adminUsername: string) => void
  onDisableAllActiveUsers: (adminUsername: string) => void
  onActivateAllDisabledUsers: (adminUsername: string) => void
  onRemoveAllUsers: (adminUsername: string) => void
}

const createSortButton = (
  column: string,
  label: string,
  t: (key: string) => string,
  handleSort: (column: string) => void,
  filters: {
    sort?: string
  },
) => {
  const handleClick = (e: React.MouseEvent) => {
    e.preventDefault()
    e.stopPropagation()
    handleSort(column)
  }

  return (
    <button type="button" onClick={handleClick} className="flex w-full items-center gap-1">
      <div className="text-xs">{t(label)}</div>
      {filters.sort && (filters.sort === column || filters.sort === '-' + column) && (
        <ChevronDown size={16} className={`transition-transform duration-300 ${filters.sort === column ? 'rotate-180' : ''} ${filters.sort === '-' + column ? 'rotate-0' : ''} `} />
      )}
    </button>
  )
}

const getAdminRoleIcon = (isSudo: boolean) => (isSudo ? UserRoundKey : UserRound)

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
      cell: ({ row }) => (
        <div className="overflow-hidden text-ellipsis whitespace-nowrap py-1.5 font-medium">
          <div className="flex items-center gap-x-3">
            <div>
              {row.original.is_disabled ? (
                <div className="min-h-[10px] min-w-[10px] rounded-full border border-gray-400 shadow-sm dark:border-gray-600" />
              ) : (
                <div className="min-h-[10px] min-w-[10px] rounded-full bg-green-500 shadow-sm" />
              )}
            </div>
            <div className="flex flex-col overflow-hidden text-ellipsis whitespace-nowrap">
              <span className="overflow-hidden text-ellipsis whitespace-nowrap text-sm font-medium">{row.getValue('username')}</span>
            </div>
          </div>
        </div>
      ),
    },
    {
      accessorKey: 'used_traffic',
      header: () => createSortButton('used_traffic', 'admins.used.traffic', t, handleSort, filters),
      cell: ({ row }) => {
        const traffic = row.getValue('used_traffic') as number | null
        return (
          <div className="flex items-center gap-2 whitespace-nowrap">
            <ChartPie className="hidden h-4 w-4 sm:block" />
            <span dir="ltr" className="text-xs">
              {traffic ? formatBytes(traffic) : '0 B'}
            </span>
          </div>
        )
      },
    },
    {
      accessorKey: 'lifetime_used_traffic',
      header: () => (
        <div className="flex items-center text-xs capitalize">
          <span className="md:hidden">{t('admins.role')}</span>
          <span className="hidden md:inline">{t('statistics.totalUsage')}</span>
        </div>
      ),
      cell: ({ row }) => {
        const total = row.getValue('lifetime_used_traffic') as number | null
        const RoleIcon = getAdminRoleIcon(!!row.original.is_sudo)

        return (
          <div className="flex items-center justify-start gap-0 whitespace-nowrap md:justify-start md:gap-2">
            <span dir="ltr" className="hidden text-xs md:inline">
              {formatBytes(total || 0)}
            </span>
            <RoleIcon className={row.original.is_disabled ? 'h-4 w-4 text-muted-foreground/60 md:hidden' : cn('h-4 w-4 md:hidden', row.original.is_sudo ? 'text-violet-500' : 'text-primary')} />
          </div>
        )
      },
    },
    {
      accessorKey: 'is_sudo',
      header: () => <div className="flex items-center text-xs capitalize">{t('admins.role')}</div>,
      cell: ({ row }) => {
        const isSudo = row.getValue('is_sudo')
        const isDisabled = row.original.is_disabled
        return (
          <div className="flex items-center gap-2">
            <AdminStatusBadge isSudo={!!isSudo} isDisabled={!!isDisabled} />
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
        const isSudoTarget = row.original.is_sudo

        return (
          <div className="flex items-center justify-center gap-2">
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button type="button" variant="ghost" size="icon">
                  <MoreVertical className="h-4 w-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
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
                <DropdownMenuItem
                  onSelect={e => {
                    e.preventDefault()
                    e.stopPropagation()
                    onResetUsage(row.original.username)
                  }}
                >
                  <RefreshCw className="mr-2 h-4 w-4" />
                  {t('admins.reset')}
                </DropdownMenuItem>
                {!isSudoTarget && (
                  <DropdownMenuItem
                    onSelect={e => {
                      e.preventDefault()
                      e.stopPropagation()
                      toggleStatus(row.original)
                    }}
                  >
                    {row.original.is_disabled ? <Power className="mr-2 h-4 w-4" /> : <PowerOff className="mr-2 h-4 w-4" />}
                    {row.original.is_disabled ? t('enable') : t('disable')}
                  </DropdownMenuItem>
                )}
                {!isSudoTarget && (
                  <DropdownMenuItem
                    onSelect={e => {
                      e.preventDefault()
                      e.stopPropagation()
                      onDisableAllActiveUsers(row.original.username)
                    }}
                  >
                    <UserMinus className="mr-2 h-4 w-4" />
                    {t('admins.disableAllActiveUsers')}
                  </DropdownMenuItem>
                )}
                {!isSudoTarget && (
                  <DropdownMenuItem
                    onSelect={e => {
                      e.preventDefault()
                      e.stopPropagation()
                      onActivateAllDisabledUsers(row.original.username)
                    }}
                  >
                    <UserCheck className="mr-2 h-4 w-4" />
                    {t('admins.activateAllDisabledUsers')}
                  </DropdownMenuItem>
                )}
                {!isSudoTarget && (
                  <DropdownMenuItem
                    className="text-destructive"
                    onSelect={e => {
                      e.preventDefault()
                      e.stopPropagation()
                      onRemoveAllUsers(row.original.username)
                    }}
                  >
                    <UserX className="mr-2 h-4 w-4" />
                    {t('admins.removeAllUsers')}
                  </DropdownMenuItem>
                )}
                {!isSudoTarget && row.original.username !== currentAdminUsername && (
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
