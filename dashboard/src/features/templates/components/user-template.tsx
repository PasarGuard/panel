import { Card } from '@/components/ui/card'
import { Infinity } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'
import { formatBytes } from '@/utils/formatByte'
import { UserTemplateResponse } from '@/service/api'
import UserTemplateActionsMenu from './user-template-actions-menu'
import type { ReactNode } from 'react'

const UserTemplate = ({
  template,
  onEdit,
  onToggleStatus,
  canCreate = true,
  canUpdate = true,
  canDelete = true,
  selectionControl,
  selected = false,
}: {
  template: UserTemplateResponse
  onEdit: (userTemplate: UserTemplateResponse) => void
  onToggleStatus: (template: UserTemplateResponse) => void
  canCreate?: boolean
  canUpdate?: boolean
  canDelete?: boolean
  selectionControl?: ReactNode
  selected?: boolean
}) => {
  const { t } = useTranslation()
  const daysUnit = t('time.days', { defaultValue: 'days' })

  return (
    <Card
      className={cn('group relative h-full rounded-lg px-4 py-5 transition-colors', canUpdate && 'hover:bg-accent cursor-pointer', selected && 'border-primary/50 bg-accent/30')}
      onClick={() => {
        if (canUpdate) onEdit(template)
      }}
    >
      <div className="flex items-start gap-3">
        {selectionControl ? <div className="pt-1">{selectionControl}</div> : null}
        <div className="flex min-w-0 flex-1 items-start justify-between gap-2 sm:gap-3">
          <div className="min-w-0 flex-1">
            <div className="flex min-w-0 items-center gap-x-2">
              <div className={cn('min-h-2 min-w-2 shrink-0 rounded-full', template.is_disabled ? 'bg-red-500' : 'bg-green-500')} />
              <span className="truncate font-medium">{template.name}</span>
            </div>
            <div className="text-muted-foreground mt-2 flex flex-col gap-y-1 text-sm">
              <p className="flex items-center gap-x-1">
                {t('userDialog.dataLimit')}:{' '}
                <span dir="ltr">{!template.data_limit || template.data_limit === 0 ? <Infinity className="h-4 w-4" /> : formatBytes(template.data_limit ? template.data_limit : 0)}</span>
              </p>
              <p className="flex items-center gap-x-1">
                {t('templates.hwidLimit', { defaultValue: 'HWID Limit' })}:{' '}
                <span dir="ltr">
                  {template.hwid_limit === null || template.hwid_limit === undefined ? (
                    t('default', { defaultValue: 'Default' })
                  ) : template.hwid_limit === 0 ? (
                    <Infinity className="h-4 w-4" />
                  ) : (
                    template.hwid_limit
                  )}
                </span>
              </p>
              <p className="flex items-center gap-x-1">
                {t('expire')}:<span>{!template.expire_duration || template.expire_duration === 0 ? <Infinity className="h-4 w-4" /> : `${template.expire_duration / 60 / 60 / 24} ${daysUnit}`}</span>
              </p>
            </div>
          </div>
          <div onClick={event => event.stopPropagation()}>
            <UserTemplateActionsMenu template={template} onEdit={onEdit} onToggleStatus={onToggleStatus} canCreate={canCreate} canUpdate={canUpdate} canDelete={canDelete} />
          </div>
        </div>
      </div>
    </Card>
  )
}

export default UserTemplate
