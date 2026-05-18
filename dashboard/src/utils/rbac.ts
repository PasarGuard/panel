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
 * A management page should only be shown when the admin can both view AND
 * mutate the resource. Plain `read` on a resource is often only used by forms
 * and selectors (e.g. picking groups while creating a user) and does not
 * justify exposing the dedicated page in the sidebar / as a navigable route.
 */
export const canManageResource = (
  admin: AdminDetails | null | undefined,
  resource: string,
  mutationActions: readonly string[] = ['create', 'update', 'delete'],
) => {
  if (isOwner(admin)) return true
  if (!hasPermission(admin, resource, 'read')) return false
  return mutationActions.some(action => hasPermission(admin, resource, action))
}

export const roleLabel = (admin: AdminDetails | null | undefined) => admin?.role?.name || 'operator'

export const firstAllowedRoute = (admin: AdminDetails | null | undefined) => {
  if (!admin) return '/login'
  if (hasPermission(admin, 'system', 'read')) return '/'
  if (hasPermission(admin, 'users', 'read')) return '/users'
  return '/settings/theme'
}

export const canAccessRoute = (admin: AdminDetails | null | undefined, pathname: string) => {
  if (!admin) return false
  if (pathname === '/') return hasPermission(admin, 'system', 'read')
  if (pathname.startsWith('/theme') || pathname.startsWith('/settings/theme')) return true
  if (pathname.startsWith('/users')) return hasPermission(admin, 'users', 'read')
  if (pathname.startsWith('/statistics')) return hasPermission(admin, 'nodes', 'stats')
  if (pathname.startsWith('/hosts')) return canManageResource(admin, 'hosts', ['create', 'update'])
  if (pathname.startsWith('/groups')) return canManageResource(admin, 'groups')
  if (pathname.startsWith('/templates/client')) return canManageResource(admin, 'client_templates')
  if (pathname.startsWith('/templates')) return canManageResource(admin, 'templates')
  if (pathname.startsWith('/admin-roles')) return isOwner(admin)
  if (pathname.startsWith('/admins')) return canManageResource(admin, 'admins')
  if (pathname.startsWith('/nodes/cores')) return canManageResource(admin, 'cores')
  if (pathname.startsWith('/nodes/logs')) return hasPermission(admin, 'nodes', 'logs')
  if (pathname.startsWith('/nodes')) return canManageResource(admin, 'nodes', ['create', 'update', 'delete', 'reconnect', 'update_core'])
  if (pathname.startsWith('/settings/general')) return hasPermission(admin, 'settings', 'read_general') && hasPermission(admin, 'settings', 'update')
  if (pathname.startsWith('/settings')) {
    if (pathname === '/settings') return true
    return hasPermission(admin, 'settings', 'read') && hasPermission(admin, 'settings', 'update')
  }
  if (pathname.startsWith('/bulk/create') || pathname === '/bulk') return hasPermission(admin, 'users', 'create')
  if (pathname.startsWith('/bulk/groups')) return hasScopeAll(admin, 'users', 'update') && hasPermission(admin, 'groups', 'read')
  if (pathname.startsWith('/bulk/expire') || pathname.startsWith('/bulk/data') || pathname.startsWith('/bulk/proxy') || pathname.startsWith('/bulk/wireguard')) return hasScopeAll(admin, 'users', 'update')
  return true
}
