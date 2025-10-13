const NUM_USERS_PER_PAGE_LOCAL_STORAGE_KEY = 'pasarguard-num-users-per-page'
const NUM_ADMINS_PER_PAGE_LOCAL_STORAGE_KEY = 'pasarguard-num-admins-per-page'
const NUM_ITEMS_PER_PAGE_DEFAULT = 10

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
