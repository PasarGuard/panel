import { Card, CardDescription, CardTitle } from '../ui/card'
import { Infinity } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'
import { formatBytes } from '@/utils/formatByte'
import { UserTemplateResponse } from '@/service/api'
import UserTemplateActionsMenu from './user-template-actions-menu'

const UserTemplate = ({
  template,
  onEdit,
  onToggleStatus,
}: {
  template: UserTemplateResponse
  onEdit: (userTemplate: UserTemplateResponse) => void
  onToggleStatus: (template: UserTemplateResponse) => void
}) => {
  const { t } = useTranslation()

  return (
    <Card className="group rounded-lg px-5 py-6 transition-colors hover:bg-accent">
      <div className="flex items-center justify-between">
        <div className="flex-1 cursor-pointer" onClick={() => onEdit(template)}>
          <CardTitle className="flex items-center gap-x-2">
            <div className={cn('min-h-2 min-w-2 rounded-full', template.is_disabled ? 'bg-red-500' : 'bg-green-500')} />
            <span>{template.name}</span>
          </CardTitle>
          <CardDescription>
            <div className="mt-2 flex flex-col gap-y-1">
              <p className={'flex items-center gap-x-1'}>
                {t('userDialog.dataLimit')}:{' '}
                <span dir="ltr">{!template.data_limit || template.data_limit === 0 ? <Infinity className="h-4 w-4"></Infinity> : formatBytes(template.data_limit ? template.data_limit : 0)}</span>
              </p>
              <p className={'flex items-center gap-x-1'}>
                {t('expire')}:
                <span>
                  {!template.expire_duration || template.expire_duration === 0 ? <Infinity className="h-4 w-4"></Infinity> : `${template.expire_duration / 60 / 60 / 24} ${t('dateInfo.day')}`}
                </span>
              </p>
            </div>
          </CardDescription>
        </div>
        <UserTemplateActionsMenu template={template} onEdit={onEdit} onToggleStatus={onToggleStatus} />
      </div>
    </Card>
  )
}

export default UserTemplate
