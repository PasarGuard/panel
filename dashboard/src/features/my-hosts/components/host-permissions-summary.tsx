import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import type { MyHostsPolicy } from '@/service/api'
import { Check, LockKeyhole, SlidersHorizontal } from 'lucide-react'
import { useTranslation } from 'react-i18next'

export function HostPermissionsSummary({ policy }: { policy: MyHostsPolicy }) {
  const { t } = useTranslation()

  return (
    <section className="bg-muted/20 flex flex-col gap-4 rounded-lg border px-4 py-4 sm:flex-row sm:items-center sm:justify-between sm:gap-6">
      <div className="flex items-start gap-3">
        <SlidersHorizontal className="text-muted-foreground mt-0.5 h-4 w-4 shrink-0" />
        <div className="space-y-1">
          <h2 className="text-sm font-medium">{t('myHosts.displaySettings')}</h2>
          <p className="text-muted-foreground text-xs leading-relaxed">{t('myHosts.scopeShort')}</p>
        </div>
      </div>
      <TooltipProvider delayDuration={150}>
        <ul className="flex shrink-0 flex-wrap items-center gap-x-5 gap-y-3 text-xs">
          {(['rename', 'reorder', 'disable'] as const).map(action => {
            const allowed = policy[`allow_${action}`]
            return (
              <li key={action}>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <span
                      tabIndex={0}
                      className={`focus-visible:ring-ring inline-flex cursor-default items-center gap-1.5 rounded-sm outline-none focus-visible:ring-2 ${allowed ? 'text-foreground' : 'text-muted-foreground'}`}
                    >
                      {allowed ? <Check className="text-primary h-3.5 w-3.5" /> : <LockKeyhole className="h-3.5 w-3.5" />}
                      {t(`myHosts.${action}Short`)}
                      <span className="sr-only">: {t(allowed ? 'myHosts.allowed' : 'myHosts.locked')}</span>
                    </span>
                  </TooltipTrigger>
                  <TooltipContent className="max-w-64 text-center">
                    <p>{t(allowed ? `myHosts.${action}Description` : 'myHosts.locked')}</p>
                    {action === 'reorder' && allowed && <p className="mt-1">{t('myHosts.policyNotice')}</p>}
                  </TooltipContent>
                </Tooltip>
              </li>
            )
          })}
        </ul>
      </TooltipProvider>
    </section>
  )
}
