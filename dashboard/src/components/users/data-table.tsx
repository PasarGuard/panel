import { ColumnDef, RowSelectionState, flexRender, getCoreRowModel, useReactTable } from '@tanstack/react-table'
import React, { useState, useCallback, useMemo, memo, useEffect } from 'react'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import useDirDetection from '@/hooks/use-dir-detection'
import { cn } from '@/lib/utils'
import { UserResponse } from '@/service/api'
import { ChevronDown, LoaderCircle, Rss } from 'lucide-react'
import ActionButtons from './action-buttons'
import { OnlineStatus } from './online-status'
import { StatusBadge } from './status-badge'
import UsageSliderCompact from './usage-slider-compact'
import { useTranslation } from 'react-i18next'

interface DataTableProps<TData extends UserResponse, TValue> {
  columns: ColumnDef<TData, TValue>[]
  data: TData[]
  isLoading?: boolean
  isFetching?: boolean
  onEdit?: (user: UserResponse) => void
  onSelectionChange?: (selectedIds: number[]) => void
  resetSelectionKey?: number
}

const ExpandedRowContent = memo(({ row }: { row: { original: UserResponse } }) => (
  <div className="flex flex-col gap-y-4 p-4 border-b">
    <UsageSliderCompact isMobile status={row.original.status} total={row.original.data_limit} totalUsedTraffic={row.original.lifetime_used_traffic} used={row.original.used_traffic} />
    <div className="flex flex-col gap-y-2">
      <div className="flex items-center justify-end">
        <div onClick={e => e.stopPropagation()}>
          <ActionButtons user={row.original} isModalHost={false} />
        </div>
      </div>
      <div className="flex flex-col gap-1.5">
        {row.original.expire && <StatusBadge showOnlyExpiry expiryDate={row.original.expire} status={row.original.status} showExpiry />}
        <div className="flex items-center gap-x-1">
          <span className="flex items-center gap-x-0.5">
            <Rss className="h-3 w-3 text-muted-foreground" />
            <span className="text-muted-foreground">:</span>
          </span>
          <OnlineStatus lastOnline={row.original.online_at} />
        </div>
      </div>
    </div>
  </div>
))

export const DataTable = memo(<TData extends UserResponse, TValue>({ columns, data, isLoading = false, onEdit, onSelectionChange, resetSelectionKey = 0 }: DataTableProps<TData, TValue>) => {
  const { t } = useTranslation()
  const [expandedRow, setExpandedRow] = useState<number | null>(null)
  /** CSS :hover can stick after closing portaled menus; drive md+ row bg with pointer events instead. */
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({})
  const dir = useDirDetection()
  const isRTL = dir === 'rtl'
  const hasSelectionColumn = useMemo(() => columns.some(column => column.id === 'select'), [columns])

  const handleRowSelectionChange = useCallback(
    (updater: RowSelectionState | ((old: RowSelectionState) => RowSelectionState)) => {
      setRowSelection(prev => {
        const next = typeof updater === 'function' ? updater(prev) : updater
        onSelectionChange?.(
          Object.entries(next)
            .filter(([, selected]) => selected)
            .map(([rowId]) => Number(rowId)),
        )
        return next
      })
    },
    [onSelectionChange],
  )

  // Memoize table configuration to prevent unnecessary re-renders
  const tableConfig = useMemo(
    () => ({
      data,
      columns,
      getRowId: (row: TData) => String(row.id),
      getCoreRowModel: getCoreRowModel(),
      enableRowSelection: hasSelectionColumn,
      onRowSelectionChange: handleRowSelectionChange,
      state: {
        rowSelection,
      },
    }),
    [columns, data, handleRowSelectionChange, hasSelectionColumn, rowSelection],
  )

  const table = useReactTable(tableConfig)

  useEffect(() => {
    setRowSelection({})
    onSelectionChange?.([])
  }, [resetSelectionKey])

  const handleRowToggle = useCallback((rowId: number) => {
    setExpandedRow(prev => (prev === rowId ? null : rowId))
  }, [])

  const handleEditModal = useCallback(
    (e: React.MouseEvent, user: UserResponse) => {
      if ((e.target as HTMLElement).closest('.chevron')) return
      if ((e.target as HTMLElement).closest('[data-role="row-selector"]')) return
      if (window.innerWidth < 768) {
        handleRowToggle(user.id)
        return
      }
      if ((e.target as HTMLElement).closest('[role="menu"], [role="menuitem"], [data-radix-popper-content-wrapper]')) return
      onEdit?.(user)
    },
    [handleRowToggle, onEdit],
  )

  // Keep rows mounted during background fetching so row-level dialogs remain stable.
  const isLoadingData = isLoading

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

  return (
    <div className="overflow-hidden rounded-md border">
      <Table dir={isRTL ? 'rtl' : 'ltr'}>
        <TableHeader>
          {table.getHeaderGroups().map(headerGroup => (
            <TableRow key={headerGroup.id} className="uppercase">
              {headerGroup.headers.map((header) => (
                <TableHead
                  key={header.id}
                  className={cn(
                    'sticky z-10 bg-background text-xs',
                    isRTL && 'text-right',
                    header.id === 'select' && 'w-8 !px-1 py-1.5',
                    header.id === 'username' && 'w-auto md:w-auto',
                    header.id === 'status' && 'max-w-[70px] !px-0 md:w-auto',
                    header.id === 'details' && 'px-1 md:w-[440px]',
                    !['select', 'username', 'status', 'details', 'chevron'].includes(header.id) && 'hidden md:table-cell',
                    header.id === 'chevron' && 'table-cell md:hidden',
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
                    <TableRow
                      className={cn(
                        'cursor-pointer border-b md:cursor-default',

                        expandedRow === row.original.id && 'border-transparent',
                      )}
                      onClick={e => handleEditModal(e, row.original)}
                      data-state={isRowSelected ? 'selected' : undefined}
                    >
                      {row.getVisibleCells().map((cell) => (
                        <TableCell
                          key={cell.id}
                          data-role={cell.column.id === 'select' ? 'row-selector' : undefined}
                          className={cn(
                            'text-sm',
                            cell.column.id !== 'details' && 'whitespace-nowrap',
                            cell.column.id === 'details' && 'md:whitespace-nowrap',
                            cell.column.id !== 'details' && 'py-1.5',
                            cell.column.id === 'username' && cn('max-w-[calc(100vw-50px-32px-100px-60px)]', hasSelectionColumn && '!px-0'),
                            cell.column.id === "status" && '!px-0',
                            cell.column.id === 'select' && 'w-8 !px-1 !py-5',
                            cell.column.id === 'chevron' && 'w-4 !p-0',
                            !['select', 'username', 'status', 'details', 'chevron'].includes(cell.column.id) && 'hidden !p-0 md:table-cell',
                            cell.column.id === 'chevron' && 'table-cell md:hidden',
                            !['details', 'select', 'chevron'].includes(cell.column.id) && (isRTL ? 'pl-1.5 sm:pl-3' : 'pr-1.5 sm:pr-3'),
                          )}
                        >
                          {cell.column.id === 'chevron' ? (
                            <div
                              className="chevron flex cursor-pointer items-center justify-center"
                              onClick={e => {
                                e.stopPropagation()
                                handleRowToggle(row.original.id)
                              }}
                            >
                              <ChevronDown className={cn('h-3.5 w-3.5', expandedRow === row.original.id && 'rotate-180')} />
                            </div>
                          ) : (
                            flexRender(cell.column.columnDef.cell, cell.getContext())
                          )}
                        </TableCell>
                      ))}
                    </TableRow>
                    {expandedRow === row.original.id && (
                      <TableRow className={cn('border-b md:hidden', 'border-transparent')} data-state={isRowSelected ? 'selected' : undefined}>
                        <TableCell colSpan={columns.length} className={cn('p-0 text-sm',)}>
                          <ExpandedRowContent row={row} />
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
})
