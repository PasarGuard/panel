import { useSyncExternalStore } from 'react'

const desktopQuery = '(min-width: 1024px)'

function subscribe(onChange: () => void) {
  const mediaQuery = window.matchMedia(desktopQuery)
  mediaQuery.addEventListener('change', onChange)
  return () => mediaQuery.removeEventListener('change', onChange)
}

export function useIsMobile() {
  return useSyncExternalStore(
    subscribe,
    () => !window.matchMedia(desktopQuery).matches,
    () => false,
  )
}
