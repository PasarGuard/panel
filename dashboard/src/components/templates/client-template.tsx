import { Card, CardTitle } from '../ui/card'
import { useTranslation } from 'react-i18next'
import { ClientTemplateResponse } from '@/service/api'
import ClientTemplateActionsMenu from './client-template-actions-menu'
import { Badge } from '../ui/badge'
import { Shield } from 'lucide-react'

const ClientTemplate = ({
  template,
  onEdit,
}: {
  template: ClientTemplateResponse
  onEdit: (template: ClientTemplateResponse) => void
}) => {
  const { t } = useTranslation()

  return (
    <Card className="group rounded-lg px-5 py-6 transition-colors hover:bg-accent">
      <div className="flex items-center justify-between">
        <div className="flex-1 cursor-pointer" onClick={() => onEdit(template)}>
          <CardTitle className="flex items-center gap-x-2">
            <span>{template.name}</span>
            {template.is_default && <Badge variant="secondary" className="text-xs">{t('default', { defaultValue: 'Default' })}</Badge>}
            {template.is_system && (
              <Badge variant="outline" className="flex items-center gap-1 text-xs">
                <Shield className="h-3 w-3" />
                {t('system', { defaultValue: 'System' })}
              </Badge>
            )}
          </CardTitle>
          <div className="mt-1.5">
            <Badge variant="secondary" className="text-xs capitalize">
              {template.template_type.replace(/_/g, ' ')}
            </Badge>
          </div>
        </div>
        <ClientTemplateActionsMenu template={template} onEdit={onEdit} />
      </div>
    </Card>
  )
}

export default ClientTemplate
