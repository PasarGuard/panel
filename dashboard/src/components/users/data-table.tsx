import { ColumnDef, flexRender, getCoreRowModel, useReactTable } from '@tanstack/react-table'
import React, { useState, useCallback, useMemo, memo } from 'react'
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
}

export const DataTable = memo(<TData extends UserResponse, TValue>({ columns, data, isLoading = false, isFetching = false, onEdit }: DataTableProps<TData, TValue>) => {
  const { t } = useTranslation()
  const [expandedRow, setExpandedRow] = useState<number | null>(null)
  const dir = useDirDetection()
  const isRTL = dir === 'rtl'

  // Memoize table configuration to prevent unnecessary re-renders
  const tableConfig = useMemo(
    () => ({
      data,
      columns,
      getCoreRowModel: getCoreRowModel(),
    }),
    [data, columns],
  )

  const table = useReactTable(tableConfig)

  const handleRowToggle = useCallback((rowId: number) => {
    setExpandedRow(prev => (prev === rowId ? null : rowId))
  }, [])

  const handleEditModal = useCallback(
    (e: React.MouseEvent, user: UserResponse) => {
      if ((e.target as HTMLElement).closest('.chevron')) return
      if (window.innerWidth < 768) {
        handleRowToggle(user.id)
        return
      }
      if ((e.target as HTMLElement).closest('[role="menu"], [role="menuitem"], [data-radix-popper-content-wrapper]')) return
      onEdit?.(user)
    },
    [handleRowToggle, onEdit],
  )

  const isLoadingData = isLoading || isFetching

  const ExpandedRowContent = memo(({ row }: { row: any }) => (
    <div className="flex flex-col gap-y-4 p-4">
      <UsageSliderCompact isMobile status={row.original.status} total={row.original.data_limit} totalUsedTraffic={row.original.lifetime_used_traffic} used={row.original.used_traffic} />
      <div className="flex flex-col gap-y-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center">
            <StatusBadge showOnlyExpiry expiryDate={row.original.expire} status={row.original.status} showExpiry />
          </div>
          <div onClick={e => e.stopPropagation()}>
            <ActionButtons user={row.original} />
          </div>
        </div>
        <div className="flex items-center gap-x-1">
          <span className="flex items-center gap-x-0.5">
            <Rss className="h-3 w-3 text-muted-foreground" />
            <span className="text-muted-foreground">:</span>
          </span>
          <OnlineStatus lastOnline={row.original.online_at} />
        </div>
      </div>
    </div>
  ))

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
              {headerGroup.headers.map((header, index) => (
                <TableHead
                  key={header.id}
                  className={cn(
                    'sticky z-10 bg-background text-xs',
                    isRTL && 'text-right',
                    index === 0 && 'w-[200px] sm:w-[270px] md:w-auto',
                    index === 1 && 'max-w-[70px] !px-0 md:w-auto',
                    index === 2 && 'min-w-[100px] px-1 md:w-[450px]',
                    index >= 3 && 'hidden md:table-cell',
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
              ? table.getRowModel().rows.map(row => (
                  <React.Fragment key={row.id}>
                    <TableRow
                      className={cn('cursor-pointer border-b hover:!bg-inherit md:cursor-default md:hover:!bg-muted/50', expandedRow === row.original.id && 'border-transparent')}
                      onClick={e => handleEditModal(e, row.original)}
                      data-state={row.getIsSelected() && 'selected'}
                    >
                      {row.getVisibleCells().map((cell, index) => (
                        <TableCell
                          key={cell.id}
                          className={cn(
                            'text-sm',
                            index !== 2 && 'whitespace-nowrap',
                            index === 2 && 'md:whitespace-nowrap',
                            index !== 2 && 'py-1.5',
                            index <= 1 && 'max-w-[calc(100vw-50px-32px-100px-60px)] md:py-2',
                            index === 2 && 'min-w-[100px] max-w-full md:w-[450px]',
                            index === 3 && 'w-8',
                            index === 3 && '!p-0',
                            index >= 4 && 'hidden !p-0 md:table-cell',
                            cell.column.id === 'chevron' && 'table-cell md:hidden',
                            index !== 2 && (isRTL ? 'pl-1.5 sm:pl-3' : 'pr-1.5 sm:pr-3'),
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
                              <ChevronDown className={cn('h-4 w-4', expandedRow === row.original.id && 'rotate-180')} />
                            </div>
                          ) : (
                            flexRender(cell.column.columnDef.cell, cell.getContext())
                          )}
                        </TableCell>
                      ))}
                    </TableRow>
                    {expandedRow === row.original.id && (
                      <TableRow className="border-b hover:!bg-inherit md:hidden">
                        <TableCell colSpan={columns.length} className="p-0 text-sm">
                          <ExpandedRowContent row={row} />
                        </TableCell>
                      </TableRow>
                    )}
                  </React.Fragment>
                ))
              : EmptyState}
        </TableBody>
      </Table>
    </div>
  )
})
