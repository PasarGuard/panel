import { Card } from '@/components/ui/card'
import { cn } from '@/lib/utils'
import type { ReactNode } from 'react'

export interface CoreEditorListItemCardProps {
  selectionControl?: ReactNode
  /** Grip handle injected when using {@link CoreEditorSortableGridCard} (grid DnD). */
  reorderGrip?: ReactNode
  /** Checkbox / bulk selection styling (aligned with cores list). */
  selected?: boolean
  /** Primary headline. */
  title: ReactNode
  /** Secondary lines (protocol, ports, tags, …). */
  lines?: ReactNode[]
  actionsMenu?: ReactNode
  onOpen: () => void
}

/**
 * Card shell for core editor entities — matches `@/features/nodes/components/cores/core` grid layout / spacing.
 */
export function CoreEditorListItemCard({
  selectionControl,
  reorderGrip,
  selected = false,
  title,
  lines = [],
  actionsMenu,
  onOpen,
}: CoreEditorListItemCardProps) {
  return (
    <Card
      className={cn(
        'group hover:bg-accent relative h-full max-w-full min-w-0 cursor-pointer overflow-hidden px-4 py-5 transition-colors',
        selected && 'border-primary/50 bg-accent/30',
      )}
      onClick={onOpen}
    >
      <div className="flex min-w-0 max-w-full items-start gap-3">
        {reorderGrip ? <div className="flex shrink-0">{reorderGrip}</div> : null}
        {selectionControl ? <div className="pt-1">{selectionControl}</div> : null}
        <div className="flex min-w-0 max-w-full flex-1 items-start gap-3 overflow-hidden">
          <div className="min-w-0 flex-1 overflow-hidden">
            <div className="flex min-w-0 items-center gap-2">{title}</div>
            {lines.length > 0 ? (
              <div className="text-muted-foreground mt-2 space-y-0.5 text-xs leading-snug sm:text-[13px]">
                {lines.map((line, i) => (
                  <div key={i} className="min-w-0">
                    {line}
                  </div>
                ))}
              </div>
            ) : null}
          </div>
          {actionsMenu ? <div className="flex shrink-0">{actionsMenu}</div> : null}
        </div>
      </div>
    </Card>
  )
}
