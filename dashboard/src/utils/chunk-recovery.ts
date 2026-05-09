import { lazy, type ComponentType } from 'react'

const CHUNK_RELOAD_KEY = 'pasarguard:chunk-reload-at'
const CHUNK_RELOAD_WINDOW_MS = 30_000

function getErrorText(error: unknown): string {
  if (typeof error === 'string') {
    return error
  }

  if (error instanceof Error) {
    return `${error.name} ${error.message}`.trim()
  }

  if (typeof error === 'object' && error !== null) {
    const maybeMessage = 'message' in error ? String(error.message) : ''
    const maybeType = 'type' in error ? String(error.type) : ''
    return `${maybeType} ${maybeMessage}`.trim()
  }

  return ''
}

export function isChunkLoadError(error: unknown): boolean {
  const errorText = getErrorText(error)

  return (
    /failed to fetch dynamically imported module/i.test(errorText) ||
    /error loading dynamically imported module/i.test(errorText) ||
    /importing a module script failed/i.test(errorText) ||
    /loading chunk \d+ failed/i.test(errorText) ||
    /chunkloaderror/i.test(errorText)
  )
}

export async function clearBrowserBuildCaches(): Promise<void> {
  const deletions: Promise<unknown>[] = []

  if ('caches' in window) {
    deletions.push(
      window.caches
        .keys()
        .then((keys) => Promise.all(keys.map((key) => window.caches.delete(key))))
        .catch(() => undefined),
    )
  }

  if ('serviceWorker' in navigator) {
    deletions.push(
      navigator.serviceWorker
        .getRegistrations()
        .then((registrations) => Promise.all(registrations.map((registration) => registration.unregister())))
        .catch(() => undefined),
    )
  }

  await Promise.all(deletions)
}

function canReloadForChunkError(): boolean {
  try {
    const lastReloadAt = Number(window.sessionStorage.getItem(CHUNK_RELOAD_KEY) || 0)

    return Date.now() - lastReloadAt > CHUNK_RELOAD_WINDOW_MS
  } catch {
    return true
  }
}

function markChunkReloadAttempt(): void {
  try {
    window.sessionStorage.setItem(CHUNK_RELOAD_KEY, String(Date.now()))
  } catch {
    // Ignore storage failures; the reload is still the best recovery path.
  }
}

export function recoverFromChunkLoadError(error: unknown): boolean {
  if (!isChunkLoadError(error) || !canReloadForChunkError()) {
    return false
  }

  markChunkReloadAttempt()
  void clearBrowserBuildCaches().finally(() => {
    window.location.reload()
  })

  return true
}

export function installChunkLoadRecovery(): void {
  window.addEventListener('vite:preloadError', (event) => {
    event.preventDefault()
    const preloadError =
      'payload' in event ? (event as Event & { payload: unknown }).payload : (event as CustomEvent<unknown>).detail
    recoverFromChunkLoadError(preloadError ?? event)
  })

  window.addEventListener('unhandledrejection', (event) => {
    if (recoverFromChunkLoadError(event.reason)) {
      event.preventDefault()
    }
  })
}

export function lazyWithChunkRecovery<T extends ComponentType<any>>(
  importer: () => Promise<{ default: T }>,
) {
  return lazy(async () => {
    try {
      return await importer()
    } catch (error) {
      if (recoverFromChunkLoadError(error)) {
        return new Promise<{ default: T }>(() => undefined)
      }

      throw error
    }
  })
}
