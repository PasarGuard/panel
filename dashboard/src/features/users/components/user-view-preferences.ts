export const USER_FIELDS = [
  { id: 'created_at', sort: 'created_at' },
  { id: 'edit_at', sort: 'edit_at' },
  { id: 'remaining_traffic', sort: undefined },
  { id: 'groups', sort: undefined },
  { id: 'note', sort: undefined },
  { id: 'hwid_count', sort: 'hwid_count' },
  { id: 'hwid_limit', sort: undefined },
  { id: 'data_limit_reset_strategy', sort: undefined },
  { id: 'on_hold_timeout', sort: undefined },
  { id: 'on_hold_expire_duration', sort: undefined },
  { id: 'auto_delete_in_days', sort: undefined },
  { id: 'next_plan', sort: undefined },
] as const

export type UserFieldId = (typeof USER_FIELDS)[number]['id']
export function availableUserFields(canReadHwids: boolean): UserFieldId[] {
  return USER_FIELDS.filter(field => field.id !== 'hwid_count' || canReadHwids).map(field => field.id)
}

export type UserViewPreferences = {
  version: 2
  desktop: UserFieldId[]
  mobileExpanded: UserFieldId[]
  showCreatedBy: boolean
}

export const defaultUserView = (): UserViewPreferences => ({
  version: 2,
  desktop: [],
  mobileExpanded: [],
  showCreatedBy: true,
})

const knownFields = new Set<string>(USER_FIELDS.map(field => field.id))
const cleanFields = (value: unknown): UserFieldId[] => {
  if (!Array.isArray(value)) return []
  return [...new Set(value.filter((id): id is UserFieldId => typeof id === 'string' && knownFields.has(id)))]
}

// Keep the original cells in place and the usage/actions cell at the end.
export function userColumnOrder(fields: UserFieldId[], allowed: UserFieldId[]): string[] {
  return ['select', 'username', 'status', ...cleanFields(fields).filter(id => allowed.includes(id)), 'details', 'chevron']
}

export function normalizeUserView(value: unknown): UserViewPreferences {
  if (!value || typeof value !== 'object') return defaultUserView()
  const saved = value as Record<string, unknown>
  if (saved.version !== 1 && saved.version !== 2) return defaultUserView()
  return {
    version: 2,
    desktop: cleanFields(saved.desktop),
    mobileExpanded: cleanFields(saved.mobileExpanded),
    showCreatedBy: saved.version === 1 ? !Array.isArray(saved.desktop) || saved.desktop.includes('creator') : typeof saved.showCreatedBy === 'boolean' ? saved.showCreatedBy : true,
  }
}

// Browser origin isolates panels; the account suffix isolates administrators on a shared browser.
export const userViewStorageKey = (username: string) => `pasarguard-users-view:${encodeURIComponent(username)}`

export function readUserView(username: string): UserViewPreferences {
  try {
    const raw = localStorage.getItem(userViewStorageKey(username))
    if (raw !== null) return normalizeUserView(JSON.parse(raw))
    const defaults = defaultUserView()
    if (localStorage.getItem('pasarguard-users-show-created-by') === 'false') {
      defaults.showCreatedBy = false
    }
    return defaults
  } catch {
    return defaultUserView()
  }
}

export function writeUserView(username: string, value: UserViewPreferences): boolean {
  try {
    localStorage.setItem(userViewStorageKey(username), JSON.stringify(normalizeUserView(value)))
    return true
  } catch {
    return false
  }
}
