import { useSortable } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { GripVertical } from 'lucide-react'
import { cloneElement, type ReactElement, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'

interface SortableGridChildProps {
  reorderControl?: ReactNode
  selectionControl?: ReactNode
  selected?: boolean
}

interface SortableGridItemProps {
  id: string | number
  disabled?: boolean
  children: ReactElement<SortableGridChildProps>
  selectionControl?: ReactNode
  selected?: boolean
}

export function SortableGridItem({ id, disabled = false, children, selectionControl, selected }: SortableGridItemProps) {
  const { t } = useTranslation()
  const { attributes, listeners, setActivatorNodeRef, setNodeRef, transform, transition, isDragging } = useSortable({ id, disabled })
  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    zIndex: isDragging ? 2 : 1,
    opacity: isDragging ? 0.8 : 1,
  }
  const reorderControl = (
    <button
      ref={setActivatorNodeRef}
      type="button"
      className={cn(
        'text-muted-foreground focus-visible:ring-ring focus-visible:ring-offset-background mt-0.5 flex size-6 shrink-0 touch-none items-center justify-center rounded-md outline-none focus-visible:ring-2 focus-visible:ring-offset-2',
        disabled ? 'cursor-not-allowed opacity-40' : 'cursor-grab active:cursor-grabbing',
      )}
      onClick={event => event.stopPropagation()}
      disabled={disabled}
      {...(!disabled ? attributes : {})}
      {...(!disabled ? listeners : {})}
      aria-label={t('dragToReorder', { defaultValue: 'Drag to reorder' })}
    >
      <GripVertical className="size-5" />
    </button>
  )

  return (
    <div ref={setNodeRef} className="h-full" style={style}>
      {cloneElement(children, { reorderControl, selectionControl, selected })}
    </div>
  )
}
