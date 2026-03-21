import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { ListColumn } from '@/components/common/list-generator'
import { ClientTemplateResponse } from '@/service/api'
import ClientTemplateActionsMenu from '@/components/templates/client-template-actions-menu'
import { Badge } from '@/components/ui/badge'
import { Shield } from 'lucide-react'

const TEMPLATE_TYPE_LABELS: Record<string, string> = {
  clash_subscription: 'Clash',
  xray_subscription: 'Xray',
  singbox_subscription: 'SingBox',
  user_agent: 'User Agent',
  grpc_user_agent: 'gRPC UA',
}

interface UseClientTemplatesListColumnsProps {
  onEdit: (template: ClientTemplateResponse) => void
}

export const useClientTemplatesListColumns = ({ onEdit }: UseClientTemplatesListColumnsProps) => {
  const { t } = useTranslation()

  return useMemo<ListColumn<ClientTemplateResponse>[]>(
    () => [
      {
        id: 'name',
        header: t('name', { defaultValue: 'Name' }),
        width: '2.5fr',
        cell: template => (
          <div
            className="flex min-w-0 cursor-pointer items-center gap-2"
            onClick={event => {
              event.stopPropagation()
              onEdit(template)
            }}
          >
            <span className="truncate font-medium">{template.name}</span>
            {template.is_default && (
              <Badge variant="secondary" className="shrink-0 text-xs">
                {t('default', { defaultValue: 'Default' })}
              </Badge>
            )}
            {template.is_system && (
              <Badge variant="outline" className="flex shrink-0 items-center gap-1 text-xs">
                <Shield className="h-3 w-3" />
                {t('system', { defaultValue: 'System' })}
              </Badge>
            )}
          </div>
        ),
      },
      {
        id: 'type',
        header: t('clientTemplates.templateType', { defaultValue: 'Type' }),
        width: '1fr',
        cell: template => (
          <Badge variant="secondary" className="text-xs capitalize">
            {TEMPLATE_TYPE_LABELS[template.template_type] || template.template_type.replace(/_/g, ' ')}
          </Badge>
        ),
        hideOnMobile: true,
      },
      {
        id: 'actions',
        header: '',
        width: '24px',
        align: 'end',
        hideOnMobile: false,
        cell: template => <ClientTemplateActionsMenu template={template} onEdit={onEdit} />,
      },
    ],
    [t, onEdit],
  )
}
