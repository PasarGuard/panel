import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { ListColumn } from '@/components/common/list-generator'
import NodeUsageDisplay from '@/components/nodes/node-usage-display'
import NodeActionsMenu from '@/components/nodes/node-actions-menu'
import { NodeResponse, NodeStatus } from '@/service/api'
import { cn } from '@/lib/utils'

interface UseNodeListColumnsProps {
  onEdit: (node: NodeResponse) => void
  onToggleStatus: (node: NodeResponse) => void
}

const getNodeStatusDotColor = (status: NodeStatus) => {
  switch (status) {
    case 'connected':
      return 'bg-green-500'
    case 'connecting':
      return 'bg-amber-500'
    case 'error':
      return 'bg-destructive'
    case 'limited':
      return 'bg-orange-500'
    default:
      return 'bg-gray-400 dark:bg-gray-600'
  }
}

export const useNodeListColumns = ({ onEdit, onToggleStatus }: UseNodeListColumnsProps) => {
  const { t } = useTranslation()

  return useMemo<ListColumn<NodeResponse>[]>(
    () => [
      {
        id: 'name',
        header: t('name', { defaultValue: 'Name' }),
        width: '4fr',
        cell: node => (
          <div className="flex min-w-0 items-center gap-2">
            <span className={cn('h-2 w-2 shrink-0 rounded-full', getNodeStatusDotColor(node.status))} />
            <span className="truncate font-medium">{node.name}</span>
          </div>
        ),
      },
      {
        id: 'address',
        header: t('address', { defaultValue: 'Address' }),
        width: '1fr',
        cell: node => (
          <div dir="ltr" className="truncate font-mono text-xs text-muted-foreground">
            {node.address}:{node.port}
          </div>
        ),
        hideOnMobile: true,
      },
      {
        id: 'usage',
        header: t('usage', { defaultValue: 'Usage' }),
        width: '1fr',
        cell: node => <NodeUsageDisplay node={node} />,
        hideOnMobile: true,
      },
      {
        id: 'actions',
        header: '',
        width: '64px',
        align: 'end',
        hideOnMobile: true,
        cell: node => <NodeActionsMenu node={node} onEdit={onEdit} onToggleStatus={onToggleStatus} />,
      },
    ],
    [t, onEdit, onToggleStatus],
  )
}
