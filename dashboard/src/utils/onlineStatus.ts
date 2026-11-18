// Same window the API uses for the online filter and the online users count
export const ONLINE_USERS_WINDOW_SECONDS = 120

export const isOnlineWithinWindow = (secondsSinceOnline: number): boolean => secondsSinceOnline <= ONLINE_USERS_WINDOW_SECONDS
