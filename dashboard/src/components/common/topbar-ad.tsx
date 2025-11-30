import { X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { useTheme } from '@/components/common/theme-provider'
import { getGradientByColorTheme } from '@/constants/ThemeGradients'
import useDirDetection from '@/hooks/use-dir-detection'

const TOPBAR_AD_STORAGE_KEY = 'topbar_ad_closed'
const HOURS_TO_HIDE = 24

interface TopbarAdConfig {
  enabled: boolean
  translations: {
    [key: string]: {
      enabled: boolean
      text: string
      textMobile: string
      linkText: string
      linkTextMobile: string
      linkUrl: string
      icon?: string
    }
  }
}


export default function TopbarAd() {
  const { i18n } = useTranslation()
  const { resolvedTheme, colorTheme } = useTheme()
  const dir = useDirDetection()
  const isRTL = dir === 'rtl'
  const [isVisible, setIsVisible] = useState(false)
  const [isClosing, setIsClosing] = useState(false)
  const [config, setConfig] = useState<TopbarAdConfig | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [isAnimating, setIsAnimating] = useState(false)
  const [iconLoaded, setIconLoaded] = useState(false)
  const [iconError, setIconError] = useState(false)

  useEffect(() => {
    const checkShouldFetch = () => {
      const closedTimestamp = localStorage.getItem(TOPBAR_AD_STORAGE_KEY)
      
      if (!closedTimestamp) {
        return true
      }

      const closedTime = parseInt(closedTimestamp, 10)
      const now = Date.now()
      const hoursSinceClose = (now - closedTime) / (1000 * 60 * 60)

      return hoursSinceClose >= HOURS_TO_HIDE
    }

    if (!checkShouldFetch()) {
      setIsLoading(false)
      return
    }

    const loadConfig = async () => {
      try {
        const githubApiUrl = 'https://api.github.com/repos/pasarguard/ads/contents/config'
        const response = await fetch(githubApiUrl, {
          cache: 'no-cache',
        })
        if (response.ok) {
          const apiData = await response.json()
          if (apiData.content && apiData.encoding === 'base64') {
            const base64Content = apiData.content.replace(/\n/g, '')
            const binaryString = atob(base64Content)
            const utf8String = decodeURIComponent(
              Array.from(binaryString, (char) => '%' + ('00' + char.charCodeAt(0).toString(16)).slice(-2)).join('')
            )
            const data = JSON.parse(utf8String)
            setConfig(data)
          } else {
            setConfig(null)
          }
        } else {
          setConfig(null)
        }
      } catch (error) {
        setConfig(null)
      } finally {
        setIsLoading(false)
      }
    }

    if ('requestIdleCallback' in window) {
      requestIdleCallback(() => {
        setIsLoading(true)
        loadConfig()
      }, { timeout: 2000 })
    } else {
      setTimeout(() => {
        setIsLoading(true)
        loadConfig()
      }, 500)
    }
  }, [])

  useEffect(() => {
    if (isLoading || !config || !config.enabled) {
      setIsVisible(false)
      setIsAnimating(false)
      return
    }

    const checkShouldShow = () => {
      const closedTimestamp = localStorage.getItem(TOPBAR_AD_STORAGE_KEY)

      if (!closedTimestamp) {
        setIsVisible(true)
        setTimeout(() => {
          setIsAnimating(true)
        }, 100)
        return
      }

      const closedTime = parseInt(closedTimestamp, 10)
      const now = Date.now()
      const hoursSinceClose = (now - closedTime) / (1000 * 60 * 60)

      if (hoursSinceClose >= HOURS_TO_HIDE) {
        setIsVisible(true)
        setTimeout(() => {
          setIsAnimating(true)
        }, 100)
      }
    }

    checkShouldShow()
  }, [config, isLoading])

  const handleClose = (e: React.MouseEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setIsClosing(true)
    localStorage.setItem(TOPBAR_AD_STORAGE_KEY, Date.now().toString())
    setTimeout(() => {
      setIsVisible(false)
    }, 300)
  }

  const currentLang = i18n.language || 'en'
  const langCode = currentLang.split('-')[0]
  const translations = config?.translations?.[langCode] || config?.translations?.en
  const iconUrl = translations?.icon

  useEffect(() => {
    if (iconUrl) {
      setIconLoaded(false)
      setIconError(false)
    } else {
      setIconError(true)
    }
  }, [iconUrl])

  if (isLoading || !config || !config.enabled) return null
  if (!isVisible) return null
  if (!translations?.enabled) return null

  const handleTopbarClick = (e: React.MouseEvent) => {
    if (translations.linkUrl === '#') {
      e.preventDefault()
    }
  }

  const isDark = resolvedTheme === 'dark'
  const gradientBg = getGradientByColorTheme(colorTheme, isDark, 'ad')

  return (
    <div
      className={cn(
        'relative z-[25] lg:z-30 w-full border-b border-border/40 backdrop-blur-sm',
        gradientBg,
        'overflow-hidden',
        isClosing
          ? 'max-h-0 opacity-0 -translate-y-2 border-0 py-0'
          : 'max-h-32 sm:max-h-36'
      )}
      style={{
        transition: isClosing
          ? 'max-height 300ms ease-in-out, opacity 300ms ease-in-out, transform 300ms ease-in-out, border 300ms ease-in-out, padding 300ms ease-in-out'
          : 'opacity 400ms ease-out, transform 400ms ease-out',
        opacity: isClosing ? 0 : isAnimating ? 1 : 0,
        transform: isClosing ? 'translateY(-8px)' : isAnimating ? 'translateY(0)' : 'translateY(-8px)',
      }}
    >
      <a
        href={translations.linkUrl}
        onClick={handleTopbarClick}
        target="_blank"
        rel="noopener noreferrer"
        className={cn(
          'block w-full cursor-pointer transition-all duration-200 ease-in-out hover:opacity-95 hover:brightness-[1.02]',
          isRTL ? 'pl-10 sm:pl-12' : 'pr-10 sm:pr-12'
        )}
      >
        <div className={cn(
          'mx-auto flex max-w-[1920px] items-center gap-2.5 px-3 py-2.5 sm:px-4',
          isRTL ? 'justify-between' : 'justify-center'
        )}>
          <div className={cn(
            'flex flex-1 items-center gap-2 sm:gap-3 text-xs sm:text-sm min-w-0',
            isRTL ? 'justify-start' : 'justify-center'
          )}>
            {iconUrl && !iconError && (
              <img
                src={iconUrl}
                alt=""
                className="h-5 w-5 shrink-0 object-contain rounded text-foreground/75"
                onLoad={() => setIconLoaded(true)}
                onError={() => setIconError(true)}
                style={{ display: iconLoaded ? 'block' : 'none' }}
              />
            )}
            <span className={cn(
              'text-foreground/75 line-clamp-2 flex-1',
              isRTL ? 'text-center sm:text-right' : 'text-center sm:text-left'
            )}>
              <span className="hidden sm:inline">{translations.text}</span>
              <span className="sm:hidden">{translations.textMobile}</span>
            </span>
          </div>
          <div className="flex items-center shrink-0">
            <span className={cn(
              'shrink-0 hidden sm:inline whitespace-nowrap',
              'px-2.5 py-1 rounded-md text-xs font-medium',
              'bg-primary text-primary-foreground hover:bg-primary/90',
              'transition-colors duration-200 ease-in-out',
              'shadow-sm hover:shadow'
            )}>
              {translations.linkText}
            </span>
            <span className={cn(
              'shrink-0 sm:hidden whitespace-nowrap',
              'px-2 py-0.5 rounded-md text-xs font-medium',
              'bg-primary text-primary-foreground hover:bg-primary/90',
              'transition-colors duration-200 ease-in-out',
              'shadow-sm hover:shadow'
            )}>
              {translations.linkTextMobile}
            </span>
          </div>
        </div>
      </a>

      <Button
        variant="ghost"
        size="icon"
        onClick={handleClose}
        className={cn(
          'absolute top-1/2 -translate-y-1/2',
          isRTL ? 'left-3 sm:left-4' : 'right-3 sm:right-4',
          'h-7 w-7 shrink-0 rounded hover:bg-muted/40 transition-all z-10',
          'text-muted-foreground/70 hover:text-foreground',
          'touch-manipulation'
        )}
        aria-label="Close ad"
      >
        <X className="h-4 w-4" />
      </Button>
    </div>
  )
}

