import { ColumnDef, RowSelectionState, flexRender, getCoreRowModel, useReactTable } from '@tanstack/react-table'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { cn } from '@/lib/utils'
import useDirDetection from '@/hooks/use-dir-detection'
import React, { useState, useMemo, memo, useCallback, useEffect } from 'react'
import { ChartPie, ChevronDown, Edit2, Power, PowerOff, RefreshCw, Trash2, UserCheck, UserMinus, UserX, LoaderCircle, MoreVertical, Users } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { AdminDetails } from '@/service/api'
import { useTranslation } from 'react-i18next'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { formatBytes } from '@/utils/formatByte'

interface DataTableProps<TData extends AdminDetails> {
  columns: ColumnDef<TData, any>[]
  data: TData[]
  currentAdminUsername?: string
  onEdit: (admin: AdminDetails) => void
  onDelete: (admin: AdminDetails) => void
  onToggleStatus: (admin: AdminDetails) => void
  setStatusToggleDialogOpen: (isOpen: boolean) => void
  onResetUsage: (adminUsername: string) => void
  onDisableAllActiveUsers?: (adminUsername: string) => void
  onActivateAllDisabledUsers?: (adminUsername: string) => void
  onRemoveAllUsers?: (adminUsername: string) => void
  onSelectionChange?: (selectedUsernames: string[]) => void
  resetSelectionKey?: number
  isLoading?: boolean
  isFetching?: boolean
}

const ExpandedRowContent = memo(
  ({
    row,
    onEdit,
    onDelete,
    onToggleStatus,
    onResetUsage,
    onDisableAllActiveUsers,
    onActivateAllDisabledUsers,
    onRemoveAllUsers,
    currentAdminUsername,
  }: {
    row: AdminDetails
    onEdit: (admin: AdminDetails) => void
    onDelete: (admin: AdminDetails) => void
    onToggleStatus: (admin: AdminDetails) => void
    onResetUsage: (adminUsername: string) => void
    onDisableAllActiveUsers?: (adminUsername: string) => void
    onActivateAllDisabledUsers?: (adminUsername: string) => void
    onRemoveAllUsers?: (adminUsername: string) => void
    currentAdminUsername?: string
  }) => {
    const { t } = useTranslation()
    const isSudoTarget = row.is_sudo

    return (
      <div className="flex items-start justify-between gap-2 border-b px-3 py-3 text-xs">
        <div className="flex min-w-0 flex-col gap-1.5 text-[11px]">
          <div className="flex items-center gap-1.5 leading-none">
            <Users className="h-3 w-3 shrink-0 text-muted-foreground" />
            <span className="text-muted-foreground">{t('admins.total.users')}:</span>
            <span className="text-foreground">{row.total_users || 0}</span>
          </div>
          <div className="flex items-center gap-1.5 leading-none">
            <ChartPie className="h-3 w-3 shrink-0 text-muted-foreground" />
            <span className="text-muted-foreground">{t('statistics.totalUsage')}:</span>
            <span dir="ltr" className="text-foreground" style={{ unicodeBidi: 'isolate' }}>
              {formatBytes(row.lifetime_used_traffic || 0)}
            </span>
          </div>
        </div>
        <div className="flex justify-end gap-1">
          <Button type="button" variant="ghost" size="icon" className="h-8 w-8" onClick={() => onEdit(row)} title={t('edit')}>
            <Edit2 className="!h-3.5 !w-3.5" />
          </Button>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button type="button" variant="ghost" size="icon" className="h-8 w-8">
                <MoreVertical className="!h-3.5 !w-3.5" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              {!isSudoTarget && row.username !== currentAdminUsername && (
                <DropdownMenuItem
                  onSelect={e => {
                    e.preventDefault()
                    e.stopPropagation()
                    onToggleStatus(row)
                  }}
                >
                  {row.is_disabled ? <Power className="mr-2 h-4 w-4" /> : <PowerOff className="mr-2 h-4 w-4" />}
                  {row.is_disabled ? t('enable') : t('disable')}
                </DropdownMenuItem>
              )}
              <DropdownMenuItem
                onSelect={e => {
                  e.preventDefault()
                  e.stopPropagation()
                  onResetUsage(row.username)
                }}
              >
                <RefreshCw className="mr-2 h-4 w-4" />
                {t('admins.reset')}
              </DropdownMenuItem>
              {!isSudoTarget && onDisableAllActiveUsers && (
                <DropdownMenuItem
                  onSelect={e => {
                    e.preventDefault()
                    e.stopPropagation()
                    onDisableAllActiveUsers(row.username)
                  }}
                >
                  <UserMinus className="mr-2 h-4 w-4" />
                  {t('admins.disableAllActiveUsers')}
                </DropdownMenuItem>
              )}
              {!isSudoTarget && onActivateAllDisabledUsers && (
                <DropdownMenuItem
                  onSelect={e => {
                    e.preventDefault()
                    e.stopPropagation()
                    onActivateAllDisabledUsers(row.username)
                  }}
                >
                  <UserCheck className="mr-2 h-4 w-4" />
                  {t('admins.activateAllDisabledUsers')}
                </DropdownMenuItem>
              )}
              {!isSudoTarget && onRemoveAllUsers && (
                <DropdownMenuItem
                  className="text-destructive"
                  onSelect={e => {
                    e.preventDefault()
                    e.stopPropagation()
                    onRemoveAllUsers(row.username)
                  }}
                >
                  <UserX className="mr-2 h-4 w-4" />
                  {t('admins.removeAllUsers')}
                </DropdownMenuItem>
              )}
              {!isSudoTarget && row.username !== currentAdminUsername && (
                <>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem
                    className="text-destructive"
                    onSelect={e => {
                      e.preventDefault()
                      e.stopPropagation()
                      onDelete(row)
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
      </div>
    )
  },
)

export function DataTable<TData extends AdminDetails>({
  columns,
  data,
  currentAdminUsername,
  onEdit,
  onDelete,
  onToggleStatus,
  onResetUsage,
  onDisableAllActiveUsers,
  onActivateAllDisabledUsers,
  onRemoveAllUsers,
  onSelectionChange,
  resetSelectionKey = 0,
  isLoading = false,
  isFetching = false,
}: DataTableProps<TData>) {
  const [expandedRow, setExpandedRow] = useState<string | null>(null)
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({})
  const { t } = useTranslation()

  const handleRowSelectionChange = useCallback(
    (updater: RowSelectionState | ((old: RowSelectionState) => RowSelectionState)) => {
      setRowSelection(prev => {
        const next = typeof updater === 'function' ? updater(prev) : updater
        onSelectionChange?.(
          Object.entries(next)
            .filter(([, selected]) => selected)
            .map(([rowId]) => rowId),
        )
        return next
      })
    },
    [onSelectionChange],
  )

  const table = useReactTable({
    data,
    columns,
    getRowId: row => row.username,
    getCoreRowModel: getCoreRowModel(),
    enableRowSelection: row => !row.original.is_sudo && row.original.username !== currentAdminUsername,
    onRowSelectionChange: handleRowSelectionChange,
    state: {
      rowSelection,
    },
  })
  const dir = useDirDetection()
  const isRTL = dir === 'rtl'
  const isLoadingData = isLoading || isFetching

  const LoadingState = useMemo(
    () => (
      <TableRow>
        <TableCell colSpan={columns.length} className="h-24">
          <div dir={dir} className="flex flex-col items-center justify-center gap-2">
            <LoaderCircle className="h-8 w-8 animate-spin text-primary" />
            <span className="text-sm">{t('loading')}</span>
          </div>
        </TableCell>
      </TableRow>
    ),
    [columns.length, dir, t],
  )

  const EmptyState = useMemo(
    () => (
      <TableRow>
        <TableCell colSpan={columns.length} className="h-24 text-center">
          <span className="text-muted-foreground">{t('noResults')}</span>
        </TableCell>
      </TableRow>
    ),
    [columns.length, t],
  )

  useEffect(() => {
    setRowSelection({})
    onSelectionChange?.([])
  }, [onSelectionChange, resetSelectionKey])

  const handleRowToggle = useCallback((rowId: string) => {
    setExpandedRow(prev => (prev === rowId ? null : rowId))
  }, [])

  const handleEditModal = useCallback(
    (e: React.MouseEvent, rowData: AdminDetails) => {
      const isSmallScreen = window.innerWidth < 768
      const target = e.target as HTMLElement

      if (target.closest('.chevron')) return
      if (target.closest('[data-role="row-selector"]')) return
      if (target.closest('button')) return
      if (target.closest('[role="menu"], [role="menuitem"], [data-radix-popper-content-wrapper]')) return

      if (isSmallScreen) {
        handleRowToggle(rowData.username)
        return
      }

      onEdit(rowData)
    },
    [handleRowToggle, onEdit],
  )

  return (
    <div className="overflow-hidden rounded-md border">
      <Table dir={isRTL ? 'rtl' : 'ltr'}>
        <TableHeader>
          {table.getHeaderGroups().map(headerGroup => (
            <TableRow key={headerGroup.id} className="uppercase">
              {headerGroup.headers.map(header => (
                <TableHead
                  key={header.id}
                  className={cn(
                    'sticky z-10 bg-background text-xs',
                    isRTL && 'text-right',
                    header.id === 'select' && 'w-8 !px-1 py-1.5',
                    header.id === 'username' && 'w-auto md:w-auto',
                    header.id === 'total_users' && '!px-0',
                    header.id === 'used_traffic' && 'w-[72px] !px-0 text-center md:w-auto md:px-2 md:text-left',
                    header.id === 'lifetime_used_traffic' && 'w-[44px] !px-0 text-center md:w-auto md:px-2 md:text-left',
                    !['select', 'username', 'used_traffic', 'lifetime_used_traffic', 'chevron'].includes(header.id) && 'hidden md:table-cell',
                    header.id === 'chevron' && 'w-4 !p-0 table-cell md:hidden',
                  )}
                >
                  {header.isPlaceholder ? null : flexRender(header.column.columnDef.header, header.getContext())}
                </TableHead>
              ))}
            </TableRow>
          ))}
        </TableHeader>
        <TableBody>
          {isLoadingData
            ? LoadingState
            : table.getRowModel().rows?.length
              ? table.getRowModel().rows.map(row => {
                const isRowSelected = row.getIsSelected()

                return (
                  <React.Fragment key={row.id}>
                    <TableRow className={cn('cursor-pointer border-b md:cursor-default', expandedRow === row.id && 'border-transparent')} onClick={e => handleEditModal(e, row.original)} data-state={isRowSelected ? 'selected' : undefined}>
                      {row.getVisibleCells().map(cell => (
                        <TableCell
                          key={cell.id}
                          data-role={cell.column.id === 'select' ? 'row-selector' : undefined}
                          className={cn(
                            'text-sm',
                            cell.column.id !== 'username' && 'whitespace-nowrap',
                            cell.column.id === 'select' && 'w-8 !px-1 !py-4',
                            cell.column.id === 'username' && 'max-w-[calc(100vw-32px-72px-44px-16px-56px)] !px-0',
                            cell.column.id === 'used_traffic' && '!px-0 text-center',
                            cell.column.id === 'lifetime_used_traffic' && '!px-0 text-center',
                            cell.column.id === 'chevron' && 'w-10',
                            !['select', 'username', 'used_traffic', 'lifetime_used_traffic', 'chevron'].includes(cell.column.id) && 'hidden !p-0 md:table-cell',
                            cell.column.id === 'chevron' && 'table-cell md:hidden',
                            !['select', 'username', 'used_traffic', 'lifetime_used_traffic', 'chevron'].includes(cell.column.id) && (isRTL ? 'pl-1.5 sm:pl-3' : 'pr-1.5 sm:pr-3'),
                          )}
                        >
                          {cell.column.id === 'chevron' ? (
                            <div
                              className="chevron flex cursor-pointer items-center justify-center"
                              onClick={e => {
                                e.stopPropagation()
                                handleRowToggle(row.id)
                              }}
                            >
                              <ChevronDown className={cn('h-3.5 w-3.5', expandedRow === row.id && 'rotate-180')} />
                            </div>
                          ) : (
                            flexRender(cell.column.columnDef.cell, cell.getContext())
                          )}
                        </TableCell>
                      ))}
                    </TableRow>
                    {expandedRow === row.id && (
                      <TableRow className="border-b border-transparent md:hidden" data-state={isRowSelected ? 'selected' : undefined}>
                        <TableCell colSpan={columns.length} className="p-0 text-sm">
                          <ExpandedRowContent
                            row={row.original}
                            onEdit={onEdit}
                            onDelete={onDelete}
                            onToggleStatus={onToggleStatus}
                            onResetUsage={onResetUsage}
                            onDisableAllActiveUsers={onDisableAllActiveUsers}
                            onActivateAllDisabledUsers={onActivateAllDisabledUsers}
                            onRemoveAllUsers={onRemoveAllUsers}
                            currentAdminUsername={currentAdminUsername}
                          />
                        </TableCell>
                      </TableRow>
                    )}
                  </React.Fragment>
                )
              })
              : EmptyState}
        </TableBody>
      </Table>
    </div>
  )
}
