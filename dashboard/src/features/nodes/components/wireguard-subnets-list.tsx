import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Progress } from '@/components/ui/progress'
import { Skeleton } from '@/components/ui/skeleton'
import { useGetWireguardSubnets, type WireGuardSubnetUsage } from '@/service/api'
import { cn } from '@/lib/utils'
import { ChevronDown, RefreshCw } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'

function usagePercent(row: WireGuardSubnetUsage): number {
  if (row.capacity <= 0) return 0
  return Math.min(100, Math.round((row.used / row.capacity) * 100))
}

function SubnetCard({ row }: { row: WireGuardSubnetUsage }) {
  const { t } = useTranslation()
  const [showFree, setShowFree] = useState(false)
  const percent = usagePercent(row)
  const previewFree = row.free_ips.slice(0, 12)
  const hasMoreFree = row.free_ips.length > previewFree.length

  return (
    <Card className="px-4 py-4">
      <div className="flex flex-col gap-3">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="min-w-0">
            <div className="truncate font-mono text-sm font-medium">{row.subnet}</div>
            <div className="text-muted-foreground mt-1 flex flex-wrap gap-1">
              {row.interface_tags.length === 0 ? (
                <span className="text-xs">{t('nodes.wireguard.noTags')}</span>
              ) : (
                row.interface_tags.map(tag => (
                  <Badge key={tag} variant="secondary" className="font-mono text-xs">
                    {tag}
                  </Badge>
                ))
              )}
            </div>
          </div>
          <div className="text-muted-foreground shrink-0 text-right text-xs tabular-nums">
            <div>
              {t('nodes.wireguard.used')}: <span className="text-foreground font-medium">{row.used}</span>
            </div>
            <div>
              {t('nodes.wireguard.free')}: <span className="text-foreground font-medium">{row.free}</span>
            </div>
            <div>
              {t('nodes.wireguard.capacity')}: <span className="text-foreground font-medium">{row.capacity}</span>
            </div>
          </div>
        </div>

        <div className="space-y-1">
          <div className="text-muted-foreground flex justify-between text-xs tabular-nums">
            <span>{t('nodes.wireguard.usage')}</span>
            <span>{percent}%</span>
          </div>
          <Progress
            value={percent}
            indicatorClassName={cn(percent >= 90 ? 'bg-destructive' : percent >= 70 ? 'bg-amber-500' : undefined)}
          />
        </div>

        {row.free_ips.length > 0 && (
          <div>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="text-muted-foreground h-7 px-2 text-xs"
              onClick={() => setShowFree(open => !open)}
            >
              <ChevronDown className={cn('mr-1 h-3.5 w-3.5 transition-transform', showFree && 'rotate-180')} />
              {t('nodes.wireguard.freeIps')} ({row.free_ips.length}
              {row.free_ips.length < row.free ? '+' : ''})
            </Button>
            {showFree && (
              <div className="bg-muted/40 mt-1 flex flex-wrap gap-1 rounded-md p-2 font-mono text-xs">
                {previewFree.map(ip => (
                  <span key={ip} className="bg-background rounded px-1.5 py-0.5">
                    {ip}
                  </span>
                ))}
                {hasMoreFree && <span className="text-muted-foreground px-1.5 py-0.5">…</span>}
              </div>
            )}
          </div>
        )}
      </div>
    </Card>
  )
}

export default function WireGuardSubnetsList() {
  const { t } = useTranslation()
  const { data, isLoading, isFetching, refetch } = useGetWireguardSubnets()
  const rows = useMemo(() => data ?? [], [data])

  return (
    <div className="flex w-full flex-col gap-4 px-4 py-4">
      <div className="flex items-center justify-end">
        <Button type="button" variant="outline" size="sm" onClick={() => refetch()} disabled={isFetching}>
          <RefreshCw className={cn('mr-1.5 h-3.5 w-3.5', isFetching && 'animate-spin')} />
          {t('nodes.wireguard.refresh')}
        </Button>
      </div>

      {isLoading ? (
        <div className="grid gap-3 md:grid-cols-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-36 w-full rounded-xl" />
          ))}
        </div>
      ) : rows.length === 0 ? (
        <Card className="text-muted-foreground px-4 py-10 text-center text-sm">{t('nodes.wireguard.empty')}</Card>
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
