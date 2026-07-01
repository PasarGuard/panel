import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { ListColumn } from '@/components/common/list-generator'
import { BaseHost } from '@/service/api'
import { cn } from '@/lib/utils'
import HostActionsMenu from '@/features/hosts/components/host-actions-menu'
import { TagChip } from '@/features/hosts/components/host-tag-picker'
import { Settings } from 'lucide-react'

interface UseHostsListColumnsProps {
  onEdit: (host: BaseHost) => void
  onDuplicate: (host: BaseHost) => Promise<void>
  onDataChanged: () => void
  canUpdate?: boolean
  canCreate?: boolean
}

export const useHostsListColumns = ({ onEdit, onDuplicate, onDataChanged, canUpdate = true, canCreate = true }: UseHostsListColumnsProps) => {
  const { t } = useTranslation()

  return useMemo<ListColumn<BaseHost>[]>(
    () => [
      {
        id: 'remark',
        header: t('name'),
        width: '3fr',
        cell: host => (
          <div className="flex min-w-0 items-center gap-2">
            <span className={cn('h-2 w-2 shrink-0 rounded-full', host.is_disabled ? 'bg-red-500' : 'bg-green-500')} />
            <span className="truncate font-medium">{host.remark ?? ''}</span>
          </div>
        ),
      },
      {
        id: 'address',
        header: t('address'),
        width: '1fr',
        cell: host => (
          <span dir="ltr" className="text-muted-foreground truncate font-mono text-xs">
            {Array.isArray(host.address) ? host.address[0] || '' : (host.address ?? '')}:{host.port === null ? <Settings className="inline h-3 w-3" /> : host.port}
          </span>
        ),
        hideOnMobile: true,
      },
      {
        id: 'inbound',
        header: t('inbound'),
        width: '1fr',
        cell: host => <span className="text-muted-foreground truncate text-xs">{host.inbound_tag ?? ''}</span>,
        hideOnMobile: true,
      },
      {
        id: 'tags',
        header: t('hostTags.label', { defaultValue: 'Tags' }),
        width: '1.5fr',
        cell: host =>
          host.tags && host.tags.length > 0 ? (
            <div className="flex min-w-0 flex-wrap items-center gap-1">
              {host.tags.map(tag => (
                <TagChip key={tag.id ?? tag.name} tag={tag} />
              ))}
            </div>
          ) : null,
        hideOnMobile: true,
      },
      ...(canUpdate || canCreate
        ? [
            {
              id: 'actions',
              header: '',
              width: '64px',
              align: 'end' as const,
              hideOnMobile: true,
              cell: (host: BaseHost) => <HostActionsMenu host={host} onEdit={onEdit} onDuplicate={onDuplicate} onDataChanged={onDataChanged} canUpdate={canUpdate} canCreate={canCreate} />,
            },
          ]
        : []),
    ],
    [t, onEdit, onDuplicate, onDataChanged, canUpdate, canCreate],
  )
}
