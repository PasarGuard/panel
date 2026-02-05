import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { ListColumn } from '@/components/common/list-generator'
import { BaseHost } from '@/service/api'
import { cn } from '@/lib/utils'
import HostActionsMenu from '@/components/hosts/host-actions-menu'

interface UseHostsListColumnsProps {
  onEdit: (host: BaseHost) => void
  onDuplicate: (host: BaseHost) => void
  onDataChanged: () => void
}

export const useHostsListColumns = ({ onEdit, onDuplicate, onDataChanged }: UseHostsListColumnsProps) => {
  const { t } = useTranslation()

  return useMemo<ListColumn<BaseHost>[]>(
    () => [
      {
        id: 'remark',
        header: t('name', { defaultValue: 'Name' }),
        width: '2fr',
        cell: host => (
          <div className="flex min-w-0 items-center gap-2">
            <span className={cn('h-2 w-2 shrink-0 rounded-full', host.is_disabled ? 'bg-red-500' : 'bg-green-500')} />
            <span className="truncate font-medium">{host.remark ?? ''}</span>
          </div>
        ),
      },
      {
        id: 'address',
        header: t('address', { defaultValue: 'Address' }),
        width: '2fr',
        cell: host => (
          <span dir="ltr" className="truncate font-mono text-xs text-muted-foreground">
            {Array.isArray(host.address) ? host.address[0] || '' : (host.address ?? '')}:{host.port === null ? 'auto' : host.port}
          </span>
        ),
        hideOnMobile: true,
      },
      {
        id: 'inbound',
        header: t('inbound', { defaultValue: 'Inbound' }),
        width: '1.5fr',
        cell: host => <span className="truncate text-xs text-muted-foreground">{host.inbound_tag ?? ''}</span>,
        hideOnMobile: true,
      },
      {
        id: 'actions',
        header: '',
        width: '64px',
        align: 'end',
        hideOnMobile: true,
        cell: host => <HostActionsMenu host={host} onEdit={onEdit} onDuplicate={onDuplicate} onDataChanged={onDataChanged} />,
      },
    ],
    [t, onEdit, onDuplicate, onDataChanged],
  )
}
