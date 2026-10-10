import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Progress } from '@/components/ui/progress'
import { Skeleton } from '@/components/ui/skeleton'
import useDirDetection from '@/hooks/use-dir-detection'
import { cn } from '@/lib/utils'
import { useGetWireguardSubnets, type WireGuardSubnetUsage } from '@/service/api'
import { ChevronDown } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'

const numberFormatter = new Intl.NumberFormat()
const compactNumberFormatter = new Intl.NumberFormat(undefined, {
  maximumFractionDigits: 1,
  notation: 'compact',
})

function formatNumber(value: number): string {
  return numberFormatter.format(value)
}

function formatCompactNumber(value: number): string {
  return compactNumberFormatter.format(value)
}

function usagePercent(row: WireGuardSubnetUsage): number {
  if (row.capacity <= 0) return 0
  return Math.min(100, (row.used / row.capacity) * 100)
}

function formatPercent(value: number): string {
  if (value > 0 && value < 1) return '<1%'
  return `${Math.round(value)}%`
}

function usageIndicatorClassName(percent: number) {
  if (percent >= 90) return 'bg-destructive'
  if (percent >= 70) return 'bg-amber-500'
  return undefined
}

function MetricTile({ label, value, tone }: { label: string; value: number; tone?: 'muted' | 'primary' | 'danger' }) {
  return (
    <div className={cn('bg-muted/30 min-w-0 rounded-md border px-3 py-2', tone === 'danger' && 'border-destructive/30 bg-destructive/10', tone === 'primary' && 'border-primary/25 bg-primary/10')}>
      <div className="text-muted-foreground text-start text-[11px] font-medium tracking-wide uppercase">{label}</div>
      <div
        className={cn(
          'mt-1 truncate text-start text-sm font-semibold tabular-nums',
          tone === 'muted' ? 'text-muted-foreground' : tone === 'danger' ? 'text-destructive' : tone === 'primary' ? 'text-primary' : 'text-foreground',
        )}
        title={formatNumber(value)}
      >
        {formatNumber(value)}
      </div>
    </div>
  )
}

function SubnetCard({ row }: { row: WireGuardSubnetUsage }) {
  const { t } = useTranslation()
  const dir = useDirDetection()
  const [showFree, setShowFree] = useState(false)
  const percent = usagePercent(row)
  const percentLabel = formatPercent(percent)
  const previewFree = row.free_ips.slice(0, 10)
  const hasMoreFree = row.free_ips.length > previewFree.length
  const visibleTags = row.interface_tags.slice(0, 4)
  const hiddenTagsCount = Math.max(0, row.interface_tags.length - visibleTags.length)
  const freeCountLabel = row.free_ips.length < row.free ? `${formatCompactNumber(row.free_ips.length)}+` : formatCompactNumber(row.free_ips.length)
  const loadedMoreCount = Math.max(0, row.free_ips.length - previewFree.length)
  const usedLabel = t('nodes.wireguard.used', { defaultValue: 'Used' })

  return (
    <Card dir={dir} className={cn('overflow-hidden px-4 py-4', dir === 'rtl' && 'text-right')}>
      <div className="flex flex-col gap-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-start sm:justify-between">
          <div className="min-w-0 flex-1">
            <div className="flex min-w-0 flex-wrap items-center gap-2">
              <div dir="ltr" className="min-w-0 truncate font-mono text-base font-semibold">
                {row.subnet}
              </div>
              <Badge variant="outline" className="shrink-0 text-xs tabular-nums">
                {percentLabel}
              </Badge>
            </div>
            <div className="text-muted-foreground mt-2 flex flex-wrap gap-1.5">
              {row.interface_tags.length === 0 ? (
                <span className="text-xs">{t('nodes.wireguard.noTags', { defaultValue: 'No tags' })}</span>
              ) : (
                visibleTags.map(tag => (
                  <Badge key={tag} dir="ltr" variant="secondary" className="font-mono text-xs">
                    {tag}
                  </Badge>
                ))
              )}
              {hiddenTagsCount > 0 && (
                <Badge variant="outline" className="text-xs tabular-nums">
                  +{hiddenTagsCount}
                </Badge>
              )}
            </div>
          </div>
          <div className="grid grid-cols-3 gap-2 sm:flex-[0_1_16rem]">
            <MetricTile label={usedLabel} value={row.used} tone={row.used === 0 ? 'muted' : 'primary'} />
            <MetricTile label={t('nodes.wireguard.free', { defaultValue: 'Free' })} value={row.free} />
            <MetricTile label={t('nodes.wireguard.capacity', { defaultValue: 'Capacity' })} value={row.capacity} />
          </div>
        </div>

        <div className="space-y-2">
          <div className="flex items-center justify-between gap-3 text-xs">
            <span className="text-muted-foreground font-medium">{t('nodes.wireguard.usage', { defaultValue: 'Usage' })}</span>
            <span className={cn('text-muted-foreground inline-flex items-center gap-1 tabular-nums', dir === 'rtl' && 'flex-row-reverse')}>
              <span dir="ltr" className="text-foreground font-medium">
                {percentLabel}
              </span>
              <span>/</span>
              <span>{t('nodes.wireguard.usedCount', { value: formatNumber(row.used) })}</span>
            </span>
          </div>
          <Progress value={percent} className="h-2 bg-muted" indicatorClassName={usageIndicatorClassName(percent)} />
        </div>

        {row.free_ips.length > 0 && (
          <div className="rounded-lg border bg-muted/20 p-2.5">
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0">
                <div className="text-sm font-medium">
                  {t('nodes.wireguard.freeIps', { defaultValue: 'Free IPs' })} <span className="text-muted-foreground font-normal tabular-nums">({freeCountLabel})</span>
                </div>
                <div className="text-muted-foreground text-xs">
                  {t('nodes.wireguard.freeIpsPreview', { count: previewFree.length })}
                </div>
              </div>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="text-muted-foreground h-8 justify-start px-2 text-xs sm:justify-center"
                onClick={() => setShowFree(open => !open)}
                aria-expanded={showFree}
              >
                <ChevronDown className={cn('h-3.5 w-3.5 transition-transform', dir === 'rtl' ? 'ml-1' : 'mr-1', showFree && 'rotate-180')} />
                {showFree ? t('nodes.wireguard.hidePreview') : t('nodes.wireguard.showPreview')}
              </Button>
            </div>
            {showFree && (
              <div dir="ltr" className="mt-2 flex flex-wrap justify-start gap-1.5 font-mono text-xs">
                {previewFree.map(ip => (
                  <span key={ip} className="bg-background rounded-md border px-2 py-1">
                    {ip}
                  </span>
                ))}
                {hasMoreFree && <span className="text-muted-foreground rounded-md border border-dashed px-2 py-1">+{formatNumber(loadedMoreCount)} ...</span>}
              </div>
            )}
          </div>
        )}

        {row.free_ips.length === 0 && (
          <div className="border-destructive/20 bg-destructive/10 text-destructive rounded-lg border px-3 py-2 text-sm">
            {t('nodes.wireguard.noFreeIps')}
          </div>
        )}
      </div>
    </Card>
  )
}

function SubnetCardSkeleton({ index }: { index: number }) {
  const dir = useDirDetection()

  return (
    <Card key={index} dir={dir} className="overflow-hidden px-4 py-4">
      <div className="flex flex-col gap-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <Skeleton className="h-5 w-36 sm:w-44" />
              <Skeleton className="h-5 w-12 rounded-full" />
            </div>
            <div className="mt-2 flex flex-wrap gap-1.5">
              <Skeleton className="h-5 w-14 rounded-full" />
              <Skeleton className="h-5 w-20 rounded-full" />
              {index % 2 === 0 && <Skeleton className="h-5 w-16 rounded-full" />}
            </div>
          </div>
          <div className="grid grid-cols-3 gap-2 sm:flex-[0_1_22rem]">
            <Skeleton className="h-[58px] rounded-md" />
            <Skeleton className="h-[58px] rounded-md" />
            <Skeleton className="h-[58px] rounded-md" />
          </div>
        </div>

        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <Skeleton className="h-3.5 w-16" />
            <Skeleton className="h-3.5 w-24" />
          </div>
          <Skeleton className="h-2 w-full rounded-full" />
        </div>

        <div className="rounded-lg border bg-muted/20 p-2.5">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <div className="space-y-1.5">
              <Skeleton className="h-4 w-32" />
              <Skeleton className="h-3.5 w-44" />
            </div>
            <Skeleton className="h-8 w-28" />
          </div>
        </div>
      </div>
    </Card>
  )
}

export default function WireGuardSubnetsList() {
  const { t } = useTranslation()
  const dir = useDirDetection()
  const { data, isLoading } = useGetWireguardSubnets()
  const rows = useMemo(() => data ?? [], [data])

  return (
    <div dir={dir} className={cn('flex w-full flex-col gap-4 px-4 py-4', dir === 'rtl' && 'rtl')}>
      {isLoading ? (
        <div className="grid gap-3 md:grid-cols-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <SubnetCardSkeleton key={i} index={i} />
          ))}
        </div>
      ) : rows.length === 0 ? (
        <Card className="text-muted-foreground px-4 py-10 text-center text-sm">{t('nodes.wireguard.empty', { defaultValue: 'No WireGuard subnets found.' })}</Card>
      ) : (
        <div className="grid gap-3 md:grid-cols-2">
          {rows.map(row => (
            <SubnetCard key={row.subnet} row={row} />
          ))}
        </div>
      )}
    </div>
  )
}
