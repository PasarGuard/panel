import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { ListColumn } from '@/components/common/list-generator'
import NodeUsageDisplay from '@/features/nodes/components/node-usage-display'
import NodeActionsMenu from '@/features/nodes/components/node-actions-menu'
import { CoresSimpleResponse, NodeResponse, NodeStatus } from '@/service/api'
import { cn } from '@/lib/utils'
import { Package, Server } from 'lucide-react'
import { useXrayReleases } from '@/hooks/use-xray-releases'
import { useNodeReleases } from '@/hooks/use-node-releases'
import { Separator } from '@/components/ui/separator'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'

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

export const useNodeListColumns = ({
  onEdit,
  onToggleStatus,
  coresData,
  canUpdate = true,
  canDelete = true,
  canReconnect = true,
  canUpdateCore = true,
  canReadStats = true,
}: UseNodeListColumnsProps) => {
  const { t } = useTranslation()
  const { latestVersion: latestXrayVersion, hasUpdate: hasXrayUpdate } = useXrayReleases()
  const { latestVersion: latestNodeVersion, hasUpdate: hasNodeUpdate } = useNodeReleases()

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
          const coreVersion = node.core_version ?? node.xray_version
          const resolvedCoreType = coresData?.cores?.find(c => c.id === node.core_config_id)?.type ?? null
          const isWireGuardCore = resolvedCoreType === 'wg'
          const isXrayBackend = resolvedCoreType !== 'wg'
          const coreUpdateVersion = node.xray_version ?? coreVersion
          const hasCoreUpdate = !!(isXrayBackend && coreUpdateVersion && latestXrayVersion && hasXrayUpdate(coreUpdateVersion))
          const hasNodeVersionUpdate = !isWireGuardCore && !!latestNodeVersion && !!node.node_version && hasNodeUpdate(node.node_version)

          if (!coreVersion && !node.node_version) return null

          return (
            <TooltipProvider>
              <div className="flex flex-col gap-1 text-xs">
                {coreVersion && (
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <div className="inline-flex min-w-0 items-center gap-1.5">
                        <Package className={cn('h-3.5 w-3.5 shrink-0 transition-colors', hasCoreUpdate ? 'text-amber-600 dark:text-amber-400' : 'text-muted-foreground')} />
                        <span className={cn('truncate font-mono font-medium', hasCoreUpdate ? 'text-amber-700 dark:text-amber-300' : 'text-muted-foreground')}>{coreVersion}</span>
                        {hasCoreUpdate && <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-amber-500" />}
                      </div>
                    </TooltipTrigger>
                    <TooltipContent side="top" className="max-w-xs">
                      <div className="space-y-2 text-xs">
                        <div className="font-semibold">{t('node.xrayVersion', { defaultValue: 'Core' })}</div>
                        <div className="space-y-1.5">
                          <div className="flex items-center justify-between gap-4">
                            <span>{t('version.currentVersion', { defaultValue: 'Current' })}</span>
                            <span className="font-mono font-medium">{coreVersion}</span>
                          </div>
                          {isXrayBackend && latestXrayVersion && (
                            <div className="flex items-center justify-between gap-4">
                              <span>{t('version.latestVersion', { defaultValue: 'Latest' })}</span>
                              <span className="font-mono font-medium">{latestXrayVersion}</span>
                            </div>
                          )}
                          {hasCoreUpdate && (
                            <>
                              <Separator className="my-1.5" />
                              <span>{t('nodeModal.updateAvailable', { defaultValue: 'Update available' })}</span>
                            </>
                          )}
                        </div>
                      </div>
                    </TooltipContent>
                  </Tooltip>
                )}
                {node.node_version && (
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <div className="inline-flex min-w-0 items-center gap-1.5">
                        <Server className={cn('h-3.5 w-3.5 shrink-0 transition-colors', hasNodeVersionUpdate ? 'text-amber-600 dark:text-amber-400' : 'text-muted-foreground')} />
                        <span className={cn('truncate font-mono font-medium', hasNodeVersionUpdate ? 'text-amber-700 dark:text-amber-300' : 'text-muted-foreground')}>{node.node_version}</span>
                        {hasNodeVersionUpdate && <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-amber-500" />}
                      </div>
                    </TooltipTrigger>
                    <TooltipContent side="top" className="max-w-xs">
                      <div className="space-y-2 text-xs">
                        <div className="font-semibold">{t('node.coreVersion', { defaultValue: 'Node Core' })}</div>
                        <div className="space-y-1.5">
                          <div className="flex items-center justify-between gap-4">
                            <span>{t('version.currentVersion', { defaultValue: 'Current' })}</span>
                            <span className="font-mono font-medium">{node.node_version}</span>
                          </div>
                          {!isWireGuardCore && latestNodeVersion && (
                            <div className="flex items-center justify-between gap-4">
                              <span>{t('version.latestVersion', { defaultValue: 'Latest' })}</span>
                              <span className="font-mono font-medium">{latestNodeVersion}</span>
                            </div>
                          )}
                          {hasNodeVersionUpdate && (
                            <>
                              <Separator className="my-1.5" />
                              <span>{t('nodeModal.updateAvailable', { defaultValue: 'Update available' })}</span>
                            </>
                          )}
                        </div>
                      </div>
                    </TooltipContent>
                  </Tooltip>
                )}
              </div>
            </TooltipProvider>
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
    [t, onEdit, onToggleStatus, coresData, canUpdate, canDelete, canReconnect, canUpdateCore, canReadStats, latestXrayVersion, hasXrayUpdate, latestNodeVersion, hasNodeUpdate],
  )
}
