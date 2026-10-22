import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { DateRange } from 'react-day-picker'
import { Calendar, Users } from 'lucide-react'
import { useTheme } from '@/app/providers/theme-provider'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { EmptyState } from '@/components/charts/empty-state'
import TimeSelector, { TRAFFIC_TIME_SELECTOR_SHORTCUTS } from '@/components/charts/time-selector'
import AdminFilterCombobox from '@/components/common/admin-filter-combobox'
import { TimeRangeSelector } from '@/components/common/time-range-selector'
import { statusColors } from '@/constants/UserSettings'
import { StatusBadge } from '@/features/users/components/status-badge'
import UsageModal from '@/features/users/dialogs/usage-modal.lazy'
import { useAdmin } from '@/hooks/use-admin'
import useDirDetection from '@/hooks/use-dir-detection'
import dayjs from '@/lib/dayjs'
import { cn } from '@/lib/utils'
import { type NodeSimple, Period, type UserUsageTotal, useGetUsersUsageTotals } from '@/service/api'
import { getChartSeriesColor } from '@/utils/chart-colors'
import { getChartQueryRangeFromDateRange, getChartQueryRangeFromShortcut, TrafficShortcutKey } from '@/utils/chart-period-utils'
import { formatBytes } from '@/utils/formatByte'
import { hasPermission, hasScopeAll } from '@/utils/rbac'

const LIMIT_STEP = 10
const MAX_LIMIT = 100
const MAX_TOOLTIP_NODES = 6
const UNKNOWN_NODE_KEY = 'unknown'
const UNKNOWN_NODE_COLOR = 'hsl(var(--muted-foreground))'
const FALLBACK_COLOR = 'hsl(var(--chart-1))'
const ROW_GRID = 'grid grid-cols-[2rem_minmax(0,1fr)_auto] items-center gap-x-2 gap-y-1.5 px-2 py-2 sm:grid-cols-[2rem_12rem_minmax(0,1fr)_9rem] sm:gap-x-3'

type BarSegment = {
  key: string
  name: string
  color: string
  bytes: number
}

type UserRow = {
  user: UserUsageTotal
  segments: BarSegment[]
  isSplit: boolean
}

interface UsersTrafficCardProps {
  nodeId?: number
  nodesData?: NodeSimple[]
}

const formatShare = (part: number, whole: number) => (whole > 0 ? ((part / whole) * 100).toFixed(1) : '0.0')

export function UsersTrafficCard({ nodeId, nodesData = [] }: UsersTrafficCardProps) {
  const { t } = useTranslation()
  const dir = useDirDetection()
  const { resolvedTheme } = useTheme()
  const isDark = resolvedTheme === 'dark'
  const { admin } = useAdmin()
  const canFilterByAdmin = hasScopeAll(admin, 'users', 'read') && hasPermission(admin, 'admins', 'read_simple')
  const [selectedTime, setSelectedTime] = useState<TrafficShortcutKey>('1w')
  const [showCustomRange, setShowCustomRange] = useState(false)
  const [customRange, setCustomRange] = useState<DateRange | undefined>(undefined)
  const [selectedAdmin, setSelectedAdmin] = useState('all')
  const [limit, setLimit] = useState(LIMIT_STEP)
  const [prevNodeId, setPrevNodeId] = useState(nodeId)
  const [usageUserId, setUsageUserId] = useState<number | null>(null)
  const [isUsageOpen, setUsageOpen] = useState(false)

  if (prevNodeId !== nodeId) {
    setPrevNodeId(nodeId)
    setLimit(LIMIT_STEP)
  }

  const wholeDayRange = useMemo(
    () => (showCustomRange && customRange?.from && customRange?.to ? { from: dayjs(customRange.from).startOf('day').toDate(), to: dayjs(customRange.to).endOf('day').toDate() } : undefined),
    [showCustomRange, customRange],
  )

  const queryRange = useMemo(
    () =>
      wholeDayRange
        ? getChartQueryRangeFromDateRange(wholeDayRange, selectedTime, { periodOverride: Period.hour })
        : getChartQueryRangeFromShortcut(selectedTime, new Date(), { periodOverride: Period.hour }),
    [wholeDayRange, selectedTime],
  )

  const { data, isLoading, isPlaceholderData, error } = useGetUsersUsageTotals(
    {
      start: queryRange.startDate,
      end: queryRange.endDate,
      node_id: nodeId,
      admin: canFilterByAdmin && selectedAdmin !== 'all' ? [selectedAdmin] : undefined,
      group_by_node: nodeId === undefined,
      limit,
    },
    {
      query: {
        refetchInterval: 1000 * 60 * 5,
        placeholderData: previousData => previousData,
      },
    },
  )

  const rows = useMemo<UserRow[]>(() => {
    const users: UserUsageTotal[] = data?.users ?? []
    const nodeIndexById = new Map(nodesData.map((node, index) => [node.id, index]))
    const selectedNodeIndex = nodeId === undefined ? undefined : nodeIndexById.get(nodeId)
    const singleColor = selectedNodeIndex === undefined ? FALLBACK_COLOR : getChartSeriesColor(selectedNodeIndex, isDark)

    return users.map(user => {
      if (!user.nodes || nodesData.length === 0) {
        return { user, isSplit: false, segments: [{ key: 'total', name: '', color: singleColor, bytes: user.total_traffic }] }
      }

      const segments: BarSegment[] = user.nodes
        .flatMap(usage => {
          const index = nodeIndexById.get(usage.node_id)
          return index === undefined || usage.total_traffic <= 0 ? [] : [{ index, usage }]
        })
        .sort((a, b) => a.index - b.index)
        .map(({ index, usage }) => ({ key: String(usage.node_id), name: nodesData[index].name, color: getChartSeriesColor(index, isDark), bytes: usage.total_traffic }))
      const unknownBytes = user.nodes.filter(usage => !nodeIndexById.has(usage.node_id)).reduce((sum, usage) => sum + usage.total_traffic, 0)
      if (unknownBytes > 0) {
        segments.push({ key: UNKNOWN_NODE_KEY, name: t('statistics.usersTrafficUnknownNode', { defaultValue: 'Unknown node' }), color: UNKNOWN_NODE_COLOR, bytes: unknownBytes })
      }

      return { user, isSplit: true, segments }
    })
  }, [data, nodesData, nodeId, isDark, t])

  const legendItems = useMemo(() => {
    const present = new Map<string, BarSegment>()
    rows.forEach(row => {
      if (row.isSplit) row.segments.forEach(segment => present.set(segment.key, segment))
    })
    const nodeOrder = nodesData.map(node => String(node.id))
    const orderOf = (key: string) => (key === UNKNOWN_NODE_KEY ? Number.MAX_SAFE_INTEGER : nodeOrder.indexOf(key))
    return [...present.values()].sort((a, b) => orderOf(a.key) - orderOf(b.key))
  }, [rows, nodesData])

  const total = data?.total ?? 0
  const totalTraffic = data?.total_traffic ?? 0
  const topTraffic = rows[0]?.user.total_traffic ?? 0
  const loadedTraffic = rows.reduce((sum, row) => sum + row.user.total_traffic, 0)
  const remainingUsers = Math.max(0, total - rows.length)
  const remainingTraffic = Math.max(0, totalTraffic - loadedTraffic)
  const canShowMore = remainingUsers > 0 && rows.length < MAX_LIMIT

  const handleTimeSelect = (value: string) => {
    setSelectedTime(value as TrafficShortcutKey)
    setShowCustomRange(false)
    setCustomRange(undefined)
    setLimit(LIMIT_STEP)
  }

  const handleCustomRangeChange = (range: DateRange | undefined) => {
    setCustomRange(range)
    if (range?.from && range?.to) {
      setShowCustomRange(true)
      setLimit(LIMIT_STEP)
    }
  }

  const handleAdminChange = (username: string) => {
    setSelectedAdmin(username)
    setLimit(LIMIT_STEP)
  }

  const openUsage = (userId: number) => {
    setUsageUserId(userId)
    setUsageOpen(true)
  }

  const renderRow = ({ user, segments, isSplit }: UserRow, index: number) => {
    const traffic = formatBytes(user.total_traffic)
    const share = formatShare(user.total_traffic, totalTraffic)
    const isActive = user.status === 'active'
    const StatusIcon = statusColors[user.status]?.icon
    const tooltipSegments = [...segments].sort((a, b) => b.bytes - a.bytes)
    const hiddenNodes = Math.max(0, tooltipSegments.length - MAX_TOOLTIP_NODES)
    const barWidth = topTraffic > 0 ? (user.total_traffic / topTraffic) * 100 : 0

    return (
      <Tooltip key={user.user_id}>
        <TooltipTrigger asChild>
          <button
            type="button"
            disabled={isPlaceholderData}
            onClick={() => openUsage(user.user_id)}
            className={cn(ROW_GRID, 'hover:bg-muted/50 focus-visible:ring-ring w-full rounded-md text-start focus-visible:ring-2 focus-visible:outline-none disabled:pointer-events-none')}
          >
            <span className="text-muted-foreground col-start-1 row-start-1 text-sm tabular-nums">{index + 1}</span>
            <span className="col-start-2 row-start-1 flex min-w-0 items-center gap-1.5">
              <span dir="auto" className="truncate text-sm font-medium">
                {user.username}
              </span>
              {isActive || !StatusIcon ? null : (
                <span aria-hidden="true" className={cn('inline-flex shrink-0 items-center justify-center rounded-full p-0.5', statusColors[user.status]?.statusColor)}>
                  <StatusIcon className="h-3 w-3" />
                </span>
              )}
            </span>
            <span dir="ltr" className="col-start-3 row-start-1 justify-self-end text-sm whitespace-nowrap tabular-nums sm:col-start-4">
              {traffic}
              <span className="text-muted-foreground"> · {share}%</span>
            </span>
            <span aria-hidden="true" className="col-span-full row-start-2 min-w-0 sm:col-span-1 sm:col-start-3 sm:row-start-1">
              <span className="bg-background flex h-2.5 gap-px overflow-hidden rounded-[4px]" style={{ width: `${barWidth}%`, minWidth: 2 }}>
                {segments.map(segment => (
                  <span key={segment.key} className="h-full" style={{ flexGrow: segment.bytes, flexBasis: 0, minWidth: 2, backgroundColor: segment.color }} />
                ))}
              </span>
            </span>
          </button>
        </TooltipTrigger>
        <TooltipContent
          dir={dir}
          className="border-border bg-background text-foreground max-w-[280px] min-w-[120px] rounded border p-1.5 text-[10px] shadow sm:max-w-[300px] sm:min-w-[140px] sm:p-2 sm:text-xs"
        >
          <div className="mb-1 flex min-w-0 items-center gap-1.5 font-semibold">
            <span dir="auto" className="truncate">
              {user.username}
            </span>
            {isActive ? null : <StatusBadge status={user.status} />}
          </div>
          <div className="text-muted-foreground mb-1.5 flex items-center gap-1.5">
            <span>{t('statistics.totalUsage', { defaultValue: 'Total Usage' })}:</span>
            <span dir="ltr" className="font-mono">
              {traffic} · {share}%
            </span>
          </div>
          {isSplit ? (
            <div className="grid gap-1">
              {tooltipSegments.slice(0, MAX_TOOLTIP_NODES).map(segment => (
                <div key={segment.key} className="flex items-center justify-between gap-3">
                  <span className="flex min-w-0 items-center gap-1">
                    <span className="h-1.5 w-1.5 shrink-0 rounded-full sm:h-2 sm:w-2" style={{ backgroundColor: segment.color }} />
                    <span className="max-w-[120px] truncate">{segment.name}</span>
                  </span>
                  <span dir="ltr" className="text-muted-foreground font-mono">
                    {formatBytes(segment.bytes)} · {formatShare(segment.bytes, user.total_traffic)}%
                  </span>
                </div>
              ))}
              {hiddenNodes > 0 ? <div className="text-muted-foreground">{t('statistics.usersTrafficMoreNodes', { defaultValue: 'More nodes: {{count}}', count: hiddenNodes })}</div> : null}
            </div>
          ) : null}
        </TooltipContent>
      </Tooltip>
    )
  }

  const renderContent = () => {
    if (isLoading) {
      return (
        <div className="space-y-1">
          {Array.from({ length: LIMIT_STEP }, (_, index) => (
            <div key={index} className={ROW_GRID}>
              <Skeleton className="col-start-1 row-start-1 h-4 w-5" />
              <Skeleton className="col-start-2 row-start-1 h-4 w-24" />
              <Skeleton className="col-start-3 row-start-1 h-4 w-20 justify-self-end sm:col-start-4" />
              <Skeleton className="col-span-full row-start-2 h-2.5 w-full sm:col-span-1 sm:col-start-3 sm:row-start-1" />
            </div>
          ))}
        </div>
      )
    }

    if (error && !data) return <EmptyState type="error" className="max-h-[400px] min-h-[200px]" />

    if (!data || total === 0) {
      return (
        <EmptyState
          type="no-data"
          title={t('statistics.noDataInRange', { defaultValue: 'No Data in Selected Range' })}
          description={t('statistics.noDataInRangeDescription', { defaultValue: 'No traffic data found for the selected time period. Try selecting a different date range.' })}
          className="max-h-[400px] min-h-[200px]"
        />
      )
    }

    return (
      <>
        <TooltipProvider>
          <div className={cn('space-y-1 transition-opacity', isPlaceholderData && 'opacity-60')}>{rows.map(renderRow)}</div>
        </TooltipProvider>
        {legendItems.length > 0 ? (
          <div className="flex flex-wrap items-center justify-center gap-x-4 gap-y-2 pt-3">
            {legendItems.map(item => (
              <div key={item.key} className="flex items-center gap-1.5">
                <div className="h-2 w-2 shrink-0 rounded-[2px]" style={{ backgroundColor: item.color }} />
                <span className="text-xs whitespace-nowrap">{item.name}</span>
              </div>
            ))}
          </div>
        ) : null}
        {remainingUsers > 0 ? (
          <div className="flex flex-wrap items-center justify-between gap-2 pt-4">
            <span className="text-muted-foreground text-xs sm:text-sm">
              {t('statistics.usersTrafficRemaining', { defaultValue: 'Other users: {{count}}', count: remainingUsers })}
              {' · '}
              <span dir="ltr" style={{ unicodeBidi: 'isolate' }}>
                {formatBytes(remainingTraffic)} ({formatShare(remainingTraffic, totalTraffic)}%)
              </span>
            </span>
            {canShowMore ? (
              <Button variant="outline" size="sm" disabled={isPlaceholderData} onClick={() => setLimit(current => Math.min(current + LIMIT_STEP, MAX_LIMIT))}>
                {t('statistics.usersTrafficShowMore', { defaultValue: 'Show {{count}} more', count: Math.min(LIMIT_STEP, remainingUsers) })}
              </Button>
            ) : (
              <span className="text-muted-foreground text-xs sm:text-sm">{t('statistics.usersTrafficTopLimit', { defaultValue: 'Showing top {{count}}', count: rows.length })}</span>
            )}
          </div>
        ) : null}
      </>
    )
  }

  return (
    <>
      <Card>
        <CardHeader className="flex flex-col items-stretch space-y-0 border-b p-0 xl:flex-row">
          <div className="flex flex-1 flex-col gap-2 border-b px-4 py-3 xl:px-6 xl:py-4">
            <div className="flex min-w-0 flex-col justify-center gap-1 pt-2">
              <CardTitle className="mb-0.5 flex min-w-0 items-center gap-2">
                <Users className="text-muted-foreground h-4 w-4 shrink-0" />
                <span className="truncate">{t('statistics.usersTrafficTitle', { defaultValue: 'Traffic by Users' })}</span>
              </CardTitle>
              <CardDescription className="text-pretty">{t('statistics.usersTrafficDescription', { defaultValue: 'Who used the traffic in the selected period, split by node' })}</CardDescription>
            </div>
            <div className="flex w-full min-w-0 flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center">
              <TimeSelector selectedTime={selectedTime} setSelectedTime={handleTimeSelect} shortcuts={TRAFFIC_TIME_SELECTOR_SHORTCUTS} maxVisible={5} className="w-full sm:w-fit" />
              <div className="flex w-full items-center gap-2 sm:w-auto">
                {canFilterByAdmin ? <AdminFilterCombobox value={selectedAdmin} onValueChange={handleAdminChange} className="min-w-0 flex-1 sm:w-[220px] sm:flex-none" /> : null}
                <button
                  type="button"
                  aria-label={t('statistics.customRange', { defaultValue: 'Custom Range' })}
                  className={`inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-md border ${showCustomRange ? 'bg-muted' : ''}`}
                  onClick={() => {
                    const next = !showCustomRange
                    setShowCustomRange(next)
                    if (!next) {
                      setCustomRange(undefined)
                      setLimit(LIMIT_STEP)
                    }
                  }}
                >
                  <Calendar className="h-4 w-4" />
                </button>
              </div>
            </div>
            {showCustomRange ? (
              <div className="flex w-full">
                <TimeRangeSelector onRangeChange={handleCustomRangeChange} initialRange={customRange} className="w-full" />
              </div>
            ) : null}
          </div>
          <div className="m-0 flex flex-col justify-center p-4 xl:border-s xl:p-5 xl:px-6">
            <span className="text-muted-foreground text-xs sm:text-sm">{t('statistics.usageDuringPeriod', { defaultValue: 'Usage During Period' })}</span>
            <span dir="ltr" className="text-foreground flex items-center justify-center gap-2 text-lg">
              <Users className="text-muted-foreground h-4 w-4" />
              {isLoading ? <Skeleton className="h-5 w-20" /> : totalTraffic > 0 ? formatBytes(totalTraffic) : <span className="text-muted-foreground">—</span>}
            </span>
            {data && total > 0 ? <span className="text-muted-foreground text-center text-xs">{t('statistics.usersTrafficUsersCount', { defaultValue: 'Users: {{count}}', count: total })}</span> : null}
          </div>
        </CardHeader>
        <CardContent className="pt-6">{renderContent()}</CardContent>
      </Card>
      {usageUserId !== null ? (
        <UsageModal open={isUsageOpen} onClose={() => setUsageOpen(false)} userId={usageUserId} initialView={{ period: selectedTime, customRange: wholeDayRange, nodeId }} />
      ) : null}
    </>
  )
}
