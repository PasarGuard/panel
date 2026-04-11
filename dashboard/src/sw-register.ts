/**
 * Service worker script URL must live under the same path prefix the app is mounted at.
 * When the bundle was built with `base: '/'` but the app is served under e.g. `/dashboard/`,
 * `import.meta.env.BASE_URL` is wrong; infer the mount prefix from `location.pathname`
 * (hash routes do not change pathname, only the hash).
 */
function getServiceWorkerBasePath(): string {
  const raw = import.meta.env.BASE_URL || '/'
  const fromBuild = raw.endsWith('/') ? raw : `${raw}/`

  if (fromBuild !== '/') {
    return fromBuild
  }

  const segments = window.location.pathname.split('/').filter(Boolean)
  if (segments.length === 0) {
    return '/'
  }
  return `/${segments[0]}/`
}

export function registerSW() {
  if ('serviceWorker' in navigator) {
    const basePath = getServiceWorkerBasePath()

    navigator.serviceWorker
      .register(`${basePath}sw.js`)
      .then(registration => {
        setInterval(
          () => {
            registration.update()
          },
          60 * 60 * 1000,
        )

        let refreshing = false
        navigator.serviceWorker.addEventListener('controllerchange', () => {
          if (!refreshing) {
            refreshing = true
            window.location.reload()
          }
        })
      })
      .catch(registrationError => {
        console.error('Service Worker registration failed:', registrationError)
      })
  }
}