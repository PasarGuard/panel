import { X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { useVersionCheck } from '@/hooks/use-version-check'
import { useTheme } from '@/app/providers/theme-provider'
import { getGradientByColorTheme, getIndicatorColorByTheme } from '@/constants/ThemeGradients'
import useDirDetection from '@/hooks/use-dir-detection'
import { useClipboard } from '@/hooks/use-clipboard'
import { toast } from 'sonner'
import { useSystemVersion } from '@/hooks/use-system-version'
import { useAdmin } from '@/hooks/use-admin'
import { isOwner } from '@/utils/rbac'

const VERSION_BANNER_STORAGE_KEY = 'version_update_banner_closed'
const HOURS_TO_HIDE = 24

interface BannerStorage {
  timestamp: number
  version: string
}

export function VersionUpdateBanner() {
  const { t } = useTranslation()
  const isRTL = useDirDetection() === 'rtl'
  const { resolvedTheme, colorTheme } = useTheme()
  const isDark = resolvedTheme === 'dark'
  const { copy } = useClipboard()
  const { admin } = useAdmin()
  const isOwnerAdmin = isOwner(admin)
  const { currentVersion } = useSystemVersion({ enabled: isOwnerAdmin })
  const [isVisible, setIsVisible] = useState(false)
  const [isClosing, setIsClosing] = useState(false)
  const [isAnimating, setIsAnimating] = useState(false)
  const normalizedVersion = currentVersion ? currentVersion.replace(/[^0-9.]/g, '') : null
  const { hasUpdate, latestVersion, releaseUrl, isLoading } = useVersionCheck(normalizedVersion, { enabled: isOwnerAdmin })

  const gradientBg = getGradientByColorTheme(colorTheme, isDark, 'banner')
  const indicatorColor = getIndicatorColorByTheme(colorTheme, isDark)

  useEffect(() => {
    if (!isOwnerAdmin || isLoading || !hasUpdate || !normalizedVersion) {
      setIsVisible(false)
      setIsAnimating(false)
      return
    }

    const checkShouldShow = () => {
      try {
        const stored = localStorage.getItem(VERSION_BANNER_STORAGE_KEY)
        let bannerData: BannerStorage | null = null

        if (stored) {
          bannerData = JSON.parse(stored)
        }

        // If user closed for a different version, show again
        if (bannerData && bannerData.version !== latestVersion) {
          setIsVisible(true)
          setTimeout(() => {
            setIsAnimating(true)
          }, 100)
          return
        }

        if (!bannerData) {
          setIsVisible(true)
          setTimeout(() => {
            setIsAnimating(true)
          }, 100)
          return
        }

        const now = Date.now()
        const hoursSinceClose = (now - bannerData.timestamp) / (1000 * 60 * 60)

        if (hoursSinceClose >= HOURS_TO_HIDE) {
          setIsVisible(true)
          setTimeout(() => {
            setIsAnimating(true)
          }, 100)
        }
      } catch (error) {
        // If parsing fails, show the banner
        setIsVisible(true)
        setTimeout(() => {
          setIsAnimating(true)
        }, 100)
      }
    }

    checkShouldShow()
  }, [hasUpdate, isOwnerAdmin, latestVersion, normalizedVersion, isLoading])

  const handleClose = (e: React.MouseEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setIsClosing(true)

    if (latestVersion) {
      const bannerData: BannerStorage = {
        timestamp: Date.now(),
        version: latestVersion,
      }
      localStorage.setItem(VERSION_BANNER_STORAGE_KEY, JSON.stringify(bannerData))
    }

    setTimeout(() => {
      setIsVisible(false)
    }, 300)
  }

  const handleCopyCommand = async (e: React.MouseEvent) => {
    e.preventDefault()
    e.stopPropagation()
    await copy('pasarguard update')
    toast.success(t('usersTable.copied'))
  }

  if (!isOwnerAdmin || isLoading || !hasUpdate || !isVisible || !latestVersion || !normalizedVersion) return null

  const releaseLink = releaseUrl || 'https://github.com/PasarGuard/panel/releases/latest'

  return (
    <div
      className={cn(
        'fixed bottom-3 z-[50] max-w-[calc(100vw-1rem)] sm:bottom-4 sm:max-w-sm',
        isRTL ? 'right-2 left-2 sm:right-auto sm:left-4 sm:w-96' : 'right-2 left-2 sm:right-4 sm:left-auto sm:w-96',
        'overflow-hidden rounded-lg shadow-xl backdrop-blur-md',
        gradientBg,
        'border',
        isClosing ? 'pointer-events-none translate-y-2 scale-95 opacity-0' : 'translate-y-0 scale-100 opacity-100',
      )}
      style={{
        transition: isClosing ? 'opacity 300ms ease-in-out, transform 300ms ease-in-out' : 'opacity 400ms ease-out, transform 400ms ease-out',
        opacity: isClosing ? 0 : isAnimating ? 1 : 0,
        transform: isClosing ? 'translateY(8px) scale(0.95)' : isAnimating ? 'translateY(0) scale(1)' : 'translateY(8px) scale(0.95)',
      }}
      dir={isRTL ? 'rtl' : 'ltr'}
    >
      <a
        href={releaseLink}
        target="_blank"
        rel="noopener noreferrer"
        className={cn('block w-full cursor-pointer transition-all duration-200 ease-in-out hover:opacity-95', isRTL ? 'pr-4 pl-10 sm:pr-4 sm:pl-10' : 'pr-10 pl-4 sm:pr-10 sm:pl-4')}
      >
        <div className="flex items-start gap-2 py-2.5 sm:gap-3 sm:py-3">
          <span className={cn('mt-1.5 flex h-2 w-2 shrink-0 rounded-full sm:mt-1.5 sm:h-2.5 sm:w-2.5', indicatorColor)} />
          <div className="min-w-0 flex-1 overflow-hidden">
            <p className={cn('text-foreground/90 text-xs leading-tight font-semibold break-words sm:text-sm', isRTL ? 'text-right' : 'text-left')}>{t('version.newVersionAvailable')}</p>
            <p className={cn('text-foreground/70 mt-0.5 text-[11px] leading-relaxed break-words sm:mt-1 sm:text-xs', isRTL ? 'text-right' : 'text-left')}>
              {t('version.updateBanner', { current: `v${normalizedVersion}`, latest: `v${latestVersion}` })}
            </p>
            <div className="mt-1.5 flex flex-col items-start gap-1 sm:flex-row sm:items-center sm:gap-1.5">
              <span className="text-foreground/60 text-[11px] leading-relaxed break-words sm:text-xs sm:whitespace-nowrap">{t('version.updateCommandLabel')}</span>
              <code
                className="bg-muted/50 hover:bg-muted text-foreground/60 shrink-0 cursor-pointer rounded-sm px-1.5 py-0.5 font-mono text-[10px] break-all transition-colors sm:text-[11px] sm:break-normal"
                onClick={handleCopyCommand}
                title={t('copy')}
              >
                pasarguard update
              </code>
            </div>
          </div>
        </div>
      </a>

      <Button
        variant="ghost"
        size="icon"
        onClick={handleClose}
        className={cn(
          'hover:bg-muted/40 absolute top-1.5 z-10 h-7 w-7 shrink-0 rounded transition-all sm:top-2 sm:h-6 sm:w-6',
          'text-muted-foreground/70 hover:text-foreground touch-manipulation',
          isRTL ? 'left-1.5 sm:left-2' : 'right-1.5 sm:right-2',
        )}
        aria-label={t('version.closeBanner')}
      >
        <X className="h-4 w-4 sm:h-3.5 sm:w-3.5" />
      </Button>
    </div>
  )
}
