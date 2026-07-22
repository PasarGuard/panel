import { Alert, AlertDescription } from '@/components/ui/alert'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Command, CommandEmpty, CommandInput, CommandItem, CommandList } from '@/components/ui/command'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { DatePicker } from '@/components/common/date-picker'
import { formatDateByLocale } from '@/utils/datePickerUtils'
import useDirDetection from '@/hooks/use-dir-detection'
import { cn } from '@/lib/utils'
import { useClearUsageData, useDeleteExpiredUsers, useGetAdmins, useGetCurrentAdmin, useResetUsersDataUsage, type AdminDetails, type UsageTable } from '@/service/api'
import { useDebouncedSearch } from '@/hooks/use-debounced-search'
import { AlertTriangle, Check, ChevronDown, Database, Loader2, RotateCcw, Server, Trash2, UserCog, UserRound } from 'lucide-react'
import { endOfDay, startOfDay } from 'date-fns'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { hasScopeAll, isOwner, roleLabel } from '@/utils/rbac'

const PAGE_SIZE = 20
type CleanupDeleteTarget = 'expired' | 'limited'

export default function CleanupSettings() {
  const { t, i18n } = useTranslation()
  const dir = useDirDetection()
  const isPersianLocale = i18n.language === 'fa'
  const [deleteTarget, setDeleteTarget] = useState<CleanupDeleteTarget>('expired')
  const [expiredAfter, setExpiredAfter] = useState<Date | undefined>()
  const [expiredBefore, setExpiredBefore] = useState<Date | undefined>()
  const [selectedTable, setSelectedTable] = useState<string>('')
  const [clearDataAfter, setClearDataAfter] = useState<Date | undefined>()
  const [clearDataBefore, setClearDataBefore] = useState<Date | undefined>()

  const { data: currentAdmin } = useGetCurrentAdmin()
  const canTargetAllAdmins = hasScopeAll(currentAdmin, 'users', 'delete') || hasScopeAll(currentAdmin, 'users', 'update')

  // Admin search state
  const [selectedAdmin, setSelectedAdmin] = useState<AdminDetails | undefined>()
  const [offset, setOffset] = useState(0)
  const [admins, setAdmins] = useState<AdminDetails[]>([])
  const [hasMore, setHasMore] = useState(true)
  const [isLoading, setIsLoading] = useState(false)
  const [dropdownOpen, setDropdownOpen] = useState(false)
  const listRef = useRef<HTMLDivElement>(null)
  const { debouncedSearch: adminSearch, setSearch: setAdminSearchInput } = useDebouncedSearch('', 300)

  // Handle debounced search side effects
  useEffect(() => {
    setOffset(0)
    setAdmins([])
    setHasMore(true)
  }, [adminSearch])

  let usernameParam: string | undefined = undefined
  if (adminSearch && adminSearch !== 'system' && adminSearch !== currentAdmin?.username) {
    usernameParam = adminSearch
  }

  const { data: fetchedAdminsResponse } = useGetAdmins(
    {
      limit: PAGE_SIZE,
      offset,
      ...(usernameParam ? { username: usernameParam } : {}),
    },
    {
      query: {
        enabled: canTargetAllAdmins,
      },
    },
  )

  useEffect(() => {
    if (fetchedAdminsResponse) {
      const fetchedAdmins = fetchedAdminsResponse.admins || []
      setAdmins(prev => (offset === 0 ? fetchedAdmins : [...prev, ...fetchedAdmins]))
      setHasMore(fetchedAdmins.length === PAGE_SIZE)
      setIsLoading(false)
    }
  }, [fetchedAdminsResponse, offset])

  const handleScroll = useCallback(() => {
    if (!listRef.current || isLoading || !hasMore) return
    const { scrollTop, scrollHeight, clientHeight } = listRef.current
    if (scrollHeight - scrollTop - clientHeight < 100) {
      setIsLoading(true)
      setOffset(prev => prev + PAGE_SIZE)
    }
  }, [isLoading, hasMore])

  useEffect(() => {
    const el = listRef.current
    if (!el) return
    el.addEventListener('scroll', handleScroll)
    return () => el.removeEventListener('scroll', handleScroll)
  }, [handleScroll])

  // API Mutations
  const deleteExpiredUsersMutation = useDeleteExpiredUsers()
  const resetUsersDataUsageMutation = useResetUsersDataUsage()
  const clearUsageDataMutation = useClearUsageData()

  const usageDataTables = [
    { value: 'node_user_usages', label: t('settings.cleanup.clearUsageData.tables.nodeUserUsages') },
    { value: 'node_usages', label: t('settings.cleanup.clearUsageData.tables.nodeUsages') },
  ]

  const handleDeleteExpired = async () => {
    const target = deleteTarget
    const params: any = { target }
    if (target === 'expired') {
      if (expiredAfter) params.expired_after = startOfDay(expiredAfter).toISOString()
      if (expiredBefore) params.expired_before = endOfDay(expiredBefore).toISOString()
    }
    if (selectedAdmin) params.admin_username = selectedAdmin.username

    deleteExpiredUsersMutation.mutate(
      { params: Object.keys(params).length > 0 ? params : undefined },
      {
        onSuccess: response => {
          const count = response?.count || 0
          toast.success(target === 'limited' ? t('settings.cleanup.expiredUsers.deleteLimitedSuccess', { count }) : t('settings.cleanup.expiredUsers.deleteSuccess', { count }))
        },
        onError: (error: any) => {
          const failureMessageKey = target === 'limited' ? 'settings.cleanup.expiredUsers.deleteLimitedFailed' : 'settings.cleanup.expiredUsers.deleteFailed'

          // Extract detailed error message
          let errorMessage = t(failureMessageKey)

          if (error?.data?.detail) {
            const detail = error.data.detail
            if (typeof detail === 'string') {
              errorMessage = detail
            } else if (typeof detail === 'object' && !Array.isArray(detail)) {
              const fieldErrors = Object.entries(detail)
                .map(([field, message]) => `${field}: ${message}`)
                .join(', ')
              errorMessage = fieldErrors
            }
          } else if (error?.response?.data?.detail) {
            const detail = error.response.data.detail
            if (typeof detail === 'string') {
              errorMessage = detail
            } else if (typeof detail === 'object' && !Array.isArray(detail)) {
              const fieldErrors = Object.entries(detail)
                .map(([field, message]) => `${field}: ${message}`)
                .join(', ')
              errorMessage = fieldErrors
            }
          } else if (error?.message) {
            errorMessage = error.message
          }

          toast.error(t(failureMessageKey), {
            description: errorMessage,
          })
        },
      },
    )
  }

  const formatDate = (date: Date) => {
    return formatDateByLocale(date, isPersianLocale, false)
  }

  const handleResetUsage = async () => {
    resetUsersDataUsageMutation.mutate(undefined, {
      onSuccess: () => {
        toast.success(t('settings.cleanup.resetUsage.resetSuccess'))
      },
      onError: (error: any) => {
        // Extract detailed error message
        let errorMessage = t('settings.cleanup.resetUsage.resetFailed')

        if (error?.data?.detail) {
          const detail = error.data.detail
          if (typeof detail === 'string') {
            errorMessage = detail
          } else if (typeof detail === 'object' && !Array.isArray(detail)) {
            const fieldErrors = Object.entries(detail)
              .map(([field, message]) => `${field}: ${message}`)
              .join(', ')
            errorMessage = fieldErrors
          }
        } else if (error?.response?.data?.detail) {
          const detail = error.response.data.detail
          if (typeof detail === 'string') {
            errorMessage = detail
          } else if (typeof detail === 'object' && !Array.isArray(detail)) {
            const fieldErrors = Object.entries(detail)
              .map(([field, message]) => `${field}: ${message}`)
              .join(', ')
            errorMessage = fieldErrors
          }
        } else if (error?.message) {
          errorMessage = error.message
        }

        toast.error(t('settings.cleanup.resetUsage.resetFailed'), {
          description: errorMessage,
        })
      },
    })
  }

  const handleClearUsageData = async () => {
    if (!selectedTable) {
      toast.error(t('settings.cleanup.clearUsageData.noTableSelected'))
      return
    }

    const params: any = {}
    if (clearDataAfter) params.start = clearDataAfter.toISOString()
    if (clearDataBefore) params.end = clearDataBefore.toISOString()

    clearUsageDataMutation.mutate(
      {
        table: selectedTable as UsageTable,
        params: Object.keys(params).length > 0 ? params : undefined,
      },
      {
        onSuccess: () => {
          toast.success(t('settings.cleanup.clearUsageData.clearSuccess', { table: selectedTable }))
        },
        onError: (error: any) => {
          // Extract detailed error message
          let errorMessage = t('settings.cleanup.clearUsageData.clearFailed')

          if (error?.data?.detail) {
            const detail = error.data.detail
            if (typeof detail === 'string') {
              errorMessage = detail
            } else if (typeof detail === 'object' && !Array.isArray(detail)) {
              const fieldErrors = Object.entries(detail)
                .map(([field, message]) => `${field}: ${message}`)
                .join(', ')
              errorMessage = fieldErrors
            }
          } else if (error?.response?.data?.detail) {
            const detail = error.response.data.detail
            if (typeof detail === 'string') {
              errorMessage = detail
            } else if (typeof detail === 'object' && !Array.isArray(detail)) {
              const fieldErrors = Object.entries(detail)
                .map(([field, message]) => `${field}: ${message}`)
                .join(', ')
              errorMessage = fieldErrors
            }
          } else if (error?.message) {
            errorMessage = error.message
          }

          toast.error(t('settings.cleanup.clearUsageData.clearFailed'), {
            description: errorMessage,
          })
        },
      },
    )
  }

  const filteredAdmins = admins.filter(admin => admin.username !== 'system')

  return (
    <div className="space-y-6 p-4 sm:space-y-8 sm:py-6 lg:space-y-10 lg:py-8">
      {/* Delete Expired Users Section */}
      <Card>
        <CardHeader className="p-4 sm:p-6">
          <CardTitle className="flex items-center gap-2 text-base font-semibold sm:text-lg">
            <Database className="h-5 w-5" />
            {t('settings.cleanup.expiredUsers.title')}
          </CardTitle>
          <CardDescription className="text-xs sm:text-sm">{t('settings.cleanup.expiredUsers.description')}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3 p-4 pt-0 sm:space-y-4 sm:px-6">
          <div className="relative mb-3 w-full max-w-xs sm:mb-4 sm:max-w-sm lg:max-w-md" dir={dir}>
            <Popover open={dropdownOpen} onOpenChange={setDropdownOpen}>
              <PopoverTrigger asChild>
                <Button variant="outline" className={cn('hover:bg-muted/50 h-8 w-full justify-between px-2 transition-colors sm:h-9 sm:px-3', 'min-w-0 text-xs font-medium sm:text-sm')}>
                  <div className={cn('flex min-w-0 flex-1 items-center gap-1 sm:gap-2', dir === 'rtl' ? 'flex-row-reverse' : 'flex-row')}>
                    <Avatar className="h-4 w-4 flex-shrink-0 sm:h-5 sm:w-5">
                      <AvatarFallback className="bg-muted text-xs font-medium">{selectedAdmin?.username?.charAt(0).toUpperCase() || '?'}</AvatarFallback>
                    </Avatar>
                    <span className="truncate text-xs sm:text-sm">{selectedAdmin?.username || t('advanceSearch.selectAdmin')}</span>
                    {selectedAdmin && (
                      <div className="flex-shrink-0" title={roleLabel(selectedAdmin)}>
                        {isOwner(selectedAdmin) ? <UserCog className="text-primary h-3 w-3" /> : <UserRound className="text-primary h-3 w-3" />}
                      </div>
                    )}
                  </div>
                  <ChevronDown className="text-muted-foreground ml-1 h-3 w-3 flex-shrink-0" />
                </Button>
              </PopoverTrigger>
              <PopoverContent className="w-64 p-1 sm:w-72 lg:w-80" sideOffset={4} align={dir === 'rtl' ? 'end' : 'start'}>
                <Command>
                  <CommandInput placeholder={t('search')} onValueChange={setAdminSearchInput} className="mb-1 h-7 text-xs sm:h-8 sm:text-sm" />
                  <CommandList ref={listRef}>
                    <CommandEmpty>
                      <div className="text-muted-foreground py-3 text-center text-xs sm:py-4 sm:text-sm">{t('noAdminsFound') || 'No admins found'}</div>
                    </CommandEmpty>

                    <CommandItem
                      onSelect={() => {
                        setSelectedAdmin(undefined)
                        setDropdownOpen(false)
                      }}
                      className={cn('flex min-w-0 items-center gap-2 px-2 py-1.5 text-xs sm:text-sm', dir === 'rtl' ? 'flex-row-reverse' : 'flex-row')}
                    >
                      <Avatar className="h-4 w-4 flex-shrink-0 sm:h-5 sm:w-5">
                        <AvatarFallback className="bg-primary/10 text-xs font-medium">N</AvatarFallback>
                      </Avatar>
                      <span className="flex-1 truncate">All</span>
                      <div className="flex flex-shrink-0 items-center gap-1">{!selectedAdmin && <Check className="text-primary h-3 w-3" />}</div>
                    </CommandItem>

                    {filteredAdmins.map(admin => (
                      <CommandItem
                        key={admin.username}
                        onSelect={() => {
                          setSelectedAdmin(admin)
                          setDropdownOpen(false)
                        }}
                        className={cn('flex min-w-0 items-center gap-2 px-2 py-1.5 text-xs sm:text-sm', dir === 'rtl' ? 'flex-row-reverse' : 'flex-row')}
                      >
                        <Avatar className="h-4 w-4 flex-shrink-0 sm:h-5 sm:w-5">
                          <AvatarFallback className="bg-muted text-xs font-medium">{admin.username.charAt(0).toUpperCase()}</AvatarFallback>
                        </Avatar>
                        <span className="flex-1 truncate">{admin.username}</span>
                        <div className="flex flex-shrink-0 items-center gap-1">
                          <span title={roleLabel(admin)}>{isOwner(admin) ? <UserCog className="text-primary h-3 w-3" /> : <UserRound className="text-primary h-3 w-3" />}</span>
                          {selectedAdmin?.username === admin.username && <Check className="text-primary h-3 w-3" />}
                        </div>
                      </CommandItem>
                    ))}

                    {isLoading && (
                      <div className="flex justify-center py-2">
                        <Loader2 className="text-muted-foreground h-3 w-3 animate-spin" />
                      </div>
                    )}
                  </CommandList>
                </Command>
              </PopoverContent>
            </Popover>
          </div>

          <div className="flex flex-col gap-y-2">
            <label className="text-xs font-medium sm:text-sm">{t('settings.cleanup.expiredUsers.target')}</label>
            <Select value={deleteTarget} onValueChange={value => setDeleteTarget(value as CleanupDeleteTarget)}>
              <SelectTrigger className="w-full text-xs sm:text-sm">
                <SelectValue placeholder={t('settings.cleanup.expiredUsers.targetPlaceholder')} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="expired" className="text-xs sm:text-sm">
                  {t('settings.cleanup.expiredUsers.targets.expired')}
                </SelectItem>
                <SelectItem value="limited" className="text-xs sm:text-sm">
                  {t('settings.cleanup.expiredUsers.targets.limited')}
                </SelectItem>
              </SelectContent>
            </Select>
          </div>

          {deleteTarget === 'expired' ? (
            <>
              <div className="grid grid-cols-1 gap-3 sm:gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <DatePicker
                    mode="single"
                    date={expiredAfter}
                    onDateChange={setExpiredAfter}
                    label={t('settings.cleanup.expiredUsers.expiredAfter')}
                    placeholder={t('settings.cleanup.expiredUsers.expiredAfterPlaceholder')}
                    minDate={new Date('1900-01-01')}
                    maxDate={new Date()}
                    formatDate={formatDate}
                    side={'bottom'}
                    align={'center'}
                    className="[&_button]:text-xs sm:[&_button]:text-sm [&_label]:text-xs sm:[&_label]:text-sm"
                  />
                </div>

                <div className="space-y-2">
                  <DatePicker
                    mode="single"
                    date={expiredBefore}
                    onDateChange={setExpiredBefore}
                    label={t('settings.cleanup.expiredUsers.expiredBefore')}
                    placeholder={t('settings.cleanup.expiredUsers.expiredBeforePlaceholder')}
                    minDate={new Date('1900-01-01')}
                    maxDate={new Date()}
                    formatDate={formatDate}
                    side={'bottom'}
                    align={'center'}
                    className="[&_button]:text-xs sm:[&_button]:text-sm [&_label]:text-xs sm:[&_label]:text-sm"
                  />
                </div>
              </div>

              <div className="text-muted-foreground text-xs sm:text-sm">{t('settings.cleanup.expiredUsers.selectDateRange')}</div>
            </>
          ) : (
            <div className="text-muted-foreground text-xs sm:text-sm">{t('settings.cleanup.expiredUsers.selectLimitedInfo')}</div>
          )}

          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button variant="destructive" disabled={deleteExpiredUsersMutation.isPending} className="w-full">
                <Trash2 className="mr-2 h-4 w-4" />
                {deleteExpiredUsersMutation.isPending
                  ? t('settings.cleanup.expiredUsers.deleting')
                  : deleteTarget === 'limited'
                    ? t('settings.cleanup.expiredUsers.deleteLimited')
                    : t('settings.cleanup.expiredUsers.deleteExpired')}
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle className="flex items-center gap-2">
                  <AlertTriangle className="text-destructive h-5 w-5" />
                  {deleteTarget === 'limited' ? t('settings.cleanup.expiredUsers.confirmDeleteLimited') : t('settings.cleanup.expiredUsers.confirmDelete')}
                </AlertDialogTitle>
                <AlertDialogDescription className={cn(dir === 'rtl' ? 'text-right' : 'text-left', 'text-xs sm:text-sm')}>
                  {deleteTarget === 'limited' ? t('settings.cleanup.expiredUsers.confirmDeleteLimitedMessage') : t('settings.cleanup.expiredUsers.confirmDeleteMessage')}
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>{t('cancel')}</AlertDialogCancel>
                <AlertDialogAction onClick={handleDeleteExpired} disabled={deleteExpiredUsersMutation.isPending} className="bg-destructive text-destructive-foreground hover:bg-destructive/90 !m-0">
                  {deleteTarget === 'limited' ? t('settings.cleanup.expiredUsers.deleteLimited') : t('settings.cleanup.expiredUsers.deleteExpired')}
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </CardContent>
      </Card>

      {/* Clear Usage Data Section */}
      <Card>
        <CardHeader className="p-4 sm:p-6">
          <CardTitle className="flex items-center gap-2 text-base font-semibold sm:text-lg">
            <Server className="h-5 w-5" />
            {t('settings.cleanup.clearUsageData.title')}
          </CardTitle>
          <CardDescription className="text-xs sm:text-sm">{t('settings.cleanup.clearUsageData.description')}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3 p-4 pt-0 sm:space-y-4 sm:px-6">
          <div className="flex flex-col gap-y-2">
            <label className="text-xs font-medium sm:text-sm">{t('settings.cleanup.clearUsageData.selectTable')}</label>
            <Select value={selectedTable} onValueChange={setSelectedTable}>
              <SelectTrigger className="w-full text-xs sm:text-sm">
                <SelectValue placeholder={t('settings.cleanup.clearUsageData.selectTablePlaceholder')} />
              </SelectTrigger>
              <SelectContent>
                {usageDataTables.map(table => (
                  <SelectItem key={table.value} value={table.value} className="text-xs sm:text-sm">
                    {table.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="grid grid-cols-1 gap-3 sm:gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <DatePicker
                mode="single"
                date={clearDataAfter}
                onDateChange={setClearDataAfter}
                label={t('settings.cleanup.clearUsageData.dataAfter')}
                placeholder={t('settings.cleanup.clearUsageData.dataAfterPlaceholder')}
                minDate={new Date('1900-01-01')}
                maxDate={new Date()}
                formatDate={formatDate}
                className="[&_button]:text-xs sm:[&_button]:text-sm [&_label]:text-xs sm:[&_label]:text-sm"
              />
            </div>

            <div className="space-y-2">
              <DatePicker
                mode="single"
                date={clearDataBefore}
                onDateChange={setClearDataBefore}
                label={t('settings.cleanup.clearUsageData.dataBefore')}
                placeholder={t('settings.cleanup.clearUsageData.dataBeforePlaceholder')}
                minDate={new Date('1900-01-01')}
                maxDate={new Date()}
                formatDate={formatDate}
                className="[&_button]:text-xs sm:[&_button]:text-sm [&_label]:text-xs sm:[&_label]:text-sm"
              />
            </div>
          </div>

          <div className="text-muted-foreground text-xs sm:text-sm">{t('settings.cleanup.clearUsageData.selectDateRange')}</div>

          <Alert className="p-3 sm:p-4">
            <AlertTriangle className="h-4 w-4" />
            <AlertDescription className="text-xs sm:text-sm">{t('settings.cleanup.clearUsageData.warning')}</AlertDescription>
          </Alert>

          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button variant="destructive" disabled={!selectedTable || clearUsageDataMutation.isPending} className="w-full">
                <Server className="mr-2 h-4 w-4" />
                {clearUsageDataMutation.isPending ? t('settings.cleanup.clearUsageData.clearing') : t('settings.cleanup.clearUsageData.clearData')}
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent dir={dir}>
              <AlertDialogHeader>
                <AlertDialogTitle className="flex items-center gap-2">
                  <AlertTriangle className="text-destructive h-5 w-5" />
                  {t('settings.cleanup.clearUsageData.confirmClear')}
                </AlertDialogTitle>
                <AlertDialogDescription className={cn(dir === 'rtl' ? 'text-right' : 'text-left', 'text-xs sm:text-sm')}>
                  {t('settings.cleanup.clearUsageData.confirmClearMessage', { table: selectedTable })}
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>{t('cancel')}</AlertDialogCancel>
                <AlertDialogAction onClick={handleClearUsageData} disabled={clearUsageDataMutation.isPending} className="bg-destructive text-destructive-foreground hover:bg-destructive/90 !m-0">
                  {t('settings.cleanup.clearUsageData.clearData')}
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </CardContent>
      </Card>

      {/* Reset Usage Section */}
      <Card>
        <CardHeader className="p-4 sm:p-6">
          <CardTitle className="flex items-center gap-2 text-base font-semibold sm:text-lg">
            <RotateCcw className="h-5 w-5" />
            {t('settings.cleanup.resetUsage.title')}
          </CardTitle>
          <CardDescription className="text-xs sm:text-sm">{t('settings.cleanup.resetUsage.description')}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3 p-4 pt-0 sm:space-y-4 sm:px-6">
          <Alert className="p-3 sm:p-4">
            <AlertTriangle className="h-4 w-4" />
            <AlertDescription className="text-xs sm:text-sm">{t('settings.cleanup.resetUsage.warning')}</AlertDescription>
          </Alert>

          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button variant="destructive" disabled={resetUsersDataUsageMutation.isPending} className="w-full">
                <RotateCcw className="mr-2 h-4 w-4" />
                {resetUsersDataUsageMutation.isPending ? t('settings.cleanup.resetUsage.resetting') : t('settings.cleanup.resetUsage.resetAll')}
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent dir={dir}>
              <AlertDialogHeader>
                <AlertDialogTitle className="flex items-center gap-2">
                  <AlertTriangle className="text-destructive h-5 w-5" />
                  {t('settings.cleanup.resetUsage.confirmReset')}
                </AlertDialogTitle>
                <AlertDialogDescription className={cn(dir === 'rtl' ? 'text-right' : 'text-left', 'text-xs sm:text-sm')}>{t('settings.cleanup.resetUsage.confirmResetMessage')}</AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>{t('cancel')}</AlertDialogCancel>
                <AlertDialogAction onClick={handleResetUsage} disabled={resetUsersDataUsageMutation.isPending} className="bg-destructive text-destructive-foreground hover:bg-destructive/90 !m-0">
                  {t('settings.cleanup.resetUsage.resetAll')}
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </CardContent>
      </Card>
    </div>
  )
}
