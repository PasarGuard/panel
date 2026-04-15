import { Card } from '@/components/ui/card'
import { CoreResponse } from '@/service/api'
import CoreActionsMenu from './core-actions-menu'
import { cn } from '@/lib/utils'
import type { ReactNode } from 'react'

interface CoreProps {
  core: CoreResponse
  onEdit: (core: CoreResponse) => void
  onToggleStatus: (core: CoreResponse) => Promise<void>
  onDuplicate?: () => void
  onDelete?: () => void
  selectionControl?: ReactNode
  selected?: boolean
}

export default function Core({ core, onEdit, onDuplicate, onDelete, selectionControl, selected = false }: CoreProps) {
  return (
    <Card className={cn('group relative h-full cursor-pointer px-4 py-5 transition-colors hover:bg-accent', selected && 'border-primary/50 bg-accent/30')} onClick={() => onEdit(core)}>
      <div className="flex items-start gap-3">
        {selectionControl ? <div className="pt-1">{selectionControl}</div> : null}
        <div className="flex min-w-0 flex-1 items-start gap-3">
          <div className="min-w-0 flex-1">
            <div className="flex items-center justify-between gap-2">
              <div className="flex min-w-0 items-center gap-2">
                <div className={cn('min-h-2 min-w-2 rounded-full', 'bg-green-500')} />
                <div className="truncate font-medium">{core.name}</div>
              </div>
            </div>
          </div>
          <CoreActionsMenu core={core} onEdit={onEdit} onDuplicate={onDuplicate} onDelete={onDelete} />
        </div>
      </div>
    </Card>
  )
}
