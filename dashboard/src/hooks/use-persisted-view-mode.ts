import { useCallback, useEffect, useState } from 'react'
import { ViewMode } from '@/components/common/view-toggle'

export function usePersistedViewMode(storageKey: string, defaultMode: ViewMode = 'grid') {
  const [viewMode, setViewModeState] = useState<ViewMode>(() => {
    if (typeof window === 'undefined') return defaultMode
    const savedMode = window.localStorage.getItem(storageKey)
    return savedMode === 'list' || savedMode === 'grid' ? savedMode : defaultMode
  })

  useEffect(() => {
    if (typeof window === 'undefined') return
    window.localStorage.setItem(storageKey, viewMode)
  }, [storageKey, viewMode])

  const setViewMode = useCallback((mode: ViewMode) => {
    setViewModeState(mode)
  }, [])

  return [viewMode, setViewMode] as const
}
