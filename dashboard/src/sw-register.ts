export function registerSW() {
  if ('serviceWorker' in navigator) {
    const baseUrl = import.meta.env.BASE_URL || '/'

    navigator.serviceWorker
      .register(`${baseUrl}sw.js`)
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
