import { useState, useEffect } from 'react'

/**
 * Returns whether the current browser tab is visible to the user.
 * Uses the Page Visibility API — returns true if the tab is visible,
 * false if minimized, hidden, or in a background tab.
 */
export function useDocumentVisibility(): boolean {
  const [isVisible, setIsVisible] = useState<boolean>(() => {
    if (typeof document === 'undefined') return true
    return document.visibilityState === 'visible'
  })

  useEffect(() => {
    const handleVisibilityChange = () => {
      setIsVisible(document.visibilityState === 'visible')
    }
    document.addEventListener('visibilitychange', handleVisibilityChange)
    return () => document.removeEventListener('visibilitychange', handleVisibilityChange)
  }, [])

  return isVisible
}
