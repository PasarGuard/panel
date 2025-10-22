import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'
import { type ChartConfig, ChartContainer, ChartTooltip, ChartTooltipContent } from '@/components/ui/chart'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import useDirDetection from '@/hooks/use-dir-detection'
import { type GetUsersSubUpdateChartParams, useGetAdmins, useGetUsersSubUpdateChart, type UserSubscriptionUpdateChartSegment } from '@/service/api'
import { numberWithCommas } from '@/utils/formatByte'
import { TrendingUp } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Cell, LabelList, Pie, PieChart } from 'recharts'
import { ChartEmptyState } from './EmptyState'

const COLOR_PALETTE = Array.from({ length: 5 }, (_, index) => `hsl(var(--chart-${index + 1}))`)

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
  const sanitized = name
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')

  return sanitized || `segment-${index}`
}

export function UserSubUpdatePieChart({ username, adminId }: UserSubUpdatePieChartProps) {
  const { t } = useTranslation()
  const dir = useDirDetection()
  const [selectedAdmin, setSelectedAdmin] = useState(() => (adminId != null ? String(adminId) : 'all'))

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

    return Object.keys(payload).length > 0 ? payload : undefined
  }, [username, selectedAdmin])

  const { data, isLoading, error } = useGetUsersSubUpdateChart(params, {
    query: {
      refetchInterval: 60_000,
      refetchOnWindowFocus: false,
    },
  })

  const segments = useMemo<SegmentWithColor[]>(() => {
    if (!data?.segments?.length) {
      return []
    }

    return data.segments.map((segment, index) => {
      const safePercentage = typeof segment.percentage === 'number' && !Number.isNaN(segment.percentage) ? segment.percentage : 0
      const safeCount = typeof segment.count === 'number' && !Number.isNaN(segment.count) ? segment.count : 0
      const key = buildSegmentKey(segment.name, index)

      return {
        ...segment,
        key,
        percentage: safePercentage,
        count: safeCount,
        color: COLOR_PALETTE[index % COLOR_PALETTE.length],
      }
    })
  }, [data?.segments])

  const chartData = useMemo(
    () =>
      segments.map(segment => ({
        segmentKey: segment.key,
        agent: segment.name,
        updates: segment.count,
        percentage: segment.percentage,
        fill: segment.color,
      })),
    [segments],
  )

  const chartConfig = useMemo<ChartConfig>(() => {
    const dynamicConfig = segments.reduce<ChartConfig>((config, segment) => {
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

  const hasData = segments.some(segment => segment.count > 0)
  const total = data?.total ?? 0
  const errorDescription = error && typeof error === 'object' && 'message' in error ? String((error as { message?: string }).message) : undefined
  const leadingSegment = useMemo(() => [...segments].sort((a, b) => b.count - a.count)[0], [segments])

  return (
    <Card>
      <CardHeader className="flex flex-col gap-4 pb-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <CardTitle>{t('statistics.subscriptionDistribution')}</CardTitle>
          <CardDescription>{t('statistics.subscriptionDistributionDescription')}</CardDescription>
        </div>
        <div className="flex w-full flex-col gap-2 lg:max-w-xs">
          <span className="text-xs font-medium text-muted-foreground">{t('statistics.adminFilterLabel')}</span>
          <Select value={selectedAdmin} onValueChange={setSelectedAdmin} disabled={isLoadingAdmins}>
            <SelectTrigger className="h-9">
              <SelectValue placeholder={t('statistics.adminFilterPlaceholder')} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">{t('statistics.adminFilterAll')}</SelectItem>
              {admins
                ?.filter(admin => admin.id != null)
                .map(admin => (
                  <SelectItem key={admin.id} value={String(admin.id)}>
                    {admin.username}
                  </SelectItem>
                ))}
            </SelectContent>
          </Select>
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
              <ChartContainer config={chartConfig} className="mx-auto aspect-square max-h-[320px] max-w-[320px] [&_.recharts-text]:fill-background">
                <PieChart>
                  <ChartTooltip
                    content={
                      <ChartTooltipContent
                        nameKey="updates"
                        hideLabel
                        formatter={(value, _name, item) => {
                          const payload = item?.payload as { percentage: number }
                          return `${numberWithCommas(value as number)} • ${payload?.percentage?.toFixed(1) ?? '0.0'}%`
                        }}
                      />
                    }
                  />
                  <Pie data={chartData} dataKey="updates" nameKey="segmentKey" innerRadius="55%" outerRadius="95%" paddingAngle={chartData.length > 1 ? 3 : 0} strokeWidth={2} isAnimationActive>
                    {chartData.map(segment => (
                      <Cell key={segment.segmentKey} fill={segment.fill} />
                    ))}
                    <LabelList
                      dataKey="segmentKey"
                      position="outside"
                      className="fill-background text-[10px] font-medium sm:text-xs"
                      stroke="none"
                      formatter={(value: string) => chartConfig[value]?.label ?? value}
                    />
                  </Pie>
                </PieChart>
              </ChartContainer>
            </div>
            <div className={`flex w-full flex-1 flex-col gap-4 ${dir === 'rtl' ? 'items-end' : 'items-start'}`}>
              <div className="w-full max-w-xs rounded-lg border border-border/60 bg-muted/30 p-4">
                <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{t('statistics.totalSubscriptions')}</p>
                <p dir="ltr" className="mt-2 text-3xl font-semibold text-foreground">
                  {numberWithCommas(total)}
                </p>
              </div>
              <ul className="w-full space-y-3">
                {segments.map(segment => (
                  <li key={segment.key} className={`flex items-center justify-between gap-4 rounded-md border border-border/40 px-3 py-2 ${dir === 'rtl' ? 'flex-row-reverse' : ''}`}>
                    <div className={`flex items-center gap-2 ${dir === 'rtl' ? 'flex-row-reverse' : ''}`}>
                      <span className="h-3 w-3 rounded-full" style={{ backgroundColor: segment.color }} />
                      <span className="text-sm font-medium text-foreground">{segment.name}</span>
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
        )}
      </CardContent>
      {leadingSegment && (
        <CardFooter className="flex-col gap-2 text-xs text-muted-foreground sm:text-sm">
          <div className="flex items-center gap-2 font-medium text-foreground">
            {t('statistics.leadingClientMessage', {
              client: leadingSegment.name,
              percentage: leadingSegment.percentage.toFixed(1),
            })}
            <TrendingUp className="h-4 w-4" />
          </div>
          <div>{t('statistics.subscriptionDistributionDescription')}</div>
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
          {Array.from({ length: 4 }).map((_, index) => (
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
