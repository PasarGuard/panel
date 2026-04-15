import { Card } from '@/components/ui/card'
import { ClientTemplateResponse } from '@/service/api'
import ClientTemplateActionsMenu from './client-template-actions-menu'
import ClientTemplateMarkers from './client-template-markers'
import { cn } from '@/lib/utils'
import type { ReactNode } from 'react'

const ClientTemplate = ({
  template,
  onEdit,
  selectionControl,
  selected = false,
}: {
  template: ClientTemplateResponse
  onEdit: (template: ClientTemplateResponse) => void
  selectionControl?: ReactNode
  selected?: boolean
}) => {
  const templateTypeLabel = template.template_type.replace(/_/g, ' ')

  return (
    <Card className={cn('group relative h-full cursor-pointer px-4 py-5 transition-colors hover:bg-accent', selected && 'border-primary/50 bg-accent/30')} onClick={() => onEdit(template)}>
      <div className="flex items-start gap-3">
        {selectionControl ? <div className="pt-1">{selectionControl}</div> : null}
        <div className="flex min-w-0 flex-1 items-start gap-3">
          <div className="min-w-0 flex-1">
            <div className="flex min-w-0 items-center gap-2">
              <div className="min-w-0 truncate font-medium">{template.name}</div>
              <ClientTemplateMarkers isDefault={template.is_default} isSystem={template.is_system} />
            </div>
            <div className="min-w-0 truncate text-sm capitalize text-muted-foreground">{templateTypeLabel}</div>
          </div>
          <div onClick={event => event.stopPropagation()}>
            <ClientTemplateActionsMenu template={template} onEdit={onEdit} />
          </div>
        </div>
      </div>
    </Card>
  )
}

export default ClientTemplate
