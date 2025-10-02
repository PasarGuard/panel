import { useIsFetching, useIsMutating } from '@tanstack/react-query'
import { useEffect, useState, useRef, useMemo, useCallback } from 'react'

interface LoadingState {
  isLoading: boolean
  progress: number | undefined
}

let globalLoadingState: LoadingState = {
  isLoading: false,
  progress: undefined,
}

const loadingStateListeners = new Set<(state: LoadingState) => void>()

const notifyListeners = () => {
  loadingStateListeners.forEach(listener => listener(globalLoadingState))
}

export const setGlobalLoading = (isLoading: boolean) => {
  globalLoadingState.isLoading = isLoading
  if (!isLoading) {
    globalLoadingState.progress = undefined
  }
  notifyListeners()
}

export const setGlobalProgress = (progress: number) => {
  globalLoadingState.progress = progress
  notifyListeners()
}

const IGNORED_QUERY_KEYS = [
  'currentAdmin',
  'token',
  'permissions',
  'acl',
  'heartbeat',
  'ping',
  'health',
  'status',
  'online',
  'connection',
  'websocket',
  'realtime',
  'live',
  'stream',
  'sync',
  'background',
  'polling',
  'interval',
  'cron',
  'scheduled',
  'analytics',
  'metrics',
  'telemetry',
  'tracking',
  'monitoring',
  'admin',
  'system',
]

const IGNORED_MUTATION_KEYS = [
  'auth',
  'refresh',
  'permissions',
  'acl',
  'heartbeat',
  'ping',
  'status',
  'online',
  'realtime',
  'live',
  'stream',
  'sync',
  'background',
  'polling',
  'cron',
  'scheduled',
  'analytics',
  'metrics',
  'telemetry',
  'tracking',
  'monitoring',
  'admin',
  'system',
]

const IGNORED_KEY_PATTERNS = (() => {
  const patterns = new Map<string, RegExp>()
  IGNORED_QUERY_KEYS.forEach(key => {
    patterns.set(key, new RegExp(`(^|/)${key.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}($|/)`, 'i'))
  })
  return patterns
})()

const shouldIgnoreQuery = (() => {
  const cache = new WeakMap<object, boolean>()
  const stringCache = new Map<string, boolean>()

  return (queryKey: string[]): boolean => {
    const cacheKey = queryKey as any
    if (cache.has(cacheKey)) {
      return cache.get(cacheKey)!
    }

    const keyString = queryKey.join('/')
    if (stringCache.has(keyString)) {
      cache.set(cacheKey, stringCache.get(keyString)!)
      return stringCache.get(keyString)!
    }

    const lowerKeyString = keyString.toLowerCase()
    let shouldIgnore = false

    for (const pattern of IGNORED_KEY_PATTERNS.values()) {
      if (pattern.test(lowerKeyString)) {
        shouldIgnore = true
        break
      }
    }

    if (!shouldIgnore) {
      if (lowerKeyString.includes('/api/system/stats')) {
        shouldIgnore = true
      } else if (lowerKeyString.includes('/auth/') || lowerKeyString.includes('/login') || lowerKeyString.includes('/logout')) {
        shouldIgnore = true
      }
    }

    if (stringCache.size > 1000) {
      stringCache.clear()
    }
    stringCache.set(keyString, shouldIgnore)
    cache.set(cacheKey, shouldIgnore)

    return shouldIgnore
  }
})()

const IGNORED_MUTATION_PATTERNS = (() => {
  const patterns = new Map<string, RegExp>()
  IGNORED_MUTATION_KEYS.forEach(key => {
    patterns.set(key, new RegExp(`(^|/)${key.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}($|/)`, 'i'))
  })
  return patterns
})()

const shouldIgnoreMutation = (() => {
  const cache = new WeakMap<object, boolean>()
  const stringCache = new Map<string, boolean>()

  return (mutationKey: string[]): boolean => {
    const cacheKey = mutationKey as any
    if (cache.has(cacheKey)) {
      return cache.get(cacheKey)!
    }

    const keyString = mutationKey.join('/')
    if (stringCache.has(keyString)) {
      cache.set(cacheKey, stringCache.get(keyString)!)
      return stringCache.get(keyString)!
    }

    const lowerKeyString = keyString.toLowerCase()
    let shouldIgnore = false

    for (const pattern of IGNORED_MUTATION_PATTERNS.values()) {
      if (pattern.test(lowerKeyString)) {
        shouldIgnore = true
        break
      }
    }

    if (!shouldIgnore) {
      if (lowerKeyString.includes('/auth/') || lowerKeyString.includes('/login') || lowerKeyString.includes('/logout')) {
        shouldIgnore = true
      }
    }

    if (stringCache.size > 1000) {
      stringCache.clear()
    }
    stringCache.set(keyString, shouldIgnore)
    cache.set(cacheKey, shouldIgnore)

    return shouldIgnore
  }
})()

export const LoadingBarConfig = {
  ignoredQueryKeys: IGNORED_QUERY_KEYS,
  ignoredMutationKeys: IGNORED_MUTATION_KEYS,

  addIgnoredQueryKey: (key: string) => {
    if (!IGNORED_QUERY_KEYS.includes(key)) {
      IGNORED_QUERY_KEYS.push(key)
    }
  },

  addIgnoredMutationKey: (key: string) => {
    if (!IGNORED_MUTATION_KEYS.includes(key)) {
      IGNORED_MUTATION_KEYS.push(key)
    }
  },

  removeIgnoredQueryKey: (key: string) => {
    const index = IGNORED_QUERY_KEYS.indexOf(key)
    if (index > -1) {
      IGNORED_QUERY_KEYS.splice(index, 1)
    }
  },

  removeIgnoredMutationKey: (key: string) => {
    const index = IGNORED_MUTATION_KEYS.indexOf(key)
    if (index > -1) {
      IGNORED_MUTATION_KEYS.splice(index, 1)
    }
  },
}

export const useTopLoadingBar = () => {
  const [loadingState, setLoadingState] = useState<LoadingState>(globalLoadingState)
  const [isInitialLoad, setIsInitialLoad] = useState(true)
  const initialLoadTimeoutRef = useRef<NodeJS.Timeout>()
  const debounceTimeoutRef = useRef<NodeJS.Timeout>()
  const maxTimeoutRef = useRef<NodeJS.Timeout>()

  const queryPredicate = useCallback((query: any) => !shouldIgnoreQuery(query.queryKey), [])
  const mutationPredicate = useCallback((mutation: any) => !shouldIgnoreMutation(mutation.options?.mutationKey || []), [])

  const isFetching = useIsFetching({ predicate: queryPredicate })
  const isMutating = useIsMutating({ predicate: mutationPredicate })

  const resetInitialLoad = useCallback(() => {
    setIsInitialLoad(true)
  }, [])

  const listener = useCallback((state: LoadingState) => {
    setLoadingState(state)
  }, [])

  useEffect(() => {
    loadingStateListeners.add(listener)
    ;(window as any).resetLoadingBarInitialState = resetInitialLoad

    return () => {
      loadingStateListeners.delete(listener)
    }
  }, [listener, resetInitialLoad])

  useEffect(() => {
    const isLoading = isFetching > 0 || isMutating > 0

    if (debounceTimeoutRef.current) {
      clearTimeout(debounceTimeoutRef.current)
    }

    debounceTimeoutRef.current = setTimeout(() => {
      if (isLoading && !globalLoadingState.isLoading) {
        setGlobalLoading(true)
        if (initialLoadTimeoutRef.current) {
          clearTimeout(initialLoadTimeoutRef.current)
          initialLoadTimeoutRef.current = undefined
        }

        if (maxTimeoutRef.current) {
          clearTimeout(maxTimeoutRef.current)
        }
        maxTimeoutRef.current = setTimeout(() => {
          if (globalLoadingState.isLoading) {
            setGlobalLoading(false)
          }
          maxTimeoutRef.current = undefined
        }, 3000)
      } else if (!isLoading && globalLoadingState.isLoading) {
        if (maxTimeoutRef.current) {
          clearTimeout(maxTimeoutRef.current)
          maxTimeoutRef.current = undefined
        }

        const delay = isInitialLoad ? 800 : 100

        initialLoadTimeoutRef.current = setTimeout(() => {
          setGlobalLoading(false)
          if (isInitialLoad) {
            setIsInitialLoad(false)
          }
          initialLoadTimeoutRef.current = undefined
        }, delay)
      }
    }, 16)

    return () => {
      if (debounceTimeoutRef.current) {
        clearTimeout(debounceTimeoutRef.current)
      }
    }
  }, [isFetching, isMutating, isInitialLoad])

  useEffect(() => {
    return () => {
      if (initialLoadTimeoutRef.current) {
        clearTimeout(initialLoadTimeoutRef.current)
      }
      if (debounceTimeoutRef.current) {
        clearTimeout(debounceTimeoutRef.current)
      }
      if (maxTimeoutRef.current) {
        clearTimeout(maxTimeoutRef.current)
      }
    }
  }, [])

  const startLoading = useCallback(() => {
    setGlobalLoading(true)
    if (initialLoadTimeoutRef.current) {
      clearTimeout(initialLoadTimeoutRef.current)
      initialLoadTimeoutRef.current = undefined
    }
  }, [])

  const stopLoading = useCallback(() => {
    setGlobalLoading(false)
    if (maxTimeoutRef.current) {
      clearTimeout(maxTimeoutRef.current)
      maxTimeoutRef.current = undefined
    }
  }, [])

  const setProgress = useCallback((progress: number) => {
    setGlobalProgress(progress)
  }, [])

  return useMemo(
    () => ({
      isLoading: loadingState.isLoading,
      progress: loadingState.progress,
      startLoading,
      stopLoading,
      setProgress,
    }),
    [loadingState.isLoading, loadingState.progress, startLoading, stopLoading, setProgress],
  )
}

export const useLoadingBar = () => {
  const startLoading = () => setGlobalLoading(true)
  const stopLoading = () => setGlobalLoading(false)
  const setProgress = (progress: number) => setGlobalProgress(progress)

  return {
    startLoading,
    stopLoading,
    setProgress,
  }
}
