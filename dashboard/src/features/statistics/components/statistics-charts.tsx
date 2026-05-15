import { Skeleton } from '@/components/ui/skeleton'
import { NodeRealtimeStats, NodeSimple, SystemStats, useRealtimeNodeStats } from '@/service/api'
import { useEffect, useState, useCallback, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { CostumeBarChart } from '@/components/charts/costume-bar-chart'
import { EmptyState } from '@/components/charts/empty-state'
import UserSubUpdatePieChart from '@/components/charts/user-sub-update-pie-chart'
import SystemStatisticsSection from './system-statistics-section'
import { AllNodesStackedBarChart } from '@/components/charts/all-nodes-stacked-bar-chart'
import { AreaCostumeChart } from '@/components/charts/area-costume-chart'
import { BarChart3 } from 'lucide-react'
import { UserCountsChart } from '@/components/charts/user-counts-chart'

interface StatisticsChartsProps {
  data?: SystemStats
  isLoading: boolean
  error?: { message?: string } | null
  selectedServer: string
  is_sudo: boolean
  nodesData?: NodeSimple[]
  isLoadingNodes?: boolean
}

export default function StatisticsCharts({ data, isLoading, error, selectedServer, is_sudo, nodesData = [], isLoadingNodes = false }: StatisticsChartsProps) {
  const { t } = useTranslation()

  // Add state for chart refresh
  const [chartRefreshKey, setChartRefreshKey] = useState(0)
  const resizeTimeoutRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  const lastWindowWidthRef = useRef<number>(typeof window !== 'undefined' ? window.innerWidth : 0)

  // For non-sudo admins, selectedServer should always be 'master'
  const actualSelectedServer = is_sudo ? selectedServer : 'master'
  const selectedNodeId = actualSelectedServer === 'master' ? undefined : parseInt(actualSelectedServer, 10)
  const selectedNode = selectedNodeId !== undefined ? nodesData.find(node => node.id === selectedNodeId) : undefined
  const selectedNodeConnected = selectedNode?.status === 'connected'
  const shouldFetchNodeRealtime = is_sudo && !!selectedNodeId && selectedNodeConnected

  // Only fetch realtime node stats for connected nodes.
  const { data: nodeStats, isLoading: isLoadingNodeStats } = useRealtimeNodeStats(selectedNodeId || 0, {
    query: {
      enabled: shouldFetchNodeRealtime,
      refetchInterval: 1500, // Update every 1.5 seconds for faster realtime updates
      staleTime: 1000, // Consider data stale after 1 second
    },
  })

  // Handle resize events to refresh charts
  const handleResize = useCallback(() => {
    const currentWidth = window.innerWidth
    if (currentWidth === lastWindowWidthRef.current) {
      return
    }

    lastWindowWidthRef.current = currentWidth

    if (resizeTimeoutRef.current) {
      clearTimeout(resizeTimeoutRef.current)
    }
    resizeTimeoutRef.current = setTimeout(() => {
      setChartRefreshKey(k => k + 1)
    }, 100) // Debounce resize events
  }, [])

  // Listen for window resize events
  useEffect(() => {
    window.addEventListener('resize', handleResize)

    // Listen for sidebar toggle events
    const handleSidebarToggle = () => {
      setTimeout(() => setChartRefreshKey(k => k + 1), 300) // Wait for animation to complete
    }
    window.addEventListener('sidebar-toggle', handleSidebarToggle)

    return () => {
      window.removeEventListener('resize', handleResize)
      window.removeEventListener('sidebar-toggle', handleSidebarToggle)
      if (resizeTimeoutRef.current) {
        clearTimeout(resizeTimeoutRef.current)
      }
    }
  }, [handleResize])

  // Clear any existing intervals when server selection changes
  useEffect(() => {
    return () => {
      // This cleanup function will run when the component unmounts or when selectedServer changes
      // The query will be automatically disabled when selectedServer changes due to the enabled option
    }
  }, [selectedServer])

  if ((actualSelectedServer === 'master' && isLoading) || (is_sudo && isLoadingNodes) || (shouldFetchNodeRealtime && isLoadingNodeStats)) {
    return <StatisticsSkeletons is_sudo={is_sudo} />
  }

  if (error) {
    return (
      <div className="space-y-8">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <BarChart3 className="text-primary h-5 w-5" />
            <h2 className="text-lg font-semibold">{t('statistics.system')}</h2>
          </div>
        </div>
        <EmptyState type="error" title={t('errors.statisticsLoadFailed')} description={error?.message || t('errors.connectionFailed')} className="min-h-[400px]" />
      </div>
    )
  }

  // Get the current stats based on selection
  const currentStats = actualSelectedServer === 'master' ? (data as SystemStats) : selectedNodeConnected ? (nodeStats as NodeRealtimeStats) : null
  const showRealtimeSystemStats = actualSelectedServer === 'master' || selectedNodeConnected

  return (
    <div className="space-y-8">
      {/* System Statistics Section - show for all admins */}
      {showRealtimeSystemStats && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <BarChart3 className="text-primary h-5 w-5" />
              <h2 className="text-lg font-semibold">{t('statistics.system')}</h2>
            </div>
          </div>
          <div className="animate-slide-up transform-gpu" style={{ animationDuration: '500ms', animationDelay: '100ms', animationFillMode: 'both' }}>
            <SystemStatisticsSection currentStats={currentStats} />
          </div>
        </div>
      )}

      {/* Charts Section */}
      <div className="space-y-8">
        {is_sudo && (
          <div className="animate-slide-up transform-gpu" style={{ animationDuration: '500ms', animationDelay: '260ms', animationFillMode: 'both' }}>
            {actualSelectedServer === 'master' ? <AllNodesStackedBarChart /> : <CostumeBarChart nodeId={selectedNodeId} />}
          </div>
        )}
        <div className="animate-slide-up transform-gpu" style={{ animationDuration: '500ms', animationDelay: '300ms', animationFillMode: 'both' }}>
          <UserCountsChart nodeId={selectedNodeId} isSudo={is_sudo} nodesData={nodesData} />
        </div>
        {actualSelectedServer === 'master' && (
          <div className="animate-slide-up transform-gpu" style={{ animationDuration: '500ms', animationDelay: '310ms', animationFillMode: 'both' }}>
            <UserSubUpdatePieChart />
          </div>
        )}
        <div className="animate-slide-up transform-gpu" style={{ animationDuration: '500ms', animationDelay: '320ms', animationFillMode: 'both' }}>
          <AreaCostumeChart
            key={chartRefreshKey}
            nodeId={selectedNodeId}
            currentStats={currentStats}
            realtimeStats={actualSelectedServer === 'master' ? data : selectedNodeConnected ? nodeStats || undefined : undefined}
            realtimeAvailable={actualSelectedServer === 'master' || selectedNodeConnected}
          />
        </div>
      </div>
    </div>
  )
}

function StatisticsSkeletons({ is_sudo }: { is_sudo: boolean }) {
  return (
    <div className="space-y-8">
      {/* System Stats Skeleton - show for all admins */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <Skeleton className="mb-2 h-6 w-[150px]" />
            <Skeleton className="h-4 w-[200px]" />
          </div>
        </div>
        <div className="flex flex-col items-center justify-between gap-x-4 gap-y-4 lg:flex-row">
          {[1, 2, 3].map(i => (
            <div key={i} className="w-full">
              <div className="group relative w-full overflow-hidden rounded-lg border p-6">
                <div className="flex items-center gap-3">
                  <Skeleton className="h-9 w-9 rounded-lg" />
                  <div>
                    <Skeleton className="mb-2 h-4 w-[100px]" />
                    <Skeleton className="h-8 w-[120px]" />
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Charts Skeleton - only show for sudo admins */}
      {is_sudo && (
        <div className="space-y-8">
          <Skeleton className="h-[400px] w-full" />
          <Skeleton className="h-[360px] w-full" />
        </div>
      )}
    </div>
  )
}
