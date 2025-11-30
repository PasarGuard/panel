import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { useVersionCheck } from '@/hooks/use-version-check'
import { cn } from '@/lib/utils'
import { useTranslation } from 'react-i18next'
import { useSidebar } from '@/components/ui/sidebar'

interface VersionBadgeProps {
  currentVersion: string | null
  className?: string
}

export function VersionBadge({ currentVersion, className }: VersionBadgeProps) {
  const { t } = useTranslation()
  const { hasUpdate, latestVersion, releaseUrl, isLoading } = useVersionCheck(currentVersion)
  const { state, isMobile } = useSidebar()

  if (isLoading || !currentVersion) {
    return null
  }

  const releaseLink = releaseUrl || 'https://github.com/PasarGuard/panel/releases/latest'
  const showText = isMobile || state === 'expanded'
  const showBadge = state === 'collapsed' && !isMobile

  // Show badge when collapsed on desktop
  if (showBadge && hasUpdate) {
    return (
      <span
        className={cn(
          'absolute bottom-0 right-0 h-2.5 w-2.5 rounded-full',
          'bg-amber-500 dark:bg-amber-400',
          'border-2 border-background',
          'translate-x-1/2 translate-y-1/2',
          'z-20',
          'shadow-sm'
        )}
        aria-label="Update available"
      />
    )
  }

  // Show text on mobile or when expanded with tooltip
  if (showText && hasUpdate && latestVersion) {
    return (
      <Tooltip delayDuration={100}>
        <TooltipTrigger asChild>
          <a
            href={releaseLink}
            target="_blank"
            rel="noopener noreferrer"
            className={cn('inline-flex items-center gap-1 text-xs text-amber-600 dark:text-amber-400 hover:underline min-w-0 max-w-full', className)}
            onClick={(e) => e.stopPropagation()}
          >
            <span className="h-1.5 w-1.5 rounded-full bg-amber-500 dark:bg-amber-400 shrink-0" />
            <span className="truncate min-w-0">{t('version.needsUpdate')}</span>
          </a>
        </TooltipTrigger>
        <TooltipContent side="bottom" className="p-1.5">
          <div className="space-y-0.5 text-[10px]">
            <p className="font-medium">{t('version.newVersionAvailable')}</p>
            <p>
              {t('version.currentVersion')}: v{currentVersion} → {t('version.latestVersion')}: v{latestVersion}
            </p>
            <p className="text-[9px]">{t('version.clickToUpdate')}</p>
          </div>
        </TooltipContent>
      </Tooltip>
    )
  }

  // Default: show dot with tooltip (for non-mobile, non-expanded states)
  if (!hasUpdate) {
    return (
      <span className="h-1.5 w-1.5 rounded-full bg-emerald-500/50 dark:bg-emerald-400/50" />
    )
  }

  return (
    <Tooltip delayDuration={100}>
      <TooltipTrigger asChild>
        <a
          href={releaseLink}
          target="_blank"
          rel="noopener noreferrer"
          className={cn('inline-flex', className)}
          onClick={(e) => e.stopPropagation()}
        >
          <span className="h-1.5 w-1.5 rounded-full bg-amber-500 dark:bg-amber-400" />
        </a>
      </TooltipTrigger>
      <TooltipContent side="bottom" className="p-1.5">
        <div className="space-y-0.5 text-[10px]">
          <p className="font-medium">{t('version.newVersionAvailable')}</p>
          <p>
            {t('version.currentVersion')}: v{currentVersion} → {t('version.latestVersion')}: v{latestVersion}
          </p>
          <p className="text-[9px]">{t('version.clickToUpdate')}</p>
        </div>
      </TooltipContent>
    </Tooltip>
  )
}

