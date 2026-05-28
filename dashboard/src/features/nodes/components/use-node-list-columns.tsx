import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { ListColumn } from '@/components/common/list-generator'
import NodeUsageDisplay from '@/features/nodes/components/node-usage-display'
import NodeActionsMenu from '@/features/nodes/components/node-actions-menu'
import { CoresSimpleResponse, NodeResponse, NodeStatus } from '@/service/api'
import { cn } from '@/lib/utils'
import { Package, Server } from 'lucide-react'

interface UseNodeListColumnsProps {
  onEdit: (node: NodeResponse) => void
  onToggleStatus: (node: NodeResponse) => Promise<void>
  coresData?: CoresSimpleResponse
  canUpdate?: boolean
  canDelete?: boolean
  canReconnect?: boolean
  canUpdateCore?: boolean
  canReadStats?: boolean
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

export const useNodeListColumns = ({ onEdit, onToggleStatus, coresData, canUpdate = true, canDelete = true, canReconnect = true, canUpdateCore = true, canReadStats = true }: UseNodeListColumnsProps) => {
  const { t } = useTranslation()

  return useMemo<ListColumn<NodeResponse>[]>(
    () => [
      {
        id: 'name',
        header: t('name'),
        width: '3fr',
        cell: node => (
          <div className="flex min-w-0 items-center gap-2">
            <span className={cn('h-2 w-2 shrink-0 rounded-full', getNodeStatusDotColor(node.status))} />
            <span className="truncate font-medium">{node.name}</span>
          </div>
        ),
      },
      {
        id: 'address',
        header: t('address'),
        width: '2fr',
        cell: node => (
          <div dir="ltr" className="text-muted-foreground truncate font-mono text-xs">
            {node.address}:{node.port}
          </div>
        ),
        hideOnMobile: true,
      },
      {
        id: 'version',
        header: t('version.title', { defaultValue: 'Version' }),
        width: '2fr',
        cell: node => {
          if (!node.xray_version && !node.node_version) return null
          return (
            <div className="text-muted-foreground flex flex-col gap-1 text-xs">
              {node.xray_version && (
                <div className="flex items-center gap-1.5">
                  <Server className="h-3.5 w-3.5 shrink-0" />
                  <span className="truncate">{node.xray_version}</span>
                </div>
              )}
              {node.node_version && (
                <div className="flex items-center gap-1.5">
                  <Package className="h-3.5 w-3.5 shrink-0" />
                  <span className="truncate">{node.node_version}</span>
                </div>
              )}
            </div>
          )
        },
        hideOnMobile: true,
      },
      {
        id: 'usage',
        header: t('usageLabel'),
        width: '2fr',
        cell: node => <NodeUsageDisplay node={node} />,
        hideOnMobile: true,
      },
      ...(canUpdate || canDelete || canReconnect || canUpdateCore || canReadStats
        ? [
          {
            id: 'actions',
            header: '',
            width: '64px',
            align: 'end' as const,
            hideOnMobile: true,
            cell: (node: NodeResponse) => (
              <NodeActionsMenu
                node={node}
                onEdit={onEdit}
                onToggleStatus={onToggleStatus}
                coresData={coresData}
                isModalHost={false}
                canUpdate={canUpdate}
                canDelete={canDelete}
                canReconnect={canReconnect}
                canUpdateCore={canUpdateCore}
                canReadStats={canReadStats}
              />
            ),
          },
        ]
        : []),
    ],
    [t, onEdit, onToggleStatus, coresData, canUpdate, canDelete, canReconnect, canUpdateCore, canReadStats],
  )
}
