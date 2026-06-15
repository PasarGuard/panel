import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { Infinity } from 'lucide-react'
import { ListColumn } from '@/components/common/list-generator'
import { UserTemplateResponse } from '@/service/api'
import UserTemplateActionsMenu from '@/features/templates/components/user-template-actions-menu'
import { formatBytes } from '@/utils/formatByte'
import { cn } from '@/lib/utils'

interface UseUserTemplatesListColumnsProps {
  onEdit: (template: UserTemplateResponse) => void
  onToggleStatus: (template: UserTemplateResponse) => void
  canCreate?: boolean
  canUpdate?: boolean
  canDelete?: boolean
}

export const useUserTemplatesListColumns = ({ onEdit, onToggleStatus, canCreate = true, canUpdate = true, canDelete = true }: UseUserTemplatesListColumnsProps) => {
  const { t } = useTranslation()

  return useMemo<ListColumn<UserTemplateResponse>[]>(
    () => [
      {
        id: 'name',
        header: t('name', { defaultValue: 'Name' }),
        width: '3fr',
        cell: template => (
          <div
            className={cn('flex min-w-0 items-center gap-2', canUpdate && 'cursor-pointer')}
            onClick={event => {
              event.stopPropagation()
              if (canUpdate) onEdit(template)
            }}
          >
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
          <span dir="ltr" className="text-muted-foreground text-xs">
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
          <span className="text-muted-foreground text-xs">
            {!template.expire_duration || template.expire_duration === 0 ? (
              <Infinity className="inline h-4 w-4" />
            ) : (
              `${template.expire_duration / 60 / 60 / 24} ${t('time.days', { defaultValue: 'days' })}`
            )}
          </span>
        ),
        hideOnMobile: true,
      },
      {
        id: 'hwidLimit',
        header: t('templates.hwidLimit', { defaultValue: 'HWID' }),
        width: '1fr',
        cell: template => (
          <span dir="ltr" className="text-muted-foreground text-xs">
            {template.hwid_limit === null || template.hwid_limit === undefined ? (
              t('default', { defaultValue: 'Default' })
            ) : template.hwid_limit === 0 ? (
              <Infinity className="inline h-4 w-4" />
            ) : (
              template.hwid_limit
            )}
          </span>
        ),
        hideOnMobile: true,
      },
      ...(canCreate || canUpdate || canDelete
        ? [
            {
              id: 'actions',
              header: '',
              width: '64px',
              align: 'end' as const,
              hideOnMobile: true,
              cell: (template: UserTemplateResponse) => (
                <UserTemplateActionsMenu template={template} onEdit={onEdit} onToggleStatus={onToggleStatus} canCreate={canCreate} canUpdate={canUpdate} canDelete={canDelete} />
              ),
            },
          ]
        : []),
    ],
    [t, onEdit, onToggleStatus, canCreate, canUpdate, canDelete],
  )
}
