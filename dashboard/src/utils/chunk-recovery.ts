import { lazy, type ComponentType } from 'react'

const CHUNK_RELOAD_KEY = 'pasarguard:chunk-reload-at'
const CHUNK_RELOAD_WINDOW_MS = 30_000

// Counts scheduled reloads, so an import can tell whether one was scheduled while it ran.
let scheduledReloads = 0

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

/** Whether `error` means a script or stylesheet chunk could not be fetched, usually because a redeploy removed it. */
export function isChunkLoadError(error: unknown): boolean {
  const errorText = getErrorText(error)

  return (
    /failed to fetch dynamically imported module/i.test(errorText) ||
    /error loading dynamically imported module/i.test(errorText) ||
    /importing a module script failed/i.test(errorText) ||
    // Vite's preload helper; a stale stylesheet is as recoverable as a stale script.
    /unable to preload css/i.test(errorText) ||
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
        .then(keys => Promise.all(keys.map(key => window.caches.delete(key))))
        .catch(() => undefined),
    )
  }

  if ('serviceWorker' in navigator) {
    deletions.push(
      navigator.serviceWorker
        .getRegistrations()
        .then(registrations => Promise.all(registrations.map(registration => registration.unregister())))
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

/**
 * Schedules a page reload for a chunk load error, at most once per reload window. Cache Storage is
 * cleared and service workers are unregistered first. Returns whether a reload was scheduled.
 */
export function recoverFromChunkLoadError(error: unknown): boolean {
  if (!isChunkLoadError(error) || !canReloadForChunkError()) {
    return false
  }

  markChunkReloadAttempt()
  scheduledReloads += 1
  void clearBrowserBuildCaches().finally(() => {
    window.location.reload()
  })

  return true
}

/**
 * Reloads the page when a dynamic import or one of its preloads fails because a chunk is stale. Only
 * errors that start a reload are swallowed; every other failure still reaches the importer.
 */
export function installChunkLoadRecovery(): void {
  window.addEventListener('vite:preloadError', event => {
    const preloadError = 'payload' in event ? (event as Event & { payload: unknown }).payload : (event as CustomEvent<unknown>).detail
    // preventDefault() makes Vite resolve the import with undefined instead of rejecting, so only
    // call it when a reload is on its way. Any other failure has to reject. That covers a module
    // that fails to parse or run, and a chunk error repeated within the reload window. Rejecting
    // lets the route show the real error, not "Cannot read properties of undefined (reading 'default')".
    if (recoverFromChunkLoadError(preloadError ?? event)) {
      event.preventDefault()
    }
  })

  window.addEventListener('unhandledrejection', event => {
    if (recoverFromChunkLoadError(event.reason)) {
      event.preventDefault()
    }
  })
}

/** A promise that never settles. The page reload replaces it. */
function waitForReload<T>(): Promise<T> {
  return new Promise<T>(() => undefined)
}

/**
 * Runs a dynamic import with chunk recovery. Resolves with the module. Never settles while a reload is
 * on its way, so a lazy route stays suspended instead of rendering half-loaded. Rejects with any other
 * error.
 */
export async function importWithChunkRecovery<T>(importer: () => Promise<T>): Promise<T> {
  const reloadsBeforeImport = scheduledReloads

  try {
    const module = await importer()

    // The listener above prevents Vite's preload errors only once a reload is scheduled. Then Vite
    // either resolves the import with undefined (script failed) or loads it without its stylesheet
    // (CSS failed). In both cases keep suspending until the page reloads.
    return scheduledReloads === reloadsBeforeImport ? module : waitForReload<T>()
  } catch (error) {
    // Vite reports each failed preload of an import and then the import itself. The first stale chunk
    // schedules the reload. A later one falls inside the reload window and rejects the import, but the
    // page is still about to reload, so keep suspending for it too.
    if (scheduledReloads !== reloadsBeforeImport || recoverFromChunkLoadError(error)) {
      return waitForReload<T>()
    }

    throw error
  }
}

/** `React.lazy` for a route or dialog chunk, loaded through {@link importWithChunkRecovery}. */
export function lazyWithChunkRecovery<T extends ComponentType<any>>(importer: () => Promise<{ default: T }>) {
  return lazy(() => importWithChunkRecovery(importer))
}
