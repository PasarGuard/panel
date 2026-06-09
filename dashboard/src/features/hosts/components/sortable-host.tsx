import { useSortable } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { UniqueIdentifier } from '@dnd-kit/core'
import { BaseHost } from '@/service/api'
import { Card } from '@/components/ui/card'
import { ChevronsLeftRightEllipsis, CloudCog, GripVertical, Settings } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import useDirDetection from '@/hooks/use-dir-detection'
import { cn } from '@/lib/utils'
import HostActionsMenu from './host-actions-menu'
import type { ReactNode } from 'react'

interface SortableHostProps {
  host: BaseHost
  onEdit: (host: BaseHost) => void
  onDuplicate: (host: BaseHost) => Promise<void>
  onDataChanged?: () => void // New callback for notifying parent about data changes
  disabled?: boolean // Disable drag and drop when updating priorities
  canUpdate?: boolean
  canCreate?: boolean
  selectionControl?: ReactNode
  selected?: boolean
}

export default function SortableHost({ host, onEdit, onDuplicate, onDataChanged, disabled = false, canUpdate = true, canCreate = true, selectionControl, selected = false }: SortableHostProps) {
  const { t } = useTranslation()
  const dir = useDirDetection()
  // Ensure host.id is not null before using it
  if (!host.id) {
    return null
  }

  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: host.id as UniqueIdentifier,
    disabled: disabled || !canUpdate,
  })

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    zIndex: isDragging ? 2 : 1,
    opacity: isDragging ? 0.8 : 1,
  }
  const cursor = isDragging ? 'grabbing' : 'grab'

  return (
    <div ref={setNodeRef} className="cursor-default" style={style} {...attributes}>
      <Card
        className={cn('group relative h-full p-4 transition-colors', canUpdate && 'hover:bg-accent cursor-pointer', selected && 'border-primary/50 bg-accent/30')}
        onClick={() => {
          if (canUpdate) onEdit(host)
        }}
      >
        <div className="flex items-start gap-3">
          <button
            type="button"
            style={{ cursor: disabled || !canUpdate ? 'not-allowed' : cursor }}
            className={cn('touch-none transition-opacity', disabled || !canUpdate ? 'cursor-not-allowed opacity-30' : 'opacity-50 group-hover:opacity-100')}
            {...(disabled || !canUpdate ? {} : listeners)}
            disabled={disabled || !canUpdate}
          >
            <GripVertical className="h-5 w-5" />
            <span className="sr-only">Drag to reorder</span>
          </button>
          <div className="min-w-0 flex-1">
            <div className="flex min-w-0 items-center gap-2">
              {selectionControl}
              <div className={cn('min-h-2 min-w-2 rounded-full', host.is_disabled ? 'bg-red-500' : 'bg-green-500')} />
              <div className="truncate font-medium">{host.remark ?? ''}</div>
            </div>
            <div className={cn('flex items-center gap-1', dir === 'rtl' && 'justify-start')}>
              <ChevronsLeftRightEllipsis className="text-muted-foreground h-4 w-4" />
              <div dir="ltr" className="text-muted-foreground truncate text-sm">
                {Array.isArray(host.address) ? host.address[0] || '' : (host.address ?? '')}:{host.port === null ? <Settings className="inline h-3 w-3" /> : host.port}
              </div>
            </div>
            <div className="text-muted-foreground flex items-center gap-1 truncate text-sm">
              <CloudCog className="h-4 w-4" />
              <span>{t('inbound')}: </span>
              <span dir="ltr">{host.inbound_tag ?? ''}</span>
            </div>
          </div>
          <HostActionsMenu host={host} onEdit={onEdit} onDuplicate={onDuplicate} onDataChanged={onDataChanged} canUpdate={canUpdate} canCreate={canCreate} />
        </div>
      </Card>
    </div>
  )
}
