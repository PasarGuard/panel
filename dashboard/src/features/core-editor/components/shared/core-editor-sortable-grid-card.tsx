import { CoreEditorListItemCard, type CoreEditorListItemCardProps } from '@/features/core-editor/components/shared/core-editor-list-item-card'
import type { UniqueIdentifier } from '@dnd-kit/core'
import { useSortable } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { cn } from '@/lib/utils'
import { GripVertical } from 'lucide-react'
import type { CSSProperties } from 'react'
import { useTranslation } from 'react-i18next'

export type CoreEditorSortableGridCardProps = Omit<CoreEditorListItemCardProps, 'reorderGrip'> & {
  sortableId: UniqueIdentifier
  sortingDisabled?: boolean
}

/**
 * Same control model as SortableSubscriptionRule: attributes + listeners on the grip only;
 * outer node only applies transform / ref / overflow containment.
 */
export function CoreEditorSortableGridCard({ sortableId, sortingDisabled = false, ...card }: CoreEditorSortableGridCardProps) {
  const { t } = useTranslation()
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: sortableId,
    disabled: sortingDisabled,
  })

  const style: CSSProperties = {
    transform: CSS.Transform.toString(transform),
    transition,
    zIndex: isDragging ? 2 : 1,
    opacity: isDragging ? 0.8 : 1,
    direction: 'ltr',
  }

  const cursor = sortingDisabled ? 'not-allowed' : isDragging ? 'grabbing' : 'grab'
  const gripLabel = t('coreEditor.dragToReorder', { defaultValue: 'Drag to reorder' })

  const grip = (
    <button
      type="button"
      style={{ cursor }}
      className={cn(
        'touch-none flex min-h-[44px] min-w-[40px] shrink-0 items-center justify-center self-start rounded-md transition-opacity active:bg-accent/40 sm:min-h-0 sm:min-w-0 sm:bg-transparent sm:p-0 sm:pt-1',
        sortingDisabled ? 'cursor-not-allowed opacity-35' : 'text-muted-foreground opacity-55 group-hover:opacity-100',
      )}
      onClick={event => event.stopPropagation()}
      disabled={sortingDisabled}
      {...(!sortingDisabled ? attributes : {})}
      {...(!sortingDisabled ? listeners : {})}
      aria-label={gripLabel}
    >
      <GripVertical className="size-5" />
      <span className="sr-only">{gripLabel}</span>
    </button>
  )

  return (
    <div ref={setNodeRef} style={style} className={cn('min-w-0 max-w-full cursor-default overflow-hidden')} dir="ltr">
      <div className="relative">
        <CoreEditorListItemCard {...card} reorderGrip={grip} />
        {isDragging ? (
          <div className="pointer-events-none absolute inset-0 rounded-md border border-primary/20 bg-primary/5" aria-hidden />
        ) : null}
      </div>
    </div>
  )
}
