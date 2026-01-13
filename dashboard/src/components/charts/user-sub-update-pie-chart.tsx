import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'
import { type ChartConfig, ChartContainer, ChartTooltip } from '@/components/ui/chart'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { Badge } from '@/components/ui/badge'
import useDirDetection from '@/hooks/use-dir-detection'
import { useTheme } from 'next-themes'
import { type GetUsersSubUpdateChartParams, useGetAdmins, useGetUsersSubUpdateChart, type UserSubscriptionUpdateChartSegment, type AdminDetails } from '@/service/api'
import { numberWithCommas } from '@/utils/formatByte'
import { TrendingUp, Users } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Cell, Pie, PieChart } from 'recharts'
import { ChartEmptyState } from './empty-state'

interface UserSubUpdatePieChartProps {
  username?: string
  adminId?: number
}

type SegmentWithColor = UserSubscriptionUpdateChartSegment & {
  key: string
  color: string
  count: number
  percentage: number
}

const buildSegmentKey = (name: string, index: number) => {
  const sanitized = (name || '')
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')

  return sanitized || `segment-${index}`
}

// Generate distinct colors for segments beyond the palette
const generateDistinctColor = (index: number, _totalNodes: number, isDark: boolean): string => {
  // Define a more distinct color palette with better contrast
  const distinctHues = [
    0, // Red
    30, // Orange
    60, // Yellow
    120, // Green
    180, // Cyan
    210, // Blue
    240, // Indigo
    270, // Purple
    300, // Magenta
    330, // Pink
    15, // Red-orange
    45, // Yellow-orange
    75, // Yellow-green
    150, // Green-cyan
    200, // Cyan-blue
    225, // Blue-indigo
    255, // Indigo-purple
    285, // Purple-magenta
    315, // Magenta-pink
    345, // Pink-red
  ]

  const hue = distinctHues[index % distinctHues.length]

  // Create more distinct saturation and lightness values
  const saturationVariations = [65, 75, 85, 70, 80, 60, 90, 55, 95, 50]
  const lightnessVariations = isDark ? [45, 55, 35, 50, 40, 60, 30, 65, 25, 70] : [40, 50, 30, 45, 35, 55, 25, 60, 20, 65]

  const saturation = saturationVariations[index % saturationVariations.length]
  const lightness = lightnessVariations[index % lightnessVariations.length]

  return `hsl(${hue}, ${saturation}%, ${lightness}%)`
}

// Custom tooltip component with shadcn styling
interface CustomTooltipProps {
  active?: boolean
  payload?: Array<{
    payload: {
      agent: string
      updates: number
      percentage: number
      fill: string
    }
  }>
  label?: string
}

function CustomTooltip({ active, payload }: CustomTooltipProps) {
  const { t } = useTranslation()

  if (!active || !payload || !payload.length) {
    return null
  }

  const data = payload[0].payload
  const { agent, updates, percentage, fill } = data

  return (
    <div className="rounded-lg border bg-background/95 p-3 shadow-lg backdrop-blur-sm">
      <div className="flex items-center gap-2">
        <div className="h-3 w-3 rounded-full border border-border/20" style={{ backgroundColor: fill }} />
        <span className="text-sm font-medium text-foreground">{agent}</span>
      </div>

      <div className="mt-2 space-y-1">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-1.5">
            <Users className="h-3 w-3 text-muted-foreground" />
            <span className="text-xs text-muted-foreground">{t('statistics.subscriptions')}</span>
          </div>
          <span className="font-mono text-sm font-semibold text-foreground">{numberWithCommas(updates)}</span>
        </div>

        <div className="flex items-center justify-between gap-3">
          <span className="text-xs text-muted-foreground">{t('statistics.percentage')}</span>
          <Badge variant="secondary" className="text-xs font-medium">
            {percentage.toFixed(1)}%
          </Badge>
        </div>
      </div>
    </div>
  )
}

function UserSubUpdatePieChart({ username, adminId }: UserSubUpdatePieChartProps) {
  const { t } = useTranslation()
  const dir = useDirDetection()
  const { resolvedTheme } = useTheme()
  const [selectedAdmin, setSelectedAdmin] = useState(() => (adminId != null ? String(adminId) : 'all'))
  const [selectedDays, setSelectedDays] = useState('all')

  useEffect(() => {
    if (adminId != null) {
      setSelectedAdmin(String(adminId))
    }
  }, [adminId])

  const { data: admins, isLoading: isLoadingAdmins } = useGetAdmins(undefined, {
    query: {
      enabled: true,
      staleTime: 5 * 60 * 1000,
    },
  })

  const params = useMemo(() => {
    const payload: GetUsersSubUpdateChartParams = {}
    if (username) {
      payload.username = username
    }

    const parsedAdminId = selectedAdmin !== 'all' ? Number(selectedAdmin) : undefined
    if (typeof parsedAdminId === 'number' && Number.isFinite(parsedAdminId)) {
      payload.admin_id = parsedAdminId
    }

    const parsedDays = selectedDays !== 'all' ? Number(selectedDays) : undefined
    if (typeof parsedDays === 'number' && Number.isFinite(parsedDays)) {
      payload.days = parsedDays
    }

    return Object.keys(payload).length > 0 ? payload : undefined
  }, [username, selectedAdmin, selectedDays])

  const { data, isLoading, error } = useGetUsersSubUpdateChart(params, {
    query: {
      refetchInterval: 60_000,
    },
  })

  const segments = useMemo<SegmentWithColor[]>(() => {
    if (!data?.segments?.length) {
      return []
    }

    return data.segments.map((segment: UserSubscriptionUpdateChartSegment, index: number) => {
      const safePercentage = typeof segment.percentage === 'number' && !Number.isNaN(segment.percentage) ? segment.percentage : 0
      const safeCount = typeof segment.count === 'number' && !Number.isNaN(segment.count) ? segment.count : 0
      const key = buildSegmentKey(segment.name || '', index)

      // Color assignment logic similar to AllNodesStackedBarChart
      let color
      if (index === 0) {
        // First segment uses primary color
        color = 'hsl(var(--primary))'
      } else if (index < 5) {
        // Use palette colors for segments 2-5: --chart-2, --chart-3, ...
        color = `hsl(var(--chart-${index + 1}))`
      } else {
        // Generate distinct colors for segments beyond palette
        color = generateDistinctColor(index, data?.segments?.length || 0, resolvedTheme === 'dark')
      }

      return {
        ...segment,
        key,
        percentage: safePercentage,
        count: safeCount,
        color,
      } as SegmentWithColor
    })
  }, [data?.segments, resolvedTheme])

  const chartData = useMemo(
    () =>
      segments.map((segment: SegmentWithColor) => ({
        segmentKey: segment.key,
        agent: segment.name,
        updates: segment.count,
        percentage: segment.percentage,
        fill: segment.color,
      })),
    [segments],
  )

  const chartConfig = useMemo<ChartConfig>(() => {
    const dynamicConfig = segments.reduce<ChartConfig>((config: ChartConfig, segment: SegmentWithColor) => {
      config[segment.key] = {
        label: segment.name,
        color: segment.color,
      }
      return config
    }, {})

    return {
      updates: {
        label: t('statistics.totalSubscriptions'),
      },
      ...dynamicConfig,
    }
  }, [segments, t])

  const hasData = segments.some((segment: SegmentWithColor) => segment.count > 0)
  const total = data?.total ?? 0
  const errorDescription = error && typeof error === 'object' && 'message' in error ? String((error as { message?: string }).message) : undefined
  const leadingSegment = useMemo(() => [...segments].sort((a: SegmentWithColor, b: SegmentWithColor) => b.count - a.count)[0], [segments])

  return (
    <Card>
      <CardHeader className="flex flex-col gap-4 pb-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <CardTitle className="mb-2">{t('statistics.subscriptionDistribution')}</CardTitle>
          <CardDescription>{t('statistics.subscriptionDistributionDescription')}</CardDescription>
        </div>
        <div className="flex w-full flex-col gap-4 lg:flex-row lg:items-end">
          <div className="flex flex-1 flex-col gap-2">
            <span className="text-xs font-medium text-muted-foreground">{t('statistics.daysFilterLabel')}</span>
            <Select value={selectedDays} onValueChange={setSelectedDays}>
              <SelectTrigger className="h-9">
                <SelectValue placeholder={t('statistics.daysFilterPlaceholder')} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">{t('statistics.daysFilterAll')}</SelectItem>
                <SelectItem value="1">{t('statistics.daysFilter1')}</SelectItem>
                <SelectItem value="7">{t('statistics.daysFilter7')}</SelectItem>
                <SelectItem value="30">{t('statistics.daysFilter30')}</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="flex flex-1 flex-col gap-2">
            <span className="text-xs font-medium text-muted-foreground">{t('statistics.adminFilterLabel')}</span>
            <Select value={selectedAdmin} onValueChange={setSelectedAdmin} disabled={isLoadingAdmins}>
              <SelectTrigger className="h-9">
                <SelectValue placeholder={t('statistics.adminFilterPlaceholder')} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">{t('statistics.adminFilterAll')}</SelectItem>
                {(admins?.admins || [])
                  .filter((admin: AdminDetails) => admin.id != null)
                  .map((admin: AdminDetails) => (
                    <SelectItem key={admin.id} value={String(admin.id)}>
                      {admin.username}
                    </SelectItem>
                  ))}
              </SelectContent>
            </Select>
          </div>
        </div>
      </CardHeader>
      <CardContent className="pt-4">
        {isLoading ? (
          <LoadingState />
        ) : error ? (
          <ChartEmptyState type="error" title={t('errors.statisticsLoadFailed')} description={errorDescription || t('errors.connectionFailed')} className="max-h-[340px] min-h-[260px]" />
        ) : !hasData ? (
          <ChartEmptyState type="no-data" className="max-h-[340px] min-h-[260px]" />
        ) : (
          <div className="flex flex-col items-center gap-6 lg:flex-row">
            <div className="w-full lg:w-1/2">
              <ChartContainer config={chartConfig} className="mx-auto aspect-square max-h-[320px] max-w-[320px] [&_.recharts-text]:fill-transparent">
                <PieChart>
                  <ChartTooltip content={<CustomTooltip />} />
                  <Pie data={chartData} dataKey="updates" nameKey="agent" innerRadius="55%" outerRadius="95%" paddingAngle={chartData.length > 1 ? 3 : 0} strokeWidth={2} isAnimationActive>
                    {chartData.map((segment: (typeof chartData)[0]) => (
                      <Cell key={segment.segmentKey} fill={segment.fill} />
                    ))}
                  </Pie>
                </PieChart>
              </ChartContainer>
            </div>
            <div className={`flex w-full flex-1 flex-col gap-4 lg:w-1/2 ${dir === 'rtl' ? 'items-end' : 'items-start'}`}>
              <div className="w-full max-w-xs rounded-lg border border-border/60 bg-muted/30 p-4">
                <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{t('statistics.totalSubscriptions')}</p>
                <p dir="ltr" className="mt-2 text-3xl font-semibold text-foreground">
                  {numberWithCommas(total)}
                </p>
              </div>
              <div className="max-h-64 w-full overflow-y-auto">
                <ul className="w-full space-y-3">
                  {segments.map((segment: SegmentWithColor) => (
                    <li key={segment.key} className={`flex items-center justify-between gap-4 rounded-md border border-border/40 px-3 py-2 max-w-full ${dir === 'rtl' ? 'flex-row-reverse' : ''}`}>
                      <div className={`flex items-center gap-2 overflow-hidden ${dir === 'rtl' ? 'flex-row-reverse' : ''}`}>
                        <span className="h-3 w-3 rounded-full" style={{ backgroundColor: segment.color }} />
                        <span className="text-sm font-medium text-foreground flex-1 truncate">{segment.name}</span>
                      </div>
                      <div className={`flex items-baseline gap-3 text-sm font-semibold text-foreground ${dir === 'rtl' ? 'flex-row-reverse' : ''}`}>
                        <span dir="ltr" className="font-mono">
                          {numberWithCommas(segment.count)}
                        </span>
                        <span className="text-xs font-normal text-muted-foreground">{segment.percentage.toFixed(1)}%</span>
                      </div>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </div>
        )}
      </CardContent>
      {leadingSegment && (
        <CardFooter className="flex-col gap-1.5 pt-4">
          <div className="flex items-center gap-2 rounded-lg border border-primary/20 bg-gradient-to-r from-primary/10 via-primary/5 to-transparent px-3 py-2 text-xs">
            <div className="flex items-center gap-1.5 font-semibold text-primary">
              <TrendingUp className="h-3.5 w-3.5" />
              <span>
                {t('statistics.leadingClientMessage', {
                  client: leadingSegment.name,
                  percentage: leadingSegment.percentage.toFixed(1),
                })}
              </span>
            </div>
            <div className="ml-auto h-2.5 w-2.5 rounded-full border-2 border-primary/30 shadow-sm" style={{ backgroundColor: leadingSegment.color }} />
          </div>
        </CardFooter>
      )}
    </Card>
  )
}

function LoadingState() {
  return (
    <div className="flex flex-col items-center gap-6 lg:flex-row">
      <div className="flex w-full items-center justify-center lg:w-1/2">
        <Skeleton className="h-[220px] w-[220px] rounded-full sm:h-[260px] sm:w-[260px]" />
      </div>
      <div className="flex w-full flex-1 flex-col gap-4">
        <Skeleton className="h-16 w-full max-w-xs rounded-lg" />
        <Skeleton className="h-10 w-full max-w-xs rounded-lg" />
        <div className="space-y-3">
          {Array.from({ length: 4 }).map((_, index: number) => (
            <div key={index} className="flex items-center justify-between gap-4">
              <div className="flex items-center gap-2">
                <Skeleton className="h-3 w-3 rounded-full" />
                <Skeleton className="h-4 w-24" />
              </div>
              <Skeleton className="h-4 w-16" />
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

export default UserSubUpdatePieChart
