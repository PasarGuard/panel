import { Card } from '@/components/ui/card'
import { CoreResponse } from '@/service/api'
import CoreActionsMenu from './core-actions-menu'
import { cn } from '@/lib/utils'

interface CoreProps {
  core: CoreResponse
  onEdit: (core: CoreResponse) => void
  onToggleStatus: (core: CoreResponse) => Promise<void>
  onDuplicate?: () => void
  onDelete?: () => void
}

export default function Core({ core, onEdit, onDuplicate, onDelete }: CoreProps) {
  return (
    <Card className="group relative h-full cursor-pointer px-4 py-5 transition-colors hover:bg-accent" onClick={() => onEdit(core)}>
      <div className="flex items-center gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <div className={cn('min-h-2 min-w-2 rounded-full', 'bg-green-500')} />
              <div className="font-medium">{core.name}</div>
            </div>
          </div>
        </div>
        <CoreActionsMenu core={core} onEdit={onEdit} onDuplicate={onDuplicate} onDelete={onDelete} />
      </div>
    </Card>
  )
}
