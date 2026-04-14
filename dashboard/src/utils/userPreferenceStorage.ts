const NUM_USERS_PER_PAGE_LOCAL_STORAGE_KEY = 'pasarguard-num-users-per-page'
const NUM_ADMINS_PER_PAGE_LOCAL_STORAGE_KEY = 'pasarguard-num-admins-per-page'
const NUM_ITEMS_PER_PAGE_DEFAULT = 10

const USERS_AUTO_REFRESH_INTERVAL_KEY = 'pasarguard-users-auto-refresh-interval'
const DEFAULT_USERS_AUTO_REFRESH_INTERVAL_SECONDS = 15
const USERS_SHOW_CREATED_BY_KEY = 'pasarguard-users-show-created-by'
const DEFAULT_USERS_SHOW_CREATED_BY = true
const USERS_SHOW_SELECTION_CHECKBOX_KEY = 'pasarguard-users-show-selection-checkbox'
const DEFAULT_USERS_SHOW_SELECTION_CHECKBOX = true
const CHART_VIEW_TYPE_KEY = 'pasarguard-chart-view-type'

export const DATE_PICKER_PREFERENCE_KEY = 'pasarguard-date-picker-preference'
export type DatePickerPreference = 'locale' | 'gregorian' | 'persian'
const DEFAULT_DATE_PICKER_PREFERENCE: DatePickerPreference = 'locale'

export const CHART_VIEW_TYPE_CHANGE_EVENT = 'pasarguard-chart-view-type-change'
export type ChartViewType = 'bar' | 'area'
const DEFAULT_CHART_VIEW_TYPE: ChartViewType = 'bar'

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

export const getUsersShowCreatedBy = () => {
  if (typeof localStorage === 'undefined') return DEFAULT_USERS_SHOW_CREATED_BY
  const storedValue = localStorage.getItem(USERS_SHOW_CREATED_BY_KEY)
  if (storedValue === null) return DEFAULT_USERS_SHOW_CREATED_BY
  return storedValue === 'true'
}

export const setUsersShowCreatedBy = (value: boolean) => {
  if (typeof localStorage === 'undefined') return
  localStorage.setItem(USERS_SHOW_CREATED_BY_KEY, value ? 'true' : 'false')
}

export const getUsersShowSelectionCheckbox = () => {
  if (typeof localStorage === 'undefined') return DEFAULT_USERS_SHOW_SELECTION_CHECKBOX
  const storedValue = localStorage.getItem(USERS_SHOW_SELECTION_CHECKBOX_KEY)
  if (storedValue === null) return DEFAULT_USERS_SHOW_SELECTION_CHECKBOX
  return storedValue === 'true'
}

export const setUsersShowSelectionCheckbox = (value: boolean) => {
  if (typeof localStorage === 'undefined') return
  localStorage.setItem(USERS_SHOW_SELECTION_CHECKBOX_KEY, value ? 'true' : 'false')
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

export const getChartViewTypePreference = (): ChartViewType => {
  if (typeof localStorage === 'undefined') return DEFAULT_CHART_VIEW_TYPE
  const storedValue = localStorage.getItem(CHART_VIEW_TYPE_KEY)
  if (storedValue === 'bar' || storedValue === 'area') {
    return storedValue
  }
  return DEFAULT_CHART_VIEW_TYPE
}

export const setChartViewTypePreference = (viewType: ChartViewType) => {
  if (typeof localStorage === 'undefined') return
  localStorage.setItem(CHART_VIEW_TYPE_KEY, viewType)
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent<ChartViewType>(CHART_VIEW_TYPE_CHANGE_EVENT, { detail: viewType }))
  }
}
