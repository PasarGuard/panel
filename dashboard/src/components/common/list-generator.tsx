import React, { useMemo, useState } from 'react'
import { useSortable } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { ChevronDown, GripVertical } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Skeleton } from '@/components/ui/skeleton'
import useDirDetection from '@/hooks/use-dir-detection'

export type ListColumnAlign = 'start' | 'center' | 'end'
export type ListLayoutMode = 'list' | 'grid'

export interface ListColumn<T> {
  id: string
  header: React.ReactNode
  cell: (item: T) => React.ReactNode
  width?: string
  className?: string
  headerClassName?: string
  skeletonClassName?: string
  align?: ListColumnAlign
  hideOnMobile?: boolean
}

interface ListGeneratorProps<T> {
  data: T[]
  columns: ListColumn<T>[]
  getRowId: (item: T) => string | number
  isLoading?: boolean
  loadingRows?: number
  emptyState?: React.ReactNode
  showEmptyState?: boolean
  className?: string
  headerClassName?: string
  rowClassName?: string | ((item: T, index: number) => string)
  hideHeader?: boolean
  onRowClick?: (item: T) => void
  mode?: ListLayoutMode
  gridClassName?: string
  gridStyle?: React.CSSProperties
  renderGridItem?: (item: T, index: number) => React.ReactNode
  renderGridSkeleton?: (index: number) => React.ReactNode
  enableSorting?: boolean
  sortingDisabled?: boolean
}

const getAlignClass = (align?: ListColumnAlign) => {
  switch (align) {
    case 'center':
      return 'justify-center'
    case 'end':
      return 'justify-end'
    default:
      return 'justify-start'
  }
}

export function ListGenerator<T>({
  data,
  columns,
  getRowId,
  isLoading = false,
  loadingRows = 6,
  emptyState,
  showEmptyState = true,
  className,
  headerClassName,
  rowClassName,
  hideHeader = false,
  onRowClick,
  mode = 'list',
  gridClassName,
  gridStyle,
  renderGridItem,
  renderGridSkeleton,
  enableSorting = false,
  sortingDisabled = false,
}: ListGeneratorProps<T>) {
  const templateColumns = useMemo(() => columns.map(column => column.width ?? 'minmax(0, 1fr)').join(' '), [columns])
  const [expandedRowId, setExpandedRowId] = useState<string | number | null>(null)

  const renderRowClassName = (item: T, index: number) => {
    if (typeof rowClassName === 'function') {
      return rowClassName(item, index)
    }
    return rowClassName
  }

  const hasData = data.length > 0
  const shouldShowEmptyState = showEmptyState && !isLoading && !hasData
  const showRows = !isLoading && hasData
  const mobileDetailsColumns = useMemo(() => columns.filter(column => column.hideOnMobile), [columns])
  const hasMobileDetails = mobileDetailsColumns.length > 0
  const listTemplateColumns = useMemo(() => (enableSorting ? `24px ${templateColumns}` : templateColumns), [enableSorting, templateColumns])
  const dir = useDirDetection()
  const gridContent = (showRows || isLoading) && renderGridItem

  if (mode === 'grid') {
    return (
      <div className={cn('flex w-full flex-col gap-2', className)}>
        {gridContent ? (
          <div className={cn('grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3', gridClassName)} style={gridStyle}>
            {isLoading &&
              Array.from({ length: loadingRows }).map((_, index) =>
                renderGridSkeleton ? (
                  <div key={`grid-skeleton-${index}`}>{renderGridSkeleton(index)}</div>
                ) : (
                  <div key={`grid-skeleton-${index}`} className="rounded-md border bg-background p-4">
                    <div className="space-y-2">
                      <Skeleton className="h-4 w-2/3" />
                      <Skeleton className="h-3 w-full" />
                      <Skeleton className="h-3 w-4/5" />
                    </div>
                  </div>
                ),
              )}
            {showRows && data.map((item, index) => <div key={getRowId(item)}>{renderGridItem(item, index)}</div>)}
          </div>
        ) : (
          <div className="rounded-md border bg-background px-3 py-6 text-center text-sm text-muted-foreground">
            Provide `renderGridItem` to render grid mode.
          </div>
        )}
        {shouldShowEmptyState && (emptyState ?? <div className="rounded-md border bg-background px-3 py-6 text-center text-sm text-muted-foreground">No results.</div>)}
      </div>
    )
  }

  return (
    <div className={cn('flex w-full flex-col gap-2', className)}>
      {!hideHeader && (
        <div
          className={cn('grid gap-3 px-3 text-xs font-semibold uppercase text-muted-foreground', headerClassName)}
          style={{ gridTemplateColumns: listTemplateColumns }}
        >
          {enableSorting && <div aria-hidden="true" />}
          {columns.map(column => (
            <div
              dir={dir}
              key={column.id}
              className={cn(
                'min-w-0 truncate',
                getAlignClass(column.align),
                column.hideOnMobile && 'hidden md:block',
                column.headerClassName,
              )}
            >
              {column.header}
            </div>
          ))}
        </div>
      )}

      {isLoading &&
        Array.from({ length: loadingRows }).map((_, rowIndex) => (
          <div
            key={`list-skeleton-${rowIndex}`}
            className="grid gap-3 rounded-md border bg-background px-3 py-3"
            style={{ gridTemplateColumns: listTemplateColumns }}
          >
            {enableSorting && <div aria-hidden="true" />}
            {columns.map(column => (
              <div
                key={`${column.id}-${rowIndex}`}
                className={cn(
                  'flex min-w-0 items-center',
                  getAlignClass(column.align),
                  column.hideOnMobile && 'hidden md:flex',
                  column.className,
                )}
              >
                <Skeleton className={cn('h-4 w-full', column.skeletonClassName)} />
              </div>
            ))}
          </div>
        ))}

      {showRows &&
        data.map((item, index) => {
          const rowId = getRowId(item)
          const isExpanded = hasMobileDetails && expandedRowId === rowId

          const RowContent = (props?: { attributes?: any; listeners?: any; style?: React.CSSProperties }) => (
            <div
              className={cn(
                'grid gap-3 overflow-hidden rounded-md border bg-background pl-3 py-3',
                dir === "rtl" && "pl-0 pr-3",
                hasMobileDetails && 'relative',
                onRowClick && 'cursor-pointer transition-colors hover:bg-muted/40',
                renderRowClassName(item, index),
              )}
              style={{ gridTemplateColumns: listTemplateColumns, ...props?.style }}
              onClick={() => onRowClick?.(item)}
              {...props?.attributes}
            >
              {enableSorting && (
                <button
                  type="button"
                  className={cn(
                    'flex items-center justify-center text-muted-foreground touch-none',
                    sortingDisabled ? 'cursor-not-allowed opacity-40' : 'cursor-grab z-50',
                  )}
                  onClick={event => event.stopPropagation()}
                  {...props?.listeners}
                  aria-label="Drag to reorder"
                >
                  <GripVertical className="h-5 w-5" />
                  <span className="sr-only">Drag to reorder</span>
                </button>
              )}
              {columns.map(column => (
                <div
                  key={`${column.id}-${rowId}`}
                  className={cn(
                    'flex min-w-0 items-center justify-end',
                    getAlignClass(column.align),
                    column.hideOnMobile && 'hidden md:flex',
                    column.className,
                  )}
                >
                  {column.cell(item)}
                </div>
              ))}
              {hasMobileDetails && (
                <button
                  type="button"
                  className={cn("chevron absolute right-2 top-6 flex -translate-y-1/2 items-center justify-center rounded-md p-1 text-muted-foreground md:hidden",
                  dir === "rtl" && "left-2 justify-end")}
                  onClick={event => {
                    event.stopPropagation()
                    setExpandedRowId(prev => (prev === rowId ? null : rowId))
                  }}
                  aria-label={isExpanded ? 'Collapse details' : 'Expand details'}
                >
                  <ChevronDown className={cn('h-4 w-4 transition-transform', isExpanded && 'rotate-180')} />
                </button>
              )}
              {hasMobileDetails && isExpanded && (
                <div className="col-span-full mt-2 px-0 pt-1 md:hidden">
                  <div className="flex items-center justify-between gap-4 px-3">
                    <div className="flex gap-3 items-center flex-wrap">
                      {mobileDetailsColumns
                        .filter(column => column.header)
                        .map(column => (
                          <div key={`mobile-${column.id}-${rowId}`} className="flex items-center gap-1">
                            <span className="text-xs text-muted-foreground">{column.header} :</span>
                            <div className="flex-1 text-sm">{column.cell(item)}</div>
                          </div>
                        ))}
                    </div>
                    <div className="flex shrink-0 items-start">
                      {mobileDetailsColumns
                        .filter(column => !column.header)
                        .map(column => (
                          <div key={`mobile-actions-${column.id}-${rowId}`} className="text-sm">
                            {column.cell(item)}
                          </div>
                        ))}
                    </div>
                  </div>
                </div>
              )}
            </div>
          )

          if (!enableSorting) {
            return <RowContent key={rowId} />
          }

          const SortableRow = () => {
            const { attributes, listeners, setNodeRef, transform, transition } = useSortable({
              id: rowId,
              disabled: sortingDisabled,
            })

            const style = {
              transform: CSS.Transform.toString(transform),
              transition,
            }

            return (
              <div ref={setNodeRef}>
                <RowContent attributes={attributes} listeners={listeners} style={style} />
              </div>
            )
          }

          return <SortableRow key={rowId} />
        })}

      {shouldShowEmptyState && (emptyState ?? <div className="rounded-md border bg-background px-3 py-6 text-center text-sm text-muted-foreground">No results.</div>)}
    </div>
  )
}
