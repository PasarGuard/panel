import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { Infinity } from 'lucide-react'
import { ListColumn } from '@/components/common/list-generator'
import { UserTemplateResponse } from '@/service/api'
import UserTemplateActionsMenu from '@/components/templates/user-template-actions-menu'
import { formatBytes } from '@/utils/formatByte'
import { cn } from '@/lib/utils'

interface UseUserTemplatesListColumnsProps {
  onEdit: (template: UserTemplateResponse) => void
  onToggleStatus: (template: UserTemplateResponse) => void
}

export const useUserTemplatesListColumns = ({ onEdit, onToggleStatus }: UseUserTemplatesListColumnsProps) => {
  const { t } = useTranslation()

  return useMemo<ListColumn<UserTemplateResponse>[]>(
    () => [
      {
        id: 'name',
        header: t('name', { defaultValue: 'Name' }),
        width: '3fr',
        cell: template => (
          <div className="flex min-w-0 items-center gap-2">
            <span className={cn('h-2 w-2 shrink-0 rounded-full', template.is_disabled ? 'bg-red-500' : 'bg-green-500')} />
            <span className="truncate font-medium">{template.name}</span>
          </div>
        ),
      },
      {
        id: 'dataLimit',
        header: t('userDialog.dataLimit', { defaultValue: 'Data Limit' }),
        width: '1fr',
        cell: template => (
          <span dir="ltr" className="text-xs text-muted-foreground">
            {!template.data_limit || template.data_limit === 0 ? <Infinity className="inline h-4 w-4" /> : formatBytes(template.data_limit)}
          </span>
        ),
        hideOnMobile: true,
      },
      {
        id: 'expire',
        header: t('expire', { defaultValue: 'Expire' }),
        width: '1fr',
        cell: template => (
          <span className="text-xs text-muted-foreground">
            {!template.expire_duration || template.expire_duration === 0 ? (
              <Infinity className="inline h-4 w-4" />
            ) : (
              `${template.expire_duration / 60 / 60 / 24} ${t('dateInfo.day')}`
            )}
          </span>
        ),
        hideOnMobile: true,
      },
      {
        id: 'actions',
        header: '',
        width: '64px',
        align: 'end',
        hideOnMobile: true,
        cell: template => <UserTemplateActionsMenu template={template} onEdit={onEdit} onToggleStatus={onToggleStatus} />,
      },
    ],
    [t, onEdit, onToggleStatus],
  )
}
