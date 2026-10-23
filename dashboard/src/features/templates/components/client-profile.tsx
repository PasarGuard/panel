import { Card } from '@/components/ui/card'
import { ClientProfileResponse } from '@/service/api'
import ClientProfileActionsMenu from './client-profile-actions-menu'
import { cn } from '@/lib/utils'
import { Users } from 'lucide-react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

const ClientProfile = ({
  profile,
  onEdit,
  canCreate = true,
  canUpdate = true,
  canDelete = true,
  selectionControl,
  selected = false,
}: {
  profile: ClientProfileResponse
  onEdit: (profile: ClientProfileResponse) => void
  canCreate?: boolean
  canUpdate?: boolean
  canDelete?: boolean
  selectionControl?: ReactNode
  selected?: boolean
}) => {
  const { t } = useTranslation()

  return (
    <Card
      className={cn('group relative h-full px-4 py-5 transition-colors', canUpdate && 'hover:bg-accent cursor-pointer', selected && 'border-primary/50 bg-accent/30')}
      onClick={() => {
        if (canUpdate) onEdit(profile)
      }}
    >
      <div className="flex items-start gap-3">
        {selectionControl ? <div className="pt-1">{selectionControl}</div> : null}
        <div className="flex min-w-0 flex-1 items-start gap-3">
          <div className="min-w-0 flex-1">
            <div className="min-w-0 truncate font-medium">{profile.name}</div>
            <div className="text-muted-foreground flex min-w-0 items-center gap-1 text-sm">
              <Users className="h-3.5 w-3.5 shrink-0" />
              <span>{t('clientProfiles.usersCount', { count: profile.users_count ?? 0, defaultValue: '{{count}} users' })}</span>
            </div>
            {profile.note ? <div className="text-muted-foreground mt-1 line-clamp-2 text-xs">{profile.note}</div> : null}
          </div>
          <div onClick={event => event.stopPropagation()}>
            <ClientProfileActionsMenu profile={profile} onEdit={onEdit} canCreate={canCreate} canUpdate={canUpdate} canDelete={canDelete} />
          </div>
        </div>
      </div>
    </Card>
  )
}

export default ClientProfile
