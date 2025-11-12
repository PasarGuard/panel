import { useAdmin } from '@/hooks/use-admin'
import { useEffect, useRef } from 'react'
import { useLocation, useNavigate } from 'react-router'

export default function RouteGuard({ children }: { children: React.ReactNode }) {
  const { admin } = useAdmin()
  const location = useLocation()
  const navigate = useNavigate()
  const is_sudo = admin?.is_sudo || false
  const hasNavigatedRef = useRef(false)

  useEffect(() => {
    if (!admin) {
      hasNavigatedRef.current = false
      return // Wait for admin data to load
    }

    if (!is_sudo) {
      const currentPath = location.pathname

      // Define allowed routes for non-sudo admins
      const allowedRoutes = ['/', '/users', '/settings', '/settings/theme']
      const isAllowedRoute = allowedRoutes.some(route => currentPath === route || (route === '/settings' && currentPath.startsWith('/settings/theme')))

      // If current route is allowed, don't redirect
      if (isAllowedRoute) {
        hasNavigatedRef.current = false
        return
      }

      // Prevent multiple navigations for the same route change
      if (hasNavigatedRef.current) {
        return
      }

      // Define restricted routes for non-sudo admins
      const restrictedRoutes = ['/statistics', '/hosts', '/groups', '/templates', '/admins', '/nodes']
      const isRestrictedRoute = restrictedRoutes.some(route => currentPath.startsWith(route))

      if (isRestrictedRoute) {
        hasNavigatedRef.current = true
        navigate('/users', { replace: true })
        return
      }

      // Handle settings routes
      if (currentPath === '/settings') {
        hasNavigatedRef.current = true
        navigate('/settings/theme', { replace: true })
        return
      }

      // Redirect from restricted settings pages
      const restrictedSettingsRoutes = ['/settings/general', '/settings/notifications', '/settings/subscriptions', '/settings/telegram', '/settings/discord', '/settings/webhook', '/settings/cleanup']

      if (restrictedSettingsRoutes.includes(currentPath)) {
        // Redirecting non-sudo admin from restricted settings
        hasNavigatedRef.current = true
        navigate('/settings/theme', { replace: true })
        return
      }
    } else {
      hasNavigatedRef.current = false
    }
  }, [admin, is_sudo, location.pathname, navigate])

  // Reset navigation flag when pathname changes (after navigation completes)
  useEffect(() => {
    hasNavigatedRef.current = false
  }, [location.pathname])

  return <>{children}</>
}
