/**
 * Updates a tracked row index after an `arrayMove(from, to)` so it still refers
 * to the same logical element when possible (`sel === from` tracks the moved row).
 */
export function remapIndexAfterArrayMove(sel: number, from: number, to: number): number {
  if (sel === from) return to
  if (from < to && sel > from && sel <= to) return sel - 1
  if (from > to && sel >= to && sel < from) return sel + 1
  return sel
}
