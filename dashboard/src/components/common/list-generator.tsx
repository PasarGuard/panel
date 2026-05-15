import React, { useMemo, useState } from 'react'
import { useSortable } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { ChevronDown, GripVertical } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Skeleton } from '@/components/ui/skeleton'
import { Checkbox } from '@/components/ui/checkbox'
import useDirDetection from '@/hooks/use-dir-detection'
import { useTranslation } from 'react-i18next'

export type ListColumnAlign = 'start' | 'center' | 'end'

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
  enableSorting?: boolean
  /** When true with {@link enableSorting}, rows snap to new positions with no reorder transition animation. */
  instantSortReorder?: boolean
  sortingDisabled?: boolean
  enableSelection?: boolean
  selectedRowIds?: Array<string | number>
  onSelectionChange?: (ids: Array<string | number>) => void
  isRowSelectable?: (item: T) => boolean
}

interface SortableListRowProps {
  rowId: string | number
  sortingDisabled: boolean
  instantSortReorder?: boolean
  renderRow: (props: { attributes: ReturnType<typeof useSortable>['attributes']; listeners: ReturnType<typeof useSortable>['listeners']; style: React.CSSProperties }) => React.ReactNode
}

function SortableListRow({ rowId, sortingDisabled, instantSortReorder = false, renderRow }: SortableListRowProps) {
  const { attributes, listeners, setNodeRef, transform, transition } = useSortable({
    id: rowId,
    disabled: sortingDisabled,
    ...(instantSortReorder ? { animateLayoutChanges: () => false, transition: null } : {}),
  })

  const style = {
    transform: CSS.Transform.toString(transform),
    ...(instantSortReorder ? {} : { transition }),
  }

  return <div ref={setNodeRef}>{renderRow({ attributes, listeners, style })}</div>
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
  enableSorting = false,
  instantSortReorder = false,
  sortingDisabled = false,
  enableSelection = false,
  selectedRowIds = [],
  onSelectionChange,
  isRowSelectable,
}: ListGeneratorProps<T>) {
  const { t } = useTranslation()
  const templateColumns = useMemo(() => columns.map(column => column.width ?? 'minmax(0, 1fr)').join(' '), [columns])
  const [expandedRowId, setExpandedRowId] = useState<string | number | null>(null)
  const selectedRowSet = useMemo(() => new Set(selectedRowIds), [selectedRowIds])
  const visibleSelectableRowIds = useMemo(
    () => (enableSelection ? data.filter(item => (isRowSelectable ? isRowSelectable(item) : true)).map(item => getRowId(item)) : []),
    [data, enableSelection, getRowId, isRowSelectable],
  )

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
  const mobileDetailDataColumns = useMemo(() => mobileDetailsColumns.filter(column => !!column.header), [mobileDetailsColumns])
  const mobileDetailActionColumns = useMemo(() => mobileDetailsColumns.filter(column => !column.header), [mobileDetailsColumns])
  const hasMobileExpandableDetails = mobileDetailDataColumns.length > 0
  const hasMobileTrailingWidth = mobileDetailsColumns.length > 0
  const isAllVisibleSelected = visibleSelectableRowIds.length > 0 && visibleSelectableRowIds.every(id => selectedRowSet.has(id))
  const isSomeVisibleSelected = !isAllVisibleSelected && visibleSelectableRowIds.some(id => selectedRowSet.has(id))
  const mobileTemplateColumns = useMemo(() => {
    const visibleColumns = columns.filter(column => !column.hideOnMobile).map(column => column.width ?? 'minmax(0, 1fr)')

    if (hasMobileTrailingWidth) {
      visibleColumns.push(mobileDetailActionColumns.length > 0 ? 'max-content' : '32px')
    }

    return visibleColumns.join(' ')
  }, [columns, hasMobileTrailingWidth, mobileDetailActionColumns.length])
  const listTemplateColumnsDesktop = useMemo(
    () => [enableSorting ? '24px' : null, enableSelection ? '28px' : null, templateColumns].filter(Boolean).join(' '),
    [enableSelection, enableSorting, templateColumns],
  )
  const listTemplateColumnsMobile = useMemo(
    () => [enableSorting ? '24px' : null, enableSelection ? '28px' : null, mobileTemplateColumns].filter(Boolean).join(' '),
    [enableSelection, enableSorting, mobileTemplateColumns],
  )
  const listTemplateStyleVars = useMemo(
    () =>
      ({
        '--list-cols-mobile': listTemplateColumnsMobile,
        '--list-cols-desktop': listTemplateColumnsDesktop,
      }) as React.CSSProperties,
    [listTemplateColumnsMobile, listTemplateColumnsDesktop],
  )
  const listTemplateClassName =
    'grid items-center [grid-template-columns:var(--list-cols-mobile)] md:[grid-template-columns:var(--list-cols-desktop)]'
  const dir = useDirDetection()
  const headerSelectionCheckboxClassName = 'h-3.5 w-3.5 rounded-[3px] border-muted-foreground/40 data-[state=checked]:border-primary'
  const selectionCheckboxClassName =
    'h-3.5 w-3.5 rounded-[3px] border-muted-foreground/40 bg-background data-[state=checked]:border-primary data-[state=checked]:bg-primary data-[state=checked]:text-primary-foreground data-[state=indeterminate]:border-primary data-[state=indeterminate]:bg-primary data-[state=indeterminate]:text-primary-foreground'
  const stopSelectionClick = (event: React.SyntheticEvent) => {
    event.stopPropagation()
  }
  const stopSelectionPointer = (event: React.SyntheticEvent) => {
    event.preventDefault()
    event.stopPropagation()
  }

  const handleToggleRowSelection = (rowId: string | number, item: T) => {
    if (!enableSelection || !onSelectionChange || (isRowSelectable && !isRowSelectable(item))) {
      return
    }

    if (selectedRowSet.has(rowId)) {
      onSelectionChange(selectedRowIds.filter(selectedId => selectedId !== rowId))
      return
    }

    onSelectionChange([...selectedRowIds, rowId])
  }

  const handleToggleAllVisibleSelection = (checked: boolean) => {
    if (!enableSelection || !onSelectionChange) {
      return
    }

    if (!checked) {
      const visibleSelectedSet = new Set(visibleSelectableRowIds)
      onSelectionChange(selectedRowIds.filter(selectedId => !visibleSelectedSet.has(selectedId)))
      return
    }

    const nextSelectedRowIds = [...selectedRowIds]
    for (const rowId of visibleSelectableRowIds) {
      if (!selectedRowSet.has(rowId)) {
        nextSelectedRowIds.push(rowId)
      }
    }
    onSelectionChange(nextSelectedRowIds)
  }

  return (
    <div className={cn('flex w-full flex-col gap-2', className)}>
      {!hideHeader && (
        <div className={cn(listTemplateClassName, 'text-muted-foreground gap-3 px-3 text-xs font-semibold uppercase', headerClassName)} style={listTemplateStyleVars}>
          {enableSorting && <div aria-hidden="true" />}
          {enableSelection && (
            <div className="flex items-center justify-center">
              <Checkbox
                aria-label={t('selectAll', { defaultValue: 'Select all' })}
                className={headerSelectionCheckboxClassName}
                checked={isAllVisibleSelected || (isSomeVisibleSelected && 'indeterminate')}
                onCheckedChange={value => handleToggleAllVisibleSelection(!!value)}
                onClick={stopSelectionClick}
                onMouseDown={stopSelectionPointer}
                onPointerDown={stopSelectionPointer}
                onKeyDown={stopSelectionClick}
              />
            </div>
          )}
          {columns.map(column => (
            <div dir={dir} key={column.id} className={cn('min-w-0 truncate', getAlignClass(column.align), column.hideOnMobile && 'hidden md:block', column.headerClassName)}>
              {column.header}
            </div>
          ))}
        </div>
      )}

      {isLoading &&
        Array.from({ length: loadingRows }).map((_, rowIndex) => (
          <div key={`list-skeleton-${rowIndex}`} className={cn(listTemplateClassName, 'bg-background gap-3 rounded-md border px-3 py-3')} style={listTemplateStyleVars}>
            {enableSorting && (
              <div className="flex items-center justify-center">
                <Skeleton className="size-5 shrink-0 rounded-md" aria-hidden />
              </div>
            )}
            {enableSelection && (
              <div className="flex items-center justify-center">
                <Skeleton className="h-3.5 w-3.5 shrink-0 rounded-[3px]" aria-hidden />
              </div>
            )}
            {columns.map(column => (
              <div key={`${column.id}-${rowIndex}`} className={cn('flex min-w-0 items-center', getAlignClass(column.align), column.hideOnMobile && 'hidden md:flex', column.className)}>
                <Skeleton className={cn('h-4 w-full', column.skeletonClassName)} />
              </div>
            ))}
          </div>
        ))}

      {showRows &&
        data.map((item, index) => {
          const rowId = getRowId(item)
          const isExpanded = hasMobileExpandableDetails && expandedRowId === rowId
          const canSelectRow = enableSelection && (isRowSelectable ? isRowSelectable(item) : true)
          const isSelected = selectedRowSet.has(rowId)

          const renderRowContent = (props?: { attributes?: ReturnType<typeof useSortable>['attributes']; listeners?: ReturnType<typeof useSortable>['listeners']; style?: React.CSSProperties }) => (
            <div
              key={!enableSorting ? rowId : undefined}
              className={cn(
                listTemplateClassName,
                'bg-background gap-3 overflow-hidden rounded-md border px-3 py-3',
                onRowClick && 'hover:bg-muted/40 cursor-pointer transition-colors',
                isSelected && 'border-primary/40 bg-muted/40',
                renderRowClassName(item, index),
              )}
              style={{ ...listTemplateStyleVars, ...props?.style }}
              onClick={() => onRowClick?.(item)}
            >
              {enableSorting && (
                <button
                  type="button"
                  className={cn(
                    'text-muted-foreground flex size-full max-h-9 touch-none items-center justify-center rounded-md outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background',
                    sortingDisabled ? 'cursor-not-allowed opacity-40' : 'z-50 cursor-grab active:cursor-grabbing',
                  )}
                  onClick={event => event.stopPropagation()}
                  disabled={sortingDisabled}
                  {...(!sortingDisabled ? props?.attributes : {})}
                  {...(!sortingDisabled ? props?.listeners : {})}
                  aria-label="Drag to reorder"
                >
                  <GripVertical className="size-5 shrink-0" />
                  <span className="sr-only">Drag to reorder</span>
                </button>
              )}
              {enableSelection && (
                <div className="flex items-center justify-center" onClick={stopSelectionClick} onMouseDown={stopSelectionPointer} onPointerDown={stopSelectionPointer} onKeyDown={stopSelectionClick}>
                  {canSelectRow ? (
                    <Checkbox
                      aria-label={t('select', { defaultValue: 'Select' })}
                      className={selectionCheckboxClassName}
                      checked={isSelected}
                      onCheckedChange={() => handleToggleRowSelection(rowId, item)}
                    />
                  ) : (
                    <div className="h-3.5 w-3.5" />
                  )}
                </div>
              )}
              {columns.map(column => (
                <div key={`${column.id}-${rowId}`} className={cn('flex min-w-0 items-center overflow-x-hidden', getAlignClass(column.align), column.hideOnMobile && 'hidden md:flex', column.className)}>
                  {column.cell(item)}
                </div>
              ))}
              {hasMobileTrailingWidth && (
                <div className={cn('flex items-center justify-end gap-1 md:hidden', dir === 'rtl' && 'justify-start')}>
                  {mobileDetailActionColumns.map(column => (
                    <div key={`mobile-inline-actions-${column.id}-${rowId}`} className="text-sm">
                      {column.cell(item)}
                    </div>
                  ))}
                  {hasMobileExpandableDetails && (
                    <button
                      type="button"
                      className="text-muted-foreground/80 hover:text-foreground inline-flex h-8 w-8 items-center justify-center rounded-full transition-all active:scale-95"
                      onClick={event => {
                        event.stopPropagation()
                        setExpandedRowId(prev => (prev === rowId ? null : rowId))
                      }}
                      aria-label={isExpanded ? 'Collapse details' : 'Expand details'}
                    >
                      <ChevronDown className={cn('h-4 w-4 transition-transform', isExpanded && 'rotate-180')} />
                    </button>
                  )}
                </div>
              )}
              {hasMobileExpandableDetails && isExpanded && (
                <div className="col-span-full mt-2 space-y-1.5 md:hidden">
                  {mobileDetailDataColumns.length > 0 && (
                    <div className="space-y-1">
                      {mobileDetailDataColumns.map(column => {
                        const cellContent = column.cell(item)
                        if (cellContent === null || cellContent === undefined) return null

                        return (
                          <div key={`mobile-${column.id}-${rowId}`} className={cn('flex items-start justify-between gap-3 px-1.5 py-1.5', dir === 'rtl' && 'flex-row-reverse')}>
                            <div className="text-muted-foreground shrink-0 text-[10px] font-medium tracking-wide uppercase">{column.header}</div>
                            <div className={cn('min-w-0 text-sm leading-5', dir === 'rtl' ? 'text-left' : 'text-right')}>{cellContent}</div>
                          </div>
                        )
                      })}
                    </div>
                  )}
                </div>
              )}
            </div>
          )

          if (!enableSorting) {
            return renderRowContent()
          }

          return (
            <SortableListRow
              key={rowId}
              rowId={rowId}
              sortingDisabled={sortingDisabled}
              instantSortReorder={instantSortReorder}
              renderRow={props => renderRowContent(props)}
            />
          )
        })}

      {shouldShowEmptyState && (emptyState ?? <div className="bg-background text-muted-foreground rounded-md border px-3 py-6 text-center text-sm">No results.</div>)}
    </div>
  )
}
