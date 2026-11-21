import InboundRatioTable from '@/features/inbound-ratio/components/inbound-ratio-table'
import { useAdmin } from '@/hooks/use-admin'
import { getGetInboundRatiosQueryKey, getInboundRatios } from '@/service/inbound-ratio'
import { hasPermission } from '@/utils/rbac'
import { useQuery } from '@tanstack/react-query'
import { AlertTriangle } from 'lucide-react'
import { useTranslation } from 'react-i18next'

export default function InboundRatiosSettings() {
  const { t } = useTranslation()
  const { admin } = useAdmin()
  const canUpdateInbounds = hasPermission(admin, 'hosts', 'update')

  const { data, isLoading } = useQuery({
    queryKey: getGetInboundRatiosQueryKey(),
    queryFn: getInboundRatios,
  })

  return (
    <div className="space-y-6 p-4 pb-10 sm:space-y-8 sm:py-6 lg:space-y-10 lg:py-8">
      <div className="space-y-3">
        <h3 className="text-base font-semibold sm:text-lg">
          {t('settings.inboundsratio.sectionTitle', { defaultValue: 'Inbound Usage Ratios Settings' })}
        </h3>
        <p className="text-muted-foreground max-w-4xl text-xs leading-relaxed sm:text-sm">
          {t('settings.inboundsratio.sectionDescription', {
            defaultValue:
              "Multiplies the traffic charged to users whose groups include this inbound, on top of the node's own ratio. When a user's groups expose several inbounds, the highest ratio among them applies.",
          })}
        </p>
        <p className="flex max-w-4xl items-start gap-2 rounded-md border border-amber-500/50 bg-amber-500/15 px-3 py-2 text-xs leading-relaxed text-amber-700 sm:text-sm dark:text-amber-400">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <span>
            {t('settings.inboundsratio.sectionWarning', {
              defaultValue:
                'Warning: if you set a node usage ratio and an inbound ratio at the same time, they are combined into one coefficient (node ratio × inbound ratio). Example: node usage ratio 2 and inbound usage ratio 2 — a 10 MB download or upload is charged as 40 MB.',
            })}
          </span>
        </p>
      </div>

      <InboundRatioTable data={data} isLoading={isLoading} canUpdate={canUpdateInbounds} />
    </div>
  )
}
