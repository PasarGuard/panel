/** Selected rows keyed by row id, the shape of TanStack Table's `RowSelectionState`. */
export type RowSelection = Record<string, boolean>

export const getSelectedRowIds = (selection: RowSelection): number[] =>
  Object.entries(selection)
    .filter(([, selected]) => selected)
    .map(([rowId]) => Number(rowId))

/**
 * Keeps only the selected rows that are still shown. The table keeps its selection when the page, search or filters
 * change or a refresh moves rows away, so without this bulk actions would also hit rows the admin no longer sees.
 * Returns the same object when nothing is dropped.
 */
export const keepVisibleRowSelection = (selection: RowSelection, visibleRowIds: string[]): RowSelection => {
  const visible = new Set(visibleRowIds)
  const kept = Object.entries(selection).filter(([rowId, selected]) => selected && visible.has(rowId))
  return kept.length === Object.keys(selection).length ? selection : Object.fromEntries(kept)
}

/**
 * The selection the table keeps after a render: a reset (the caller cleared the selection) wins over dropping rows
 * that are no longer shown. Applied one after the other in the same render, the pruned old selection came back.
 */
export const nextRowSelection = (selection: RowSelection, visibleRowIds: string[], reset: boolean): RowSelection => (reset ? {} : keepVisibleRowSelection(selection, visibleRowIds))
