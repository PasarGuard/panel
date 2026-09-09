import { expect, test } from 'bun:test'
import type { AdminDetails } from '@/service/api'
import { canAccessRoute, canUseClientWorkspace, clientTemplateLibraryPath, firstAllowedRoute } from './rbac'

const admin = (permissions: Record<string, unknown>) => ({ username: 'operator', is_disabled: false, is_limited: false, role: { is_owner: false, permissions } }) as unknown as AdminDetails

test('legacy template readers retain the existing page and default route without settings access', () => {
  const reader = admin({ client_templates: { read: true } })
  expect(canUseClientWorkspace(reader)).toBe(false)
  expect(clientTemplateLibraryPath(reader)).toBe('/templates/client')
  expect(firstAllowedRoute(reader)).toBe('/templates/client')
  expect(canAccessRoute(reader, '/templates/client')).toBe(true)
  expect(canAccessRoute(reader, '/client-settings/configurations')).toBe(false)
})
test('workspace requires full template and settings read while simple access remains limited to selectors', () => {
  const reader = admin({ client_templates: { read: true }, settings: { read: true } })
  expect(canUseClientWorkspace(reader)).toBe(true)
  expect(clientTemplateLibraryPath(reader)).toBe('/client-settings/configurations')
  expect(firstAllowedRoute(reader)).toBe('/client-settings/applications')
  expect(canAccessRoute(reader, '/client-settings/applications/happ')).toBe(true)
  const simple = admin({ client_templates: { read_simple: true }, settings: { read: true } })
  expect(canUseClientWorkspace(simple)).toBe(false)
  expect(canAccessRoute(simple, '/templates/client')).toBe(false)
})
