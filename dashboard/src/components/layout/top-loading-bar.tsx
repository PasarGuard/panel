import { useEffect, useRef, useMemo, useState, memo } from 'react'
import { useLocation } from 'react-router'
import { useTheme } from '@/components/common/theme-provider'
import LoadingBar from 'react-top-loading-bar'

const shouldIgnoreRoute = (pathname: string): boolean => {
  const IGNORED_ROUTE_PATTERNS = [/^\/settings\/(general|notifications|subscriptions|telegram|discord|webhook|cleanup|theme)$/, /^\/nodes\/(cores|logs)$/]

  const shouldIgnore = IGNORED_ROUTE_PATTERNS.some(pattern => pattern.test(pathname))

  if (process.env.NODE_ENV === 'development') {
  }

  return shouldIgnore
}

let lastLocation = ''

declare global {
  interface Window {
    resetLoadingBarInitialState?: () => void
  }
}

interface TopLoadingBarProps {
  height?: number
  color?: string
  shadow?: boolean
  className?: string
}

function TopLoadingBar({ height = 3, color, shadow = false, className = '' }: TopLoadingBarProps) {
  const ref = useRef<any>(null)
  const maxTimeoutRef = useRef<NodeJS.Timeout>()
  const { resolvedTheme } = useTheme()
  const location = useLocation()

  const [themeKey, setThemeKey] = useState(resolvedTheme)
  const [colorThemeKey, setColorThemeKey] = useState(() => {
    try {
      return localStorage.getItem('color-theme') || 'default'
    } catch {
      return 'default'
    }
  })

  useEffect(() => {
    setThemeKey(resolvedTheme)
  }, [resolvedTheme])

  useEffect(() => {
    const handleStorageChange = (e: StorageEvent) => {
      if (e.key === 'color-theme') {
        setColorThemeKey(e.newValue || 'default')
      }
    }

    window.addEventListener('storage', handleStorageChange)

    const checkColorTheme = () => {
      try {
        const current = localStorage.getItem('color-theme') || 'default'
        if (current !== colorThemeKey) {
          setColorThemeKey(current)
        }
      } catch {
        // ignore
      }
    }

    const interval = setInterval(checkColorTheme, 100)

    return () => {
      window.removeEventListener('storage', handleStorageChange)
      clearInterval(interval)
    }
  }, [colorThemeKey])

  const pathname = useMemo(() => location.pathname, [location.pathname])

  const primaryColor = useMemo(() => {
    if (color) return color

    const root = document.documentElement
    const primaryColorValue = getComputedStyle(root).getPropertyValue('--primary').trim()

    if (primaryColorValue) {
      const hslValues = primaryColorValue.split(' ').map(v => parseFloat(v))
      if (hslValues.length === 3) {
        const [h, s, l] = hslValues
        const hNorm = h / 360
        const sNorm = s / 100
        const lNorm = l / 100

        const c = (1 - Math.abs(2 * lNorm - 1)) * sNorm
        const x = c * (1 - Math.abs(((hNorm * 6) % 2) - 1))
        const m = lNorm - c / 2

        let r, g, b
        if (hNorm < 1 / 6) {
          ;[r, g, b] = [c, x, 0]
        } else if (hNorm < 2 / 6) {
          ;[r, g, b] = [x, c, 0]
        } else if (hNorm < 3 / 6) {
          ;[r, g, b] = [0, c, x]
        } else if (hNorm < 4 / 6) {
          ;[r, g, b] = [0, x, c]
        } else if (hNorm < 5 / 6) {
          ;[r, g, b] = [x, 0, c]
        } else {
          ;[r, g, b] = [c, 0, x]
        }

        const rFinal = Math.round((r + m) * 255)
        const gFinal = Math.round((g + m) * 255)
        const bFinal = Math.round((b + m) * 255)

        return `rgb(${rFinal}, ${gFinal}, ${bFinal})`
      }
    }

    return resolvedTheme === 'dark' ? '#3b82f6' : '#2563eb'
  }, [color, resolvedTheme, themeKey, colorThemeKey])

  useEffect(() => {
    const currentPath = location.pathname + location.search

    if (currentPath !== lastLocation && lastLocation !== '') {
      if ((window as any).resetLoadingBarInitialState) {
        ;(window as any).resetLoadingBarInitialState()
      }
    }

    lastLocation = currentPath

    if (shouldIgnoreRoute(pathname)) {
      // For ignored routes, ensure any existing loading bar is completed immediately
      if (ref.current) {
        ref.current.complete()
      }
      // Clear any pending timeout
      if (maxTimeoutRef.current) {
        clearTimeout(maxTimeoutRef.current)
        maxTimeoutRef.current = undefined
      }
    } else if (ref.current) {
      // Start loading bar on route change with continuous animation
      ref.current.continuousStart()

      // Set timeout to complete the loading bar after a longer delay
      // This gives time for the animation to progress and the page to render
      if (maxTimeoutRef.current) {
        clearTimeout(maxTimeoutRef.current)
      }

      maxTimeoutRef.current = setTimeout(() => {
        if (ref.current) {
          ref.current.complete()
        }
        maxTimeoutRef.current = undefined
      }, 800)
    }

    return () => {
      if (maxTimeoutRef.current) {
        clearTimeout(maxTimeoutRef.current)
      }
    }
  }, [pathname, location.search])

  useEffect(() => {
    return () => {
      if (maxTimeoutRef.current) {
        clearTimeout(maxTimeoutRef.current)
      }
    }
  }, [])

  const loadingBarProps = useMemo(
    () => ({
      ref,
      color: primaryColor,
      height,
      shadow,
      className: `${className} pointer-events-none [direction:ltr] !top-[env(safe-area-inset-top)]`,
      waitingTime: 0,
      transitionTime: 200,
    }),
    [primaryColor, height, shadow, className],
  )

  return (
    <div dir="ltr">
      <LoadingBar {...loadingBarProps} />
    </div>
  )
}

export { TopLoadingBar }

export default memo(TopLoadingBar)
