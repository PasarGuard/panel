import React, { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { Checkbox } from '@/components/ui/checkbox'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'

export interface ListGeneratorGridProps<T> {
  data: T[]
  getRowId: (item: T) => string | number
  isLoading?: boolean
  loadingRows?: number
  emptyState?: React.ReactNode
  showEmptyState?: boolean
  className?: string
  gridClassName?: string
  gridStyle?: React.CSSProperties
  renderItem: (item: T, index: number) => React.ReactNode
  renderSkeleton?: (index: number) => React.ReactNode
  enableSelection?: boolean
  /** When true, selection checkboxes are shown and `selected` / `selectionControl` may be injected into valid React element roots. */
  injectSelectionProps?: boolean
  selectedRowIds?: Array<string | number>
  onSelectionChange?: (ids: Array<string | number>) => void
  isRowSelectable?: (item: T) => boolean
}

const headerSelectionCheckboxClassName =
  'h-3.5 w-3.5 rounded-[3px] border-muted-foreground/40 data-[state=checked]:border-primary'
const selectionCheckboxClassName =
  'h-3.5 w-3.5 rounded-[3px] border-muted-foreground/40 bg-background data-[state=checked]:border-primary data-[state=checked]:bg-primary data-[state=checked]:text-primary-foreground data-[state=indeterminate]:border-primary data-[state=indeterminate]:bg-primary data-[state=indeterminate]:text-primary-foreground'

export function ListGeneratorGrid<T>({
  data,
  getRowId,
  isLoading = false,
  loadingRows = 6,
  emptyState,
  showEmptyState = true,
  className,
  gridClassName,
  gridStyle,
  renderItem,
  renderSkeleton,
  enableSelection = false,
  injectSelectionProps = false,
  selectedRowIds = [],
  onSelectionChange,
  isRowSelectable,
}: ListGeneratorGridProps<T>) {
  const { t } = useTranslation()
  const selectedRowSet = useMemo(() => new Set(selectedRowIds), [selectedRowIds])
  const visibleSelectableRowIds = useMemo(
    () => (enableSelection ? data.filter(item => (isRowSelectable ? isRowSelectable(item) : true)).map(item => getRowId(item)) : []),
    [data, enableSelection, getRowId, isRowSelectable],
  )
  const hasData = data.length > 0
  const shouldShowEmptyState = showEmptyState && !isLoading && !hasData
  const showRows = !isLoading && hasData
  const isAllVisibleSelected = visibleSelectableRowIds.length > 0 && visibleSelectableRowIds.every(id => selectedRowSet.has(id))
  const isSomeVisibleSelected = !isAllVisibleSelected && visibleSelectableRowIds.some(id => selectedRowSet.has(id))
  const selectedVisibleRowCount = visibleSelectableRowIds.filter(id => selectedRowSet.has(id)).length

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

  const handleGridSelectionToolbarClick = () => {
    handleToggleAllVisibleSelection(!isAllVisibleSelected)
  }

  const handleGridSelectionToolbarKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (event.key !== 'Enter' && event.key !== ' ') {
      return
    }

    event.preventDefault()
    handleGridSelectionToolbarClick()
  }

  return (
    <div className={cn('flex w-full flex-col gap-2', className)}>
      {enableSelection && injectSelectionProps && visibleSelectableRowIds.length > 0 && (
        <div
          role="button"
          tabIndex={0}
          className="bg-background hover:bg-muted/40 focus-visible:ring-ring flex w-full items-center justify-between gap-3 rounded-md border px-3 py-2 text-left transition-colors focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:outline-none"
          onClick={handleGridSelectionToolbarClick}
          onKeyDown={handleGridSelectionToolbarKeyDown}
        >
          <div className="flex min-w-0 items-center gap-2 text-sm font-medium">
            <Checkbox
              aria-label={t('selectAll', { defaultValue: 'Select all' })}
              className={headerSelectionCheckboxClassName}
              checked={isAllVisibleSelected || (isSomeVisibleSelected && 'indeterminate')}
              onCheckedChange={value => handleToggleAllVisibleSelection(!!value)}
              onClick={stopSelectionClick}
              onPointerDown={stopSelectionClick}
              onKeyDown={stopSelectionClick}
            />
            <span className="truncate">{t('selectAll', { defaultValue: 'Select all' })}</span>
          </div>
          <span className="text-muted-foreground shrink-0 text-xs">
            {selectedVisibleRowCount}/{visibleSelectableRowIds.length}
          </span>
        </div>
      )}
      <div className={cn('grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3', gridClassName)} style={gridStyle}>
        {isLoading &&
          Array.from({ length: loadingRows }).map((_, index) =>
            renderSkeleton ? (
              <div key={`grid-skeleton-${index}`}>{renderSkeleton(index)}</div>
            ) : (
              <div key={`grid-skeleton-${index}`} className="bg-background rounded-md border p-4">
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
            const canSelectRow = enableSelection && injectSelectionProps && (isRowSelectable ? isRowSelectable(item) : true)
            const isSelected = selectedRowSet.has(rowId)
            const gridItem = renderItem(item, index)
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
                <Checkbox aria-label={selectionLabel} className={selectionCheckboxClassName} checked={isSelected} onCheckedChange={() => handleToggleRowSelection(rowId, item)} />
              </div>
            ) : undefined

            const renderedGridItem =
              injectSelectionProps && React.isValidElement(gridItem)
                ? React.cloneElement(gridItem as React.ReactElement<{ selected?: boolean; selectionControl?: React.ReactNode }>, {
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
      {shouldShowEmptyState && (emptyState ?? <div className="bg-background text-muted-foreground rounded-md border px-3 py-6 text-center text-sm">No results.</div>)}
    </div>
  )
}
