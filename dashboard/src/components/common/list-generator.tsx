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
  enableSelection?: boolean
  enableGridSelection?: boolean
  selectedRowIds?: Array<string | number>
  onSelectionChange?: (ids: Array<string | number>) => void
  isRowSelectable?: (item: T) => boolean
}

interface SortableListRowProps {
  rowId: string | number
  sortingDisabled: boolean
  renderRow: (props: { attributes: ReturnType<typeof useSortable>['attributes']; listeners: ReturnType<typeof useSortable>['listeners']; style: React.CSSProperties }) => React.ReactNode
}

function SortableListRow({ rowId, sortingDisabled, renderRow }: SortableListRowProps) {
  const { attributes, listeners, setNodeRef, transform, transition } = useSortable({
    id: rowId,
    disabled: sortingDisabled,
  })

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
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
  mode = 'list',
  gridClassName,
  gridStyle,
  renderGridItem,
  renderGridSkeleton,
  enableSorting = false,
  sortingDisabled = false,
  enableSelection = false,
  enableGridSelection = false,
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
  const listTemplateClassName = 'grid [grid-template-columns:var(--list-cols-mobile)] md:[grid-template-columns:var(--list-cols-desktop)]'
  const dir = useDirDetection()
  const gridContent = (showRows || isLoading) && renderGridItem
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
            {showRows &&
              data.map((item, index) => {
                const rowId = getRowId(item)
                const canSelectRow = enableSelection && enableGridSelection && (isRowSelectable ? isRowSelectable(item) : true)
                const isSelected = selectedRowSet.has(rowId)
                const gridItem = renderGridItem(item, index)
                const selectionLabel = t(isSelected ? 'selected' : 'select', {
                  defaultValue: isSelected ? 'Selected' : 'Select',
                })
                const selectionControl = canSelectRow ? (
                  <div
                    className="flex shrink-0 items-center"
                    onClick={stopSelectionClick}
                    onMouseDown={stopSelectionPointer}
                    onPointerDown={stopSelectionPointer}
                    onKeyDown={stopSelectionClick}
                  >
                    <Checkbox
                      aria-label={selectionLabel}
                      className={selectionCheckboxClassName}
                      checked={isSelected}
                      onCheckedChange={() => handleToggleRowSelection(rowId, item)}
                    />
                  </div>
                ) : undefined

                const renderedGridItem =
                  enableGridSelection && React.isValidElement<any>(gridItem)
                    ? React.cloneElement(gridItem, {
                        selected: isSelected,
                        selectionControl,
                      })
                    : gridItem

                return (
                  <div key={rowId} className="relative">
                    {renderedGridItem}
                  </div>
                )
              })}
          </div>
        ) : (
          <div className="rounded-md border bg-background px-3 py-6 text-center text-sm text-muted-foreground">Provide `renderGridItem` to render grid mode.</div>
        )}
        {shouldShowEmptyState && (emptyState ?? <div className="rounded-md border bg-background px-3 py-6 text-center text-sm text-muted-foreground">No results.</div>)}
      </div>
    )
  }

  return (
    <div className={cn('flex w-full flex-col gap-2', className)}>
      {!hideHeader && (
        <div className={cn(listTemplateClassName, 'gap-3 px-3 text-xs font-semibold uppercase text-muted-foreground', headerClassName)} style={listTemplateStyleVars}>
          {enableSorting && <div aria-hidden="true" />}
          {enableSelection && (
            <div className="flex items-center justify-center">
              <Checkbox
                aria-label={t('selectAll', { defaultValue: 'Select all' })}
                className={selectionCheckboxClassName}
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
          <div key={`list-skeleton-${rowIndex}`} className={cn(listTemplateClassName, 'gap-3 rounded-md border bg-background px-3 py-3')} style={listTemplateStyleVars}>
            {enableSorting && <div aria-hidden="true" />}
            {enableSelection && <div aria-hidden="true" />}
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

          const RowContent = (props?: { attributes?: ReturnType<typeof useSortable>['attributes']; listeners?: ReturnType<typeof useSortable>['listeners']; style?: React.CSSProperties }) => (
            <div
              className={cn(
                listTemplateClassName,
                'gap-3 overflow-hidden rounded-md border bg-background px-3 py-3',
                onRowClick && 'cursor-pointer transition-colors hover:bg-muted/40',
                isSelected && 'border-primary/40 bg-muted/40',
                renderRowClassName(item, index),
              )}
              style={{ ...listTemplateStyleVars, ...props?.style }}
              onClick={() => onRowClick?.(item)}
              {...props?.attributes}
            >
              {enableSorting && (
                <button
                  type="button"
                  className={cn('flex touch-none items-center justify-center text-muted-foreground', sortingDisabled ? 'cursor-not-allowed opacity-40' : 'z-50 cursor-grab')}
                  onClick={event => event.stopPropagation()}
                  {...props?.listeners}
                  aria-label="Drag to reorder"
                >
                  <GripVertical className="h-5 w-5" />
                  <span className="sr-only">Drag to reorder</span>
                </button>
              )}
              {enableSelection && (
                <div
                  className="flex items-center justify-center"
                  onClick={stopSelectionClick}
                  onMouseDown={stopSelectionPointer}
                  onPointerDown={stopSelectionPointer}
                  onKeyDown={stopSelectionClick}
                >
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
                <div key={`${column.id}-${rowId}`} className={cn('flex min-w-0 items-center justify-end', getAlignClass(column.align), column.hideOnMobile && 'hidden md:flex', column.className)}>
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
                      className="inline-flex h-8 w-8 items-center justify-center rounded-full text-muted-foreground/80 transition-all hover:text-foreground active:scale-95"
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
                      {mobileDetailDataColumns.map(column => (
                        <div key={`mobile-${column.id}-${rowId}`} className={cn('flex items-start justify-between gap-3 px-1.5 py-1.5', dir === 'rtl' && 'flex-row-reverse')}>
                          <div className="shrink-0 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">{column.header}</div>
                          <div className={cn('min-w-0 text-sm leading-5', dir === 'rtl' ? 'text-left' : 'text-right')}>{column.cell(item)}</div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          )

          if (!enableSorting) {
            return <RowContent key={rowId} />
          }

          return <SortableListRow key={rowId} rowId={rowId} sortingDisabled={sortingDisabled} renderRow={props => <RowContent {...props} />} />
        })}

      {shouldShowEmptyState && (emptyState ?? <div className="rounded-md border bg-background px-3 py-6 text-center text-sm text-muted-foreground">No results.</div>)}
    </div>
  )
}
