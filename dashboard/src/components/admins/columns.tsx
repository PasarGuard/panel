import { AdminDetails } from '@/service/api'
import { ColumnDef } from '@tanstack/react-table'
import { ChartPie, ChevronDown, MoreVertical, Pen, Power, PowerOff, RefreshCw, Trash2, User, UserCheck, UserMinus, UserX } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from '@/components/ui/dropdown-menu.tsx'
import { formatBytes } from '@/utils/formatByte.ts'
import { AdminStatusBadge } from './admin-status-badge'

interface ColumnSetupProps {
  t: (key: string) => string
  handleSort: (column: string) => void
  filters: { sort?: string }
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
    <button onClick={handleClick} className="flex w-full items-center gap-1">
      <div className="text-xs">{t(label)}</div>
      {filters.sort && (filters.sort === column || filters.sort === '-' + column) && (
        <ChevronDown size={16} className={`transition-transform duration-300 ${filters.sort === column ? 'rotate-180' : ''} ${filters.sort === '-' + column ? 'rotate-0' : ''} `} />
      )}
    </button>
  )
}

export const setupColumns = ({
  t,
  handleSort,
  filters,
  onEdit,
  onDelete,
  toggleStatus,
  onResetUsage,
  onDisableAllActiveUsers,
  onActivateAllDisabledUsers,
  onRemoveAllUsers,
}: ColumnSetupProps): ColumnDef<AdminDetails>[] => [
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
    header: () => <div className="flex items-center text-xs capitalize">{t('admins.lifetime.used.traffic')}</div>,
    cell: ({ row }) => {
      const total = row.getValue('lifetime_used_traffic') as number | null
      return (
        <div className="flex items-center gap-2 whitespace-nowrap">
          <span dir="ltr" className="text-xs">
            {formatBytes(total || 0)}
          </span>
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
        <User className="h-4 w-4" />
        <span>{row.getValue('total_users') || 0}</span>
      </div>
    ),
  },
  {
    id: 'actions',
    cell: ({ row }) => (
      <div className="flex items-center justify-end gap-2">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon">
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
            <DropdownMenuSeparator />
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
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    ),
  },
  {
    id: 'chevron',
    cell: () => <div className="flex flex-wrap justify-between"></div>,
  },
]
