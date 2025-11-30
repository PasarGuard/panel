import { DOCUMENTATION } from '@/constants/Project'
import i18n from '@/locales/i18n'

/**
 * Generates a documentation URL for a given page path
 * Format: docs.pasarguard.org/{locale}/panel/{page}
 * Special case: /nodes routes use docs.pasarguard.org/{locale}/node/
 *
 * @param pagePath - The page path (e.g., '/settings', '/users', '/nodes/cores')
 * @returns The full documentation URL
 */
export function getDocsUrl(pagePath: string): string {
  const locale = i18n.language || 'en'
  // Normalize locale (e.g., 'en-US' -> 'en')
  const normalizedLocale = locale.split('-')[0]

  // Special case: node documentation uses /node/ instead of /panel/nodes
  if (pagePath === '/nodes') {
    return `${DOCUMENTATION}/${normalizedLocale}/node/`
  }
  if (pagePath.startsWith('/settings')) {
    console.log(normalizedLocale)
    return `${DOCUMENTATION}/${normalizedLocale}/panel/settings`
  }
  // Map route paths to documentation paths
  const pathMap: Record<string, string> = {
    '/': 'dashboard',
    '/users': 'users',
    '/statistics': 'statistics',
    '/hosts': 'host',
    '/groups': 'groups',
    '/templates': 'user_template',
    '/admins': 'admins',
    '/bulk': 'bulk',
    '/nodes/cores': 'core',
  }

  // Handle nested routes - find the longest matching route
  let mappedPath = ''
  let longestMatch = ''

  for (const [route, docPath] of Object.entries(pathMap)) {
    if (pagePath.startsWith(route) && route.length > longestMatch.length) {
      longestMatch = route
      mappedPath = docPath
    }
  }

  // If we found a match, always use the base path (no sub-routes in docs)
  if (mappedPath) {
    return `${DOCUMENTATION}/${normalizedLocale}/panel/${mappedPath}`
  }

  // If no mapping found, use the last segment of the path
  const segments = pagePath.split('/').filter(Boolean)
  const fallbackPath = segments[segments.length - 1] || 'dashboard'
  return `${DOCUMENTATION}/${normalizedLocale}/panel/${fallbackPath}`
}
