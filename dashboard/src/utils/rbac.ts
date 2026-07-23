import type { AdminDetails } from '@/service/api'

type PermissionValue = boolean | { scope?: number | string | null } | null | undefined

const getActionPermission = (admin: AdminDetails | null | undefined, resource: string, action: string): PermissionValue => {
  const permissions = admin?.role?.permissions as Record<string, Record<string, PermissionValue> | null | undefined> | null | undefined
  return permissions?.[resource]?.[action]
}

const isScopeNone = (value: PermissionValue) => typeof value === 'object' && value !== null && Number(value.scope) === 0
const isScopeAllValue = (value: PermissionValue) => typeof value === 'object' && value !== null && Number(value.scope) === 2
const READ_ACTIONS = new Set(['read', 'read_simple', 'read_general', 'logs', 'stats'])

export const isOwner = (admin: AdminDetails | null | undefined) => admin?.role?.is_owner === true
export const isLimited = (admin: AdminDetails | null | undefined) => admin?.status === 'limited' || admin?.is_limited === true

export const hasPermission = (admin: AdminDetails | null | undefined, resource: string, action: string) => {
  if (isOwner(admin)) return true
  if (isLimited(admin)) {
    if (admin?.role?.disabled_when_limited) return false
    if (!READ_ACTIONS.has(action)) return false
  }
  const value = getActionPermission(admin, resource, action)
  if (value === true) return true
  if (isScopeNone(value)) return false
  return typeof value === 'object' && value !== null && value.scope != null
}

export const hasScopeAll = (admin: AdminDetails | null | undefined, resource: string, action: string) => {
  if (isOwner(admin)) return true
  if (!hasPermission(admin, resource, action)) return false
  const value = getActionPermission(admin, resource, action)
  return value === true || isScopeAllValue(value)
}

/**
 * Full dashboard pages are exposed by the resource `read` permission only.
 * Simple read permissions are reserved for selector/dropdown endpoints and do
 * not grant page access.
 */
export const canReadResourcePage = (admin: AdminDetails | null | undefined, resource: string) => {
  if (isOwner(admin)) return true
  return hasPermission(admin, resource, 'read')
}

export const canManageResource = (admin: AdminDetails | null | undefined, resource: string, mutationActions: readonly string[] = ['create', 'update', 'delete']) => {
  if (isOwner(admin)) return true
  if (!hasPermission(admin, resource, 'read')) return false
  return mutationActions.some(action => hasPermission(admin, resource, action))
}

export const roleLabel = (admin: AdminDetails | null | undefined) => admin?.role?.name || 'operator'

export const firstAllowedRoute = (admin: AdminDetails | null | undefined) => {
  if (!admin) return '/login'
  if (hasPermission(admin, 'system', 'read')) return '/'
  if (hasPermission(admin, 'users', 'read')) return '/users'
  if (hasPermission(admin, 'nodes', 'stats')) return '/statistics'
  if (canReadResourcePage(admin, 'hosts')) return '/hosts'
  if (canReadResourcePage(admin, 'groups')) return '/groups'
  if (canReadResourcePage(admin, 'admins')) return '/admins'
  if (canReadResourcePage(admin, 'nodes')) return '/nodes'
  if (canReadResourcePage(admin, 'cores')) return '/nodes/cores'
  if (hasPermission(admin, 'nodes', 'logs')) return '/nodes/logs'
  if (canReadResourcePage(admin, 'templates')) return '/templates/user'
  if (canReadResourcePage(admin, 'client_templates')) return '/templates/client'
  return '/settings/theme'
}

export const canAccessRoute = (admin: AdminDetails | null | undefined, pathname: string) => {
  if (!admin) return false
  if (pathname === '/') return hasPermission(admin, 'system', 'read')
  if (pathname.startsWith('/theme') || pathname.startsWith('/settings/theme')) return true
  if (pathname.startsWith('/users')) return hasPermission(admin, 'users', 'read')
  if (pathname.startsWith('/statistics')) return hasPermission(admin, 'nodes', 'stats')
  if (pathname.startsWith('/hosts')) return canReadResourcePage(admin, 'hosts')
  if (pathname.startsWith('/groups')) return canReadResourcePage(admin, 'groups')
  if (pathname === '/templates') return canReadResourcePage(admin, 'templates') || canReadResourcePage(admin, 'client_templates')
  if (pathname.startsWith('/templates/client')) return canReadResourcePage(admin, 'client_templates')
  if (pathname.startsWith('/templates/user')) return canReadResourcePage(admin, 'templates')
  if (pathname.startsWith('/templates')) return false
  if (pathname.startsWith('/admin-roles')) return isOwner(admin)
  if (pathname.startsWith('/admins')) return canReadResourcePage(admin, 'admins')
  if (pathname.startsWith('/api-keys')) return canReadResourcePage(admin, 'api_keys')
  if (pathname === '/nodes/cores') return canReadResourcePage(admin, 'cores')
  if (pathname === '/nodes/cores/new') return hasPermission(admin, 'cores', 'create')
  if (pathname.startsWith('/nodes/cores/')) return hasPermission(admin, 'cores', 'update')
  if (pathname.startsWith('/nodes/wireguard')) return canReadResourcePage(admin, 'cores')
  if (pathname.startsWith('/nodes/logs')) return hasPermission(admin, 'nodes', 'logs')
  if (pathname === '/nodes') return canReadResourcePage(admin, 'nodes')
  if (pathname.startsWith('/nodes')) return canReadResourcePage(admin, 'nodes')
  if (pathname.startsWith('/settings/general')) return hasPermission(admin, 'settings', 'read_general') && hasPermission(admin, 'settings', 'update')
  if (pathname.startsWith('/settings')) {
    if (pathname === '/settings') return true
    return hasPermission(admin, 'settings', 'read') && hasPermission(admin, 'settings', 'update')
  }
  if (pathname.startsWith('/bulk/create') || pathname === '/bulk') return hasPermission(admin, 'users', 'create') && canReadResourcePage(admin, 'templates')
  if (pathname.startsWith('/bulk/groups')) return hasScopeAll(admin, 'users', 'update') && hasPermission(admin, 'groups', 'read')
  if (pathname.startsWith('/bulk/expire') || pathname.startsWith('/bulk/data') || pathname.startsWith('/bulk/proxy')) return hasScopeAll(admin, 'users', 'update')
  return true
}
