const NUM_USERS_PER_PAGE_LOCAL_STORAGE_KEY = 'pasarguard-num-users-per-page'
const NUM_ADMINS_PER_PAGE_LOCAL_STORAGE_KEY = 'pasarguard-num-admins-per-page'
const NUM_ITEMS_PER_PAGE_DEFAULT = 10

const USERS_AUTO_REFRESH_INTERVAL_KEY = 'pasarguard-users-auto-refresh-interval'
const DEFAULT_USERS_AUTO_REFRESH_INTERVAL_SECONDS = 0

export const DATE_PICKER_PREFERENCE_KEY = 'pasarguard-date-picker-preference'
export type DatePickerPreference = 'locale' | 'gregorian' | 'persian'
const DEFAULT_DATE_PICKER_PREFERENCE: DatePickerPreference = 'locale'

// Generic function for any table type
export const getItemsPerPageLimitSize = (tableType: 'users' | 'admins' = 'users') => {
  const storageKey = tableType === 'users' ? NUM_USERS_PER_PAGE_LOCAL_STORAGE_KEY : NUM_ADMINS_PER_PAGE_LOCAL_STORAGE_KEY
  const numItemsPerPage = (typeof localStorage !== 'undefined' && localStorage.getItem(storageKey)) || NUM_ITEMS_PER_PAGE_DEFAULT.toString() // this catches `null` values
  return parseInt(numItemsPerPage) || NUM_ITEMS_PER_PAGE_DEFAULT // this catches NaN values
}

export const setItemsPerPageLimitSize = (value: string, tableType: 'users' | 'admins' = 'users') => {
  const storageKey = tableType === 'users' ? NUM_USERS_PER_PAGE_LOCAL_STORAGE_KEY : NUM_ADMINS_PER_PAGE_LOCAL_STORAGE_KEY
  return typeof localStorage !== 'undefined' && localStorage.setItem(storageKey, value)
}

// Legacy functions for backward compatibility
export const getUsersPerPageLimitSize = () => getItemsPerPageLimitSize('users')
export const setUsersPerPageLimitSize = (value: string) => setItemsPerPageLimitSize(value, 'users')

export const getAdminsPerPageLimitSize = () => getItemsPerPageLimitSize('admins')
export const setAdminsPerPageLimitSize = (value: string) => setItemsPerPageLimitSize(value, 'admins')

export const getUsersAutoRefreshIntervalSeconds = () => {
  const storedValue = typeof localStorage !== 'undefined' && localStorage.getItem(USERS_AUTO_REFRESH_INTERVAL_KEY)
  const parsed = storedValue ? parseInt(storedValue, 10) : DEFAULT_USERS_AUTO_REFRESH_INTERVAL_SECONDS
  return Number.isNaN(parsed) ? DEFAULT_USERS_AUTO_REFRESH_INTERVAL_SECONDS : parsed
}

export const setUsersAutoRefreshIntervalSeconds = (seconds: number) => {
  if (typeof localStorage === 'undefined') return
  localStorage.setItem(USERS_AUTO_REFRESH_INTERVAL_KEY, seconds.toString())
}

export const getDatePickerPreference = (): DatePickerPreference => {
  if (typeof localStorage === 'undefined') return DEFAULT_DATE_PICKER_PREFERENCE
  const storedValue = localStorage.getItem(DATE_PICKER_PREFERENCE_KEY)
  if (storedValue === 'locale' || storedValue === 'gregorian' || storedValue === 'persian') {
    return storedValue
  }
  return DEFAULT_DATE_PICKER_PREFERENCE
}

export const setDatePickerPreference = (preference: DatePickerPreference) => {
  if (typeof localStorage === 'undefined') return
  localStorage.setItem(DATE_PICKER_PREFERENCE_KEY, preference)
}
