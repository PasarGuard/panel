import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { ListColumn } from '@/components/common/list-generator'
import { ClientTemplateResponse } from '@/service/api'
import ClientTemplateActionsMenu from '@/components/templates/client-template-actions-menu'
import { Badge } from '@/components/ui/badge'
import ClientTemplateMarkers from '@/components/templates/client-template-markers'

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
  const compactBadgeClassName = 'h-5 shrink-0 px-1.5 text-[10px] leading-none'

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
            <ClientTemplateMarkers isDefault={template.is_default} isSystem={template.is_system} />
          </div>
        ),
      },
      {
        id: 'type',
        header: t('clientTemplates.templateType', { defaultValue: 'Type' }),
        width: '1fr',
        cell: template => (
          <Badge variant="secondary" className={`${compactBadgeClassName} capitalize`}>
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
    [compactBadgeClassName, t, onEdit],
  )
}
