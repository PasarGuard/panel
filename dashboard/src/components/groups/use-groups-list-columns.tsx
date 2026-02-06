import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { ListColumn } from '@/components/common/list-generator'
import { GroupResponse } from '@/service/api'
import { cn } from '@/lib/utils'
import GroupActionsMenu from '@/components/groups/group-actions-menu'

interface UseGroupsListColumnsProps {
  onEdit: (group: GroupResponse) => void
  onToggleStatus: (group: GroupResponse) => Promise<void>
}

export const useGroupsListColumns = ({ onEdit, onToggleStatus }: UseGroupsListColumnsProps) => {
  const { t } = useTranslation()

  return useMemo<ListColumn<GroupResponse>[]>(
    () => [
      {
        id: 'name',
        header: t('name', { defaultValue: 'Name' }),
        width: '3fr',
        cell: group => (
          <div className="flex min-w-0 items-center gap-2">
            <span className={cn('h-2 w-2 shrink-0 rounded-full', group.is_disabled ? 'bg-red-500' : 'bg-green-500')} />
            <span className="truncate font-medium">{group.name}</span>
          </div>
        ),
      },
      {
        id: 'inbounds',
        header: t('inbounds', { defaultValue: 'Inbounds' }),
        width: '1fr',
        cell: group => <span className="truncate text-xs text-muted-foreground">{group.inbound_tags?.length || 0}</span>,
        hideOnMobile: true,
      },
      {
        id: 'users',
        header: t('admins.total.users'),
        width: '1fr',
        cell: group => <span className="truncate text-xs text-muted-foreground">{group.total_users || 0}</span>,
        hideOnMobile: true,
      },
      {
        id: 'actions',
        header: '',
        width: '64px',
        align: 'end',
        hideOnMobile: true,
        cell: group => <GroupActionsMenu group={group} onEdit={onEdit} onToggleStatus={onToggleStatus} />,
      },
    ],
    [t, onEdit, onToggleStatus],
  )
}
