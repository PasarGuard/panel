import PageHeader from '@/components/layout/page-header'
import MainContent from '@/features/statistics/components/statistics-charts'
import { Separator } from '@/components/ui/separator'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useGetSystemResourceStats, useGetSystemUsersStats, useGetNodesSimple, NodeSimple, NodeStatus } from '@/service/api'
import { cn } from '@/lib/utils'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Skeleton } from '@/components/ui/skeleton'
import { Card, CardContent } from '@/components/ui/card'
import { useAdmin } from '@/hooks/use-admin'
import { hasPermission } from '@/utils/rbac'

const Statistics = () => {
  const { t } = useTranslation()
  const [selectedServer, setSelectedServer] = useState<string>('master')
  const { admin } = useAdmin()
  const canViewNodeStats = hasPermission(admin, 'nodes', 'stats')
  const canViewSystemStats = hasPermission(admin, 'system', 'read')

  // Fetch nodes for the selector
  const { data: nodesResponse, isLoading: isLoadingNodes } = useGetNodesSimple(
    { all: true },
    {
      query: {
        enabled: canViewNodeStats,
      },
    },
  )

  // Extract nodes array from response
  const nodesData = nodesResponse?.nodes || []

  useEffect(() => {
    if (canViewSystemStats || selectedServer !== 'master') return

    const firstNode = nodesData[0]
    if (firstNode) {
      setSelectedServer(String(firstNode.id))
    }
  }, [canViewSystemStats, nodesData, selectedServer])

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

  const {
    data: resourceData,
    error,
    isLoading,
  } = useGetSystemResourceStats({
    query: {
      enabled: canViewSystemStats && selectedServer === 'master',
      refetchInterval: canViewSystemStats && selectedServer === 'master' ? 2000 : false,
      staleTime: 1000,
      refetchOnWindowFocus: true,
    },
  })

  const { data: usersData } = useGetSystemUsersStats(undefined, {
    query: {
      enabled: canViewSystemStats && selectedServer === 'master',
      refetchInterval: canViewSystemStats && selectedServer === 'master' ? 2000 : false,
      staleTime: 1000,
      refetchOnWindowFocus: true,
    },
  })

  return (
    <div className="flex w-full flex-col items-start gap-2">
      <div className="animate-fade-in w-full transform-gpu" style={{ animationDuration: '400ms' }}>
        <PageHeader title="statistics" description="monitorServers" />
        <Separator />
      </div>

      {canViewNodeStats && (canViewSystemStats || nodesData.length > 0) && (
        <div className="w-full px-3 pt-2 sm:px-4 sm:pt-4">
          <div className="animate-slide-up transform-gpu" style={{ animationDuration: '500ms', animationDelay: '50ms', animationFillMode: 'both' }}>
            <Card>
              <CardContent className="p-4 sm:p-6">
                <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center sm:gap-4">
                  <div className="min-w-0 flex-1">
                    <h3 className="truncate text-base font-semibold sm:text-lg">{t('nodes.title')}</h3>
                    <p className="text-muted-foreground text-xs leading-relaxed sm:text-sm">{t('statistics.selectNodeToView')}</p>
                  </div>
                  <div className="w-full sm:w-auto sm:min-w-[180px] lg:min-w-[200px]">
                    {isLoadingNodes ? (
                      <Skeleton className="h-9 w-full sm:h-10" />
                    ) : (
                      <Select value={selectedServer} onValueChange={setSelectedServer}>
                        <SelectTrigger className="h-9 w-full text-xs sm:h-10 sm:text-sm">
                          <SelectValue placeholder={t('selectServer')} />
                        </SelectTrigger>
                        <SelectContent>
                          {canViewSystemStats && (
                            <SelectItem value="master" className="text-xs sm:text-sm">
                              {t('master')}
                            </SelectItem>
                          )}
                          {nodesData.map((node: NodeSimple) => (
                            <SelectItem key={node.id} value={String(node.id)} className="text-xs sm:text-sm">
                              <span className="flex min-w-0 items-center gap-2">
                                <span className={cn('h-1.5 w-1.5 shrink-0 rounded-full', getNodeStatusDotColor(node.status))} />
                                <span className="min-w-0 truncate">{node.name}</span>
                              </span>
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
      )}

      <div className="w-full">
        <div className="w-full px-3 pt-2 sm:px-4">
          <div className="animate-slide-up transform-gpu" style={{ animationDuration: '500ms', animationDelay: '100ms', animationFillMode: 'both' }}>
            <Card>
              <CardContent className="p-4 sm:p-6">
                <MainContent
                  error={error}
                  isLoading={isLoading}
                  data={resourceData}
                  usersData={usersData}
                  selectedServer={selectedServer}
                  canViewNodeStats={canViewNodeStats}
                  canViewSystemStats={canViewSystemStats}
                  nodesData={nodesData}
                  isLoadingNodes={isLoadingNodes}
                />
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    </div>
  )
}

export default Statistics
