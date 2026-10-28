import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { ListColumn } from '@/components/common/list-generator'
import { ClientProfileResponse } from '@/service/api'
import ClientProfileActionsMenu from '@/features/templates/components/client-profile-actions-menu'
import { Badge } from '@/components/ui/badge'

interface UseClientProfilesListColumnsProps {
  onEdit: (profile: ClientProfileResponse) => void
  canCreate?: boolean
  canUpdate?: boolean
  canDelete?: boolean
}

export const useClientProfilesListColumns = ({ onEdit, canCreate = true, canUpdate = true, canDelete = true }: UseClientProfilesListColumnsProps) => {
  const { t } = useTranslation()
  const compactBadgeClassName = 'h-5 shrink-0 px-1.5 text-[10px] leading-none'

  return useMemo<ListColumn<ClientProfileResponse>[]>(
    () => [
      {
        id: 'name',
        header: t('name', { defaultValue: 'Name' }),
        width: '2fr',
        cell: profile => (
          <div
            className={`flex min-w-0 items-center gap-2 ${canUpdate ? 'cursor-pointer' : ''}`}
            onClick={event => {
              event.stopPropagation()
              if (canUpdate) onEdit(profile)
            }}
          >
            <span className="truncate font-medium">{profile.name}</span>
          </div>
        ),
      },
      {
        id: 'note',
        header: t('clientProfiles.note', { defaultValue: 'Note' }),
        width: '2fr',
        cell: profile => <span className="text-muted-foreground truncate text-xs">{profile.note || ''}</span>,
        hideOnMobile: true,
      },
      {
        id: 'users',
        header: t('clientProfiles.users', { defaultValue: 'Users' }),
        width: '1fr',
        cell: profile => (
          <Badge variant="secondary" className={compactBadgeClassName}>
            {profile.users_count ?? 0}
          </Badge>
        ),
      },
      ...(canCreate || canUpdate || canDelete
        ? [
            {
              id: 'actions',
              header: '',
              width: '24px',
              align: 'end' as const,
              hideOnMobile: false,
              cell: (profile: ClientProfileResponse) => <ClientProfileActionsMenu profile={profile} onEdit={onEdit} canCreate={canCreate} canUpdate={canUpdate} canDelete={canDelete} />,
            },
          ]
        : []),
    ],
    [compactBadgeClassName, t, onEdit, canCreate, canUpdate, canDelete],
  )
}
