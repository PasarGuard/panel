import ViewToggle from '@/components/common/view-toggle'
import { ListGenerator, type ListColumn } from '@/components/common/list-generator'
import { ListGeneratorGrid } from '@/components/common/list-generator-grid'
import { BulkActionsBar } from '@/features/users/components/bulk-actions-bar'
import { BulkActionAlertDialog } from '@/features/users/components/bulk-action-alert-dialog'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import useDirDetection from '@/hooks/use-dir-detection'
import { usePersistedViewMode } from '@/hooks/use-persisted-view-mode'
import {
  CORE_EDITOR_VIEW_MODE_STORAGE_KEY,
  DEFAULT_CORE_EDITOR_VIEW_MODE,
} from '@/utils/userPreferenceStorage'
import {
  closestCenter,
  DndContext,
  type DragEndEvent,
  KeyboardSensor,
  PointerSensor,
  type UniqueIdentifier,
  useSensor,
  useSensors,
} from '@dnd-kit/core'
import { rectSortingStrategy, SortableContext, sortableKeyboardCoordinates } from '@dnd-kit/sortable'
import type { ColumnDef } from '@tanstack/react-table'
import { flexRender, getCoreRowModel, useReactTable } from '@tanstack/react-table'
import { cn } from '@/lib/utils'
import { CoreEditorListItemCard } from '@/features/core-editor/components/shared/core-editor-list-item-card'
import { CoreEditorSortableGridCard } from '@/features/core-editor/components/shared/core-editor-sortable-grid-card'
import { CoreEditorRowActionsMenu } from '@/features/core-editor/components/shared/core-editor-row-actions-menu'
import { Search, X } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import type { ReactNode } from 'react'

function stripActionsColumns<T>(columns: ColumnDef<T, unknown>[]) {
  return columns.filter(col => !(typeof col.id === 'string' && col.id === 'actions'))
}

function defaultSearchHaystack<TData>(item: TData): string {
  try {
    return JSON.stringify(item)
  } catch {
    return String(item)
  }
}

/** Grid loading placeholder aligned with {@link CoreEditorListItemCard} / {@link CoreEditorSortableGridCard}. */
function CoreEditorGridCardSkeleton({
  reorderEnabled,
  selectionEnabled,
}: {
  reorderEnabled: boolean
  selectionEnabled: boolean
}) {
  return (
    <Card
      className={cn(
        'relative h-full max-w-full min-w-0 overflow-hidden px-4 py-5',
        'group cursor-default',
      )}
    >
      <div className="flex min-w-0 max-w-full items-start gap-3">
        {reorderEnabled ? (
          <Skeleton
            className="mt-0.5 h-11 w-10 shrink-0 rounded-md sm:mt-1 sm:h-6 sm:w-6"
            aria-hidden
          />
        ) : null}
        {selectionEnabled ? (
          <div className="pt-1">
            <Skeleton className="h-3.5 w-3.5 shrink-0 rounded-[3px]" aria-hidden />
          </div>
        ) : null}
        <div className="flex min-w-0 max-w-full flex-1 items-start gap-3 overflow-hidden">
          <div className="min-w-0 flex-1 overflow-hidden">
            <div className="flex min-w-0 items-center gap-2">
              <Skeleton className="h-5 w-[min(100%,14rem)]" />
            </div>
            <div className="mt-2 space-y-0.5">
              <Skeleton className="h-3.5 w-10 sm:w-12" />
              <Skeleton className="h-[13px] w-full max-w-48" />
              <Skeleton className="h-[13px] w-full max-w-40" />
              <Skeleton className="hidden h-[13px] w-full max-w-36 sm:block" />
            </div>
          </div>
          <div className="flex shrink-0">
            <Skeleton className="size-8 rounded-md" aria-hidden />
          </div>
        </div>
      </div>
    </Card>
  )
}

export interface CoreEditorDataTableProps<TData> {
  columns: ColumnDef<TData, unknown>[]
  data: TData[]
  getRowId?: (row: TData, index: number) => string
  onRowClick?: (row: TData, rowIndex: number) => void
  /** Remove single row index (menus + dialogs stay in sections). */
  onRemoveRow: (index: number) => void
  /** Indices of rows to remove after bulk confirmation (typically many at once). */
  onBulkRemove: (indices: number[]) => void
  /** When set, row remove and bulk remove cannot drop the list below this count. */
  minRowCount?: number
  /** Toast (and guard) when remove would violate {@link minRowCount}. */
  minRowCountMessage?: string
  enableSelection?: boolean
  bulkDeleteTitle?: string
  bulkDeleteDescription?: string
  emptyLabel?: string
  /** Drag-and-drop reorder (same primitives as hosts + subscription apps). Pair with {@link onReorder}. */
  enableReorder?: boolean
  onReorder?: (fromIndex: number, toIndex: number) => void
  /** When true, drag handles remain visible but reorder is disabled (`sensors=[]`). */
  sortingDisabled?: boolean
  /** Values matched against the search query (substring, case-insensitive). Defaults to JSON.stringify(row). */
  getSearchableText?: (item: TData) => string
  searchPlaceholder?: string
  /** Optional controls rendered next to the grid/list view toggle. */
  toolbarActions?: ReactNode
}

export function CoreEditorDataTable<TData>({
  columns,
  data,
  getRowId,
  onRowClick,
  onRemoveRow,
  onBulkRemove,
  minRowCount,
  minRowCountMessage,
  enableSelection,
  bulkDeleteTitle,
  bulkDeleteDescription,
  emptyLabel,
  enableReorder,
  onReorder,
  sortingDisabled = false,
  getSearchableText,
  searchPlaceholder,
  toolbarActions,
}: CoreEditorDataTableProps<TData>) {
  const { t, i18n } = useTranslation()
  const dir = useDirDetection()
  const [viewMode, setViewMode] = usePersistedViewMode(
    CORE_EDITOR_VIEW_MODE_STORAGE_KEY,
    DEFAULT_CORE_EDITOR_VIEW_MODE,
  )
  const [searchQuery, setSearchQuery] = useState('')
  const selectionEnabled = enableSelection !== false
  const [selectedRows, setSelectedRows] = useState<Array<string | number>>([])
  const [bulkOpen, setBulkOpen] = useState(false)

  const removeDisabled = minRowCount != null && data.length <= minRowCount
  const bulkRemoveAllowed =
    !minRowCount || selectedRows.length === 0 || selectedRows.length <= data.length - minRowCount

  const resolvedGetRowKey = useMemo(
    () => (getRowId ? (item: TData, idx: number) => getRowId(item, idx) : (_item: TData, idx: number) => String(idx)),
    [getRowId],
  )

  const reorderEnabled = Boolean(enableReorder && onReorder)

  const sensors = useSensors(
    useSensor(PointerSensor),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    }),
  )

  const searchNeedle = searchQuery.trim().toLowerCase()
  const hasActiveSearch = searchNeedle.length > 0

  const visibleEntries = useMemo(() => {
    if (!hasActiveSearch) {
      return data.map((item, originalIndex) => ({ item, originalIndex }))
    }
    const haystackFn = getSearchableText ?? defaultSearchHaystack
    return data
      .map((item, originalIndex) => ({ item, originalIndex }))
      .filter(({ item }) => haystackFn(item).toLowerCase().includes(searchNeedle))
  }, [data, getSearchableText, hasActiveSearch, searchNeedle])

  const displayData = useMemo(() => visibleEntries.map(e => e.item), [visibleEntries])
  const originalIndices = useMemo(() => visibleEntries.map(e => e.originalIndex), [visibleEntries])

  useEffect(() => {
    setSelectedRows([])
  }, [searchQuery])

  const sortableIds = useMemo(
    () =>
      visibleEntries.map(
        ({ item, originalIndex }) => resolvedGetRowKey(item, originalIndex) as UniqueIdentifier,
      ),
    [visibleEntries, resolvedGetRowKey],
  )

  const effectiveSortingDisabled = sortingDisabled || (reorderEnabled && hasActiveSearch)

  const handleDragEnd = useCallback(
    (event: DragEndEvent) => {
      if (!reorderEnabled || !onReorder || effectiveSortingDisabled) return
      const { active, over } = event
      if (!over || active.id === over.id) return
      const oldIndex = sortableIds.findIndex(id => id === active.id)
      const newIndex = sortableIds.findIndex(id => id === over.id)
      if (oldIndex === -1 || newIndex === -1) return
      const fromOrig = originalIndices[oldIndex]
      const toOrig = originalIndices[newIndex]
      onReorder(fromOrig, toOrig)
    },
    [reorderEnabled, onReorder, effectiveSortingDisabled, sortableIds, originalIndices],
  )

  const dataColumns = useMemo(() => stripActionsColumns(columns), [columns])

  const tableConfig = useMemo(
    () => ({
      data: displayData,
      columns: dataColumns,
      getRowId: (_row: TData, index: number) => resolvedGetRowKey(_row, originalIndices[index]),
      getCoreRowModel: getCoreRowModel(),
    }),
    [dataColumns, displayData, resolvedGetRowKey, originalIndices],
  )

  const table = useReactTable(tableConfig)

  const listColumnsSansMenu = useMemo((): ListColumn<TData>[] => {
    const headerGroup = table.getHeaderGroups()[0]
    if (!headerGroup) return []

    const visibleLeaves = table.getVisibleLeafColumns()
    /** Match {@link useNodeListColumns}: keep # + first summary column on the row; rest + chevron expand on mobile. */
    const primaryMobileIds = new Set<string>()
    if (visibleLeaves.some(c => c.id === 'index')) {
      primaryMobileIds.add('index')
    }
    const firstNonIndex = visibleLeaves.find(c => c.id !== 'index')
    if (firstNonIndex) {
      primaryMobileIds.add(firstNonIndex.id)
    }

    return visibleLeaves.map(column => {
        let width: string | undefined
        if (column.id === 'index') width = '52px'

        const hdr = headerGroup.headers.find(h => h.column.id === column.id && !h.isPlaceholder)

        const skeletonClassName =
          column.id === 'index' ? 'h-4 w-6 shrink-0' : column.id === 'port' ? 'h-4 max-w-[4rem]' : undefined

        return {
          id: column.id,
          width,
          align: 'start' as const,
          headerClassName: 'truncate',
          className: 'text-sm py-2',
          skeletonClassName,
          hideOnMobile: !primaryMobileIds.has(column.id),
          header:
            hdr && !hdr.isPlaceholder ? flexRender(column.columnDef.header, hdr.getContext()) : null,

          cell: (item: TData) => {
            const displayIdx = displayData.indexOf(item)
            if (displayIdx < 0) return null
            const row = table.getRowModel().rows[displayIdx]
            const cell = row?.getVisibleCells().find(c => c.column.id === column.id)
            if (!cell) return null
            return flexRender(cell.column.columnDef.cell, cell.getContext())
          },
        }
      })
    // Headers are rendered once into React nodes here; `table`/`displayData` stay the same on locale change.
  }, [table, displayData, i18n.language])

  const listColumns = useMemo((): ListColumn<TData>[] => {
    return [
      ...listColumnsSansMenu,
      {
        id: '__menu',
        header: '',
        width: '44px',
        align: 'end',
        hideOnMobile: true,
        skeletonClassName: 'size-8 max-w-8 shrink-0 rounded-md',
        cell: (item: TData) => {
          const displayIdx = displayData.indexOf(item)
          if (displayIdx < 0) return null
          const originalIdx = originalIndices[displayIdx]
          return (
            <CoreEditorRowActionsMenu
              onEdit={() => onRowClick?.(item, originalIdx)}
              onRemove={() => onRemoveRow(originalIdx)}
              removeDisabled={removeDisabled}
            />
          )
        },
      },
    ]
  }, [listColumnsSansMenu, displayData, originalIndices, onRowClick, onRemoveRow, removeDisabled])

  const empty = emptyLabel ?? t('noResults', { defaultValue: 'No results' })
  const emptyDisplay =
    hasActiveSearch && data.length > 0
      ? t('noSearchResults', { defaultValue: 'No results match your search.' })
      : empty

  const listGetRowId = (item: TData) => {
    const displayIdx = displayData.indexOf(item)
    return displayIdx >= 0 ? resolvedGetRowKey(item, originalIndices[displayIdx]) : String(displayIdx)
  }

  const handleRowActivation = (item: TData, originalIdx: number, e?: React.MouseEvent) => {
    if (originalIdx < 0 || !onRowClick) return
    const target = e?.target
    if (target instanceof Element) {
      if (
        target.closest('button') ||
        target.closest('[role="menu"], [role="menuitem"], [data-radix-popper-content-wrapper]')
      ) {
        return
      }
    }
    onRowClick(item, originalIdx)
  }

  const bulkTitle =
    bulkDeleteTitle ?? t('coreEditor.bulkRemove.title', { defaultValue: 'Remove selected entries' })

  const bulkDesc =
    selectedRows.length > 0
      ? (bulkDeleteDescription ??
        t('coreEditor.bulkRemove.description', {
          count: selectedRows.length,
          defaultValue:
            'Remove {{count}} selected items? They will be dropped from configuration.',
        }))
      : ''

  const confirmBulkDelete = () => {
    const rm = new Set(selectedRows.map(id => Number(id)).filter(Number.isFinite))
    if (minRowCount != null && data.length - rm.size < minRowCount) {
      toast.error(
        minRowCountMessage ??
          t('coreEditor.minRowsBlocked', { defaultValue: 'That would remove too many entries.' }),
      )
      setBulkOpen(false)
      return
    }
    onBulkRemove(Array.from(rm))
    setSelectedRows([])
    setBulkOpen(false)
  }

  const buildGridPresentation = (item: TData, displayIndex: number) => {
    const originalIndex = originalIndices[displayIndex]
    const columnsForBody = listColumnsSansMenu.filter(c => c.id !== '__menu')

    const indexCol = columnsForBody.find(c => c.id === 'index')
    const payloadCols = columnsForBody.filter(c => c.id !== 'index')

    const primary = payloadCols[0]?.cell(item)
    const title = (
      <div className="truncate font-medium">{primary ?? <span className="text-muted-foreground">—</span>}</div>
    )

    const lines: ReactNode[] = []
    if (indexCol && displayIndex !== undefined) {
      lines.push(
        <span dir="ltr" className="text-muted-foreground/90 text-[11px]">
          {(indexCol.header != null ? String(indexCol.header) : '#')} {displayIndex + 1}
        </span>,
      )
    }

    payloadCols.slice(1).forEach(col => {
      const val = col.cell(item)
      if (val === null || val === undefined || val === false) return
      lines.push(
        <div key={col.id} className="flex min-w-0 flex-wrap items-baseline gap-x-1.5 gap-y-0.5">
          {col.header != null ? (
            <span className="shrink-0 text-[11px] font-medium tracking-wide text-muted-foreground">
              {col.header}
            </span>
          ) : null}
          <span className="min-w-0">{val}</span>
        </div>,
      )
    })

    const menu = (
      <CoreEditorRowActionsMenu
        onEdit={() => onRowClick?.(item, originalIndex)}
        onRemove={() => onRemoveRow(originalIndex)}
        removeDisabled={removeDisabled}
      />
    )

    return { title, lines, menu }
  }

  const gridItem = (item: TData, displayIndex: number) => {
    const { title, lines, menu } = buildGridPresentation(item, displayIndex)
    const originalIndex = originalIndices[displayIndex]

    const cardProps = {
      title,
      lines,
      actionsMenu: menu,
      onOpen: () => handleRowActivation(item, originalIndex),
    }

    if (reorderEnabled) {
      return (
        <CoreEditorSortableGridCard
          {...cardProps}
          sortableId={resolvedGetRowKey(item, originalIndex)}
          sortingDisabled={effectiveSortingDisabled}
        />
      )
    }

    return <CoreEditorListItemCard {...cardProps} />
  }

  const listInner =
    viewMode === 'grid' ? (
      <ListGeneratorGrid<TData>
        data={displayData}
        getRowId={listGetRowId}
        className={cn('gap-4', reorderEnabled ? 'max-w-full min-w-0 overflow-hidden' : null)}
        emptyState={<div className="text-muted-foreground rounded-md border px-4 py-10 text-center text-sm">{emptyDisplay}</div>}
        showEmptyState={displayData.length === 0}
        enableSelection={selectionEnabled}
        injectSelectionProps={selectionEnabled}
        selectedRowIds={selectionEnabled ? selectedRows : undefined}
        onSelectionChange={selectionEnabled ? ids => setSelectedRows(ids) : undefined}
        renderItem={(item, i) => gridItem(item, i)}
        renderSkeleton={() => (
          <CoreEditorGridCardSkeleton reorderEnabled={reorderEnabled} selectionEnabled={selectionEnabled} />
        )}
      />
    ) : (
      <ListGenerator<TData>
        data={displayData}
        columns={listColumns}
        getRowId={listGetRowId}
        className={cn('gap-1.5', reorderEnabled ? 'max-w-full min-w-0 overflow-hidden' : null)}
        onRowClick={onRowClick ? item => {
          const d = displayData.indexOf(item)
          if (d < 0) return
          handleRowActivation(item, originalIndices[d])
        } : undefined}
        emptyState={<div className="text-muted-foreground rounded-md border px-4 py-10 text-center text-sm">{emptyDisplay}</div>}
        showEmptyState={displayData.length === 0}
        enableSelection={selectionEnabled}
        selectedRowIds={selectionEnabled ? selectedRows : undefined}
        onSelectionChange={selectionEnabled ? ids => setSelectedRows(ids) : undefined}
        enableSorting={reorderEnabled}
        sortingDisabled={effectiveSortingDisabled}
      />
    )

  /** Hosts list uses bare `DndContext`/`SortableContext` (no modifiers). Nested `overflow-y-auto` in {@link CoreEditorLayout} stacks badly with default auto-scroll, so programmatic scroll during drag is off here. */
  const listWrapped = reorderEnabled ? (
    <DndContext
      sensors={effectiveSortingDisabled ? [] : sensors}
      collisionDetection={closestCenter}
      onDragEnd={handleDragEnd}
      autoScroll={false}
    >
      <SortableContext items={sortableIds} strategy={rectSortingStrategy}>
        {listInner}
      </SortableContext>
    </DndContext>
  ) : (
    listInner
  )

  const clearSearch = () => setSearchQuery('')

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="relative min-w-0 flex-1 sm:max-w-md">
          <Search
            className={cn(
              'pointer-events-none absolute top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground',
              dir === 'rtl' ? 'right-2.5' : 'left-2.5',
            )}
            aria-hidden
          />
          <Input
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            placeholder={searchPlaceholder ?? t('search')}
            className={cn(dir === 'rtl' ? 'pr-9 pl-9' : 'pl-9 pr-9')}
            aria-label={t('search')}
          />
          {searchQuery ? (
            <button
              type="button"
              onClick={clearSearch}
              className={cn(
                'absolute top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground',
                dir === 'rtl' ? 'left-1.5' : 'right-1.5',
              )}
            >
              <X className="h-4 w-4" />
            </button>
          ) : null}
        </div>
        <div className="flex shrink-0 items-center justify-end gap-2 sm:justify-start">
          {toolbarActions}
          <ViewToggle value={viewMode} onChange={setViewMode} />
        </div>
      </div>
      {selectionEnabled ? (
        <BulkActionsBar
          selectedCount={selectedRows.length}
          onClear={() => setSelectedRows([])}
          onDelete={
            selectedRows.length > 0 && bulkRemoveAllowed ? () => setBulkOpen(true) : undefined
          }
        />
      ) : null}
      <BulkActionAlertDialog
        open={bulkOpen}
        onOpenChange={setBulkOpen}
        title={bulkTitle}
        description={bulkDesc}
        actionLabel={t('delete')}
        onConfirm={confirmBulkDelete}
        destructive
      />
      {listWrapped}
    </div>
  )
}
