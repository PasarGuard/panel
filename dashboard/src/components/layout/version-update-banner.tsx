import { X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { useVersionCheck } from '@/hooks/use-version-check'
import { getSystemStats } from '@/service/api'
import { useTheme } from '@/components/common/theme-provider'
import { getGradientByColorTheme, getIndicatorColorByTheme } from '@/constants/ThemeGradients'
import useDirDetection from '@/hooks/use-dir-detection'
import { useClipboard } from '@/hooks/use-clipboard'
import { toast } from 'sonner'

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
    const [currentVersion, setCurrentVersion] = useState<string | null>(null)
    const [isVisible, setIsVisible] = useState(false)
    const [isClosing, setIsClosing] = useState(false)
    const [isAnimating, setIsAnimating] = useState(false)
    const { hasUpdate, latestVersion, releaseUrl, isLoading } = useVersionCheck(currentVersion)

    const gradientBg = getGradientByColorTheme(colorTheme, isDark, 'banner')
    const indicatorColor = getIndicatorColorByTheme(colorTheme, isDark)

    useEffect(() => {
        const fetchVersion = async () => {
            try {
                const data = await getSystemStats()
                if (data?.version) {
                    setCurrentVersion(data.version)
                }
            } catch (error) {
                console.error('Failed to fetch version:', error)
            }
        }
        fetchVersion()
    }, [])

    useEffect(() => {
        if (isLoading || !hasUpdate || !currentVersion) {
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
    }, [hasUpdate, latestVersion, currentVersion, isLoading])

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

    if (isLoading || !hasUpdate || !isVisible || !latestVersion) return null

    const releaseLink = releaseUrl || 'https://github.com/PasarGuard/panel/releases/latest'

    return (
        <div
            className={cn(
                'fixed bottom-3 sm:bottom-4 z-[50] max-w-[calc(100vw-1rem)] sm:max-w-sm',
                isRTL ? 'left-2 right-2 sm:left-4 sm:right-auto sm:w-96' : 'left-2 right-2 sm:left-auto sm:right-4 sm:w-96',
                'rounded-lg shadow-xl backdrop-blur-md overflow-hidden',
                gradientBg,
                'border',
                isClosing
                    ? 'opacity-0 scale-95 translate-y-2 pointer-events-none'
                    : 'opacity-100 scale-100 translate-y-0'
            )}
            style={{
                transition: isClosing
                    ? 'opacity 300ms ease-in-out, transform 300ms ease-in-out'
                    : 'opacity 400ms ease-out, transform 400ms ease-out',
                opacity: isClosing ? 0 : isAnimating ? 1 : 0,
                transform: isClosing
                    ? 'translateY(8px) scale(0.95)'
                    : isAnimating
                        ? 'translateY(0) scale(1)'
                        : 'translateY(8px) scale(0.95)',
            }}
            dir={isRTL ? 'rtl' : 'ltr'}
        >
            <a
                href={releaseLink}
                target="_blank"
                rel="noopener noreferrer"
                className={cn(
                    'block w-full cursor-pointer transition-all duration-200 ease-in-out hover:opacity-95',
                    isRTL ? 'pl-10 pr-4 sm:pl-10 sm:pr-4' : 'pr-10 pl-4 sm:pr-10 sm:pl-4'
                )}
            >
                <div className="flex items-start gap-2 sm:gap-3 py-2.5 sm:py-3">
                    <span className={cn(
                        'flex h-2 w-2 sm:h-2.5 sm:w-2.5 shrink-0 rounded-full mt-1.5 sm:mt-1.5',
                        indicatorColor
                    )} />
                    <div className="flex-1 min-w-0 overflow-hidden">
                        <p className={cn(
                            'text-xs sm:text-sm font-semibold text-foreground/90 leading-tight break-words',
                            isRTL ? 'text-right' : 'text-left'
                        )}>
                            {t('version.newVersionAvailable')}
                        </p>
                        <p className={cn(
                            'text-[11px] sm:text-xs text-foreground/70 mt-0.5 sm:mt-1 leading-relaxed break-words',
                            isRTL ? 'text-right' : 'text-left'
                        )}>
                            {t('version.updateBanner', { current: `v${currentVersion}`, latest: `v${latestVersion}` })}
                        </p>
                        <div className="flex flex-col sm:flex-row items-start sm:items-center gap-1 sm:gap-1.5 mt-1.5">
                            <span className="text-[11px] sm:text-xs text-foreground/60 leading-relaxed break-words sm:whitespace-nowrap">
                                {t('version.updateCommandLabel')}
                            </span>
                            <code
                                className="shrink-0 cursor-pointer rounded-sm bg-muted/50 px-1.5 py-0.5 text-[10px] sm:text-[11px] font-mono transition-colors hover:bg-muted text-foreground/60 break-all sm:break-normal"
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
                    'absolute top-1.5 sm:top-2 h-7 w-7 sm:h-6 sm:w-6 shrink-0 rounded hover:bg-muted/40 transition-all z-10',
                    'text-muted-foreground/70 hover:text-foreground touch-manipulation',
                    isRTL ? 'left-1.5 sm:left-2' : 'right-1.5 sm:right-2'
                )}
                aria-label={t('version.closeBanner')}
            >
                <X className="h-4 w-4 sm:h-3.5 sm:w-3.5" />
            </Button>
        </div>
    )
}

