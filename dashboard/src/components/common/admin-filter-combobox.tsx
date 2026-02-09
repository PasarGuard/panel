import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { Button } from '@/components/ui/button'
import { Command, CommandEmpty, CommandInput, CommandItem, CommandList } from '@/components/ui/command'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import useDirDetection from '@/hooks/use-dir-detection'
import { useDebouncedSearch } from '@/hooks/use-debounced-search'
import { cn } from '@/lib/utils'
import { type AdminDetails, type AdminSimple, useGetAdminsSimple } from '@/service/api'
import { Check, ChevronDown, Loader2, Sigma, UserRound } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

interface AdminFilterComboboxProps {
  value: string
  onValueChange: (username: string) => void
  onAdminSelect?: (admin: AdminDetails | null) => void
  className?: string
}

const PAGE_SIZE = 20

export default function AdminFilterCombobox({ value, onValueChange, onAdminSelect, className }: AdminFilterComboboxProps) {
  const { t } = useTranslation()
  const dir = useDirDetection()

  const [open, setOpen] = useState(false)
  const [offset, setOffset] = useState(0)
  const [admins, setAdmins] = useState<AdminSimple[]>([])
  const [hasMore, setHasMore] = useState(true)
  const [isLoadingMore, setIsLoadingMore] = useState(false)
  const listRef = useRef<HTMLDivElement>(null)
  const { debouncedSearch: adminSearch, setSearch: setAdminSearchInput } = useDebouncedSearch('', 300)

  useEffect(() => {
    setOffset(0)
    setAdmins([])
    setHasMore(true)
    setIsLoadingMore(false)
  }, [adminSearch])

  const { data: fetchedAdminsResponse, isLoading, isFetching } = useGetAdminsSimple(
    {
      limit: PAGE_SIZE,
      offset,
      ...(adminSearch ? { username: adminSearch } : {}),
    },
    {
      query: {
        enabled: open,
      },
    },
  )

  useEffect(() => {
    if (!fetchedAdminsResponse) return

    const fetchedAdmins = (fetchedAdminsResponse.admins || []).filter(admin => admin.username !== 'system')
    setAdmins(prev => {
      const merged = offset === 0 ? fetchedAdmins : [...prev, ...fetchedAdmins]
      const byUsername = new Map<string, AdminSimple>()
      merged.forEach(admin => {
        byUsername.set(admin.username, admin)
      })
      return Array.from(byUsername.values())
    })
    setHasMore(fetchedAdmins.length === PAGE_SIZE)
    setIsLoadingMore(false)
  }, [fetchedAdminsResponse, offset])

  const handleScroll = useCallback(() => {
    if (!listRef.current || isLoadingMore || isFetching || !hasMore) return
    const { scrollTop, scrollHeight, clientHeight } = listRef.current
    if (scrollHeight - scrollTop - clientHeight < 90) {
      setIsLoadingMore(true)
      setOffset(prev => prev + PAGE_SIZE)
    }
  }, [hasMore, isFetching, isLoadingMore])

  useEffect(() => {
    const el = listRef.current
    if (!el) return
    el.addEventListener('scroll', handleScroll)
    return () => el.removeEventListener('scroll', handleScroll)
  }, [handleScroll])

  const selectedAdmin = useMemo(() => admins.find(admin => admin.username === value), [admins, value])
  const triggerLabel = value === 'all' ? t('statistics.adminFilterAll') : selectedAdmin?.username || value
  const showInitialAdminsLoading = open && admins.length === 0 && isFetching

  return (
    <div className={cn('w-full', className)} dir={dir}>
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button variant="outline" className="h-8 w-full min-w-0 justify-between px-2 text-xs font-medium transition-colors hover:bg-muted/50 sm:px-3 sm:text-sm">
            <div className={cn('flex min-w-0 flex-1 items-center gap-1.5 sm:gap-2', dir === 'rtl' ? 'flex-row-reverse' : 'flex-row')}>
              <Avatar className="h-4 w-4 flex-shrink-0 sm:h-5 sm:w-5">
                <AvatarFallback className="bg-muted text-xs font-medium">{value === 'all' ? <Sigma className="h-3 w-3" /> : triggerLabel.charAt(0).toUpperCase()}</AvatarFallback>
              </Avatar>
              <span className="truncate">{triggerLabel}</span>
              {value !== 'all' && selectedAdmin && <div className="flex-shrink-0"><UserRound className="h-3 w-3 text-primary" /></div>}
            </div>
            <ChevronDown className="ml-1 h-3 w-3 flex-shrink-0 text-muted-foreground" />
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-[min(92vw,20rem)] p-1 sm:w-[20rem]" sideOffset={4} align={dir === 'rtl' ? 'end' : 'start'}>
          <Command>
            <CommandInput placeholder={t('search', { defaultValue: 'Search' })} onValueChange={setAdminSearchInput} className="h-8 text-sm" />
            <CommandList ref={listRef}>
              <CommandEmpty>
                {showInitialAdminsLoading ? (
                  <div className="flex items-center justify-center gap-2 py-3 text-xs text-muted-foreground sm:py-4 sm:text-sm">
                    <Loader2 className="h-3 w-3 animate-spin" />
                    <span>{t('loading', { defaultValue: 'Loading...' })}</span>
                  </div>
                ) : (
                  <div className="py-3 text-center text-xs text-muted-foreground sm:py-4 sm:text-sm">{t('noAdminsFound', { defaultValue: 'No admins found' })}</div>
                )}
              </CommandEmpty>

              <CommandItem
                value="all"
                onSelect={() => {
                  onValueChange('all')
                  onAdminSelect?.(null)
                  setOpen(false)
                }}
                className={cn('flex min-w-0 items-center gap-2 px-2 py-1.5 text-xs sm:text-sm', dir === 'rtl' ? 'flex-row-reverse' : 'flex-row')}
              >
                <Avatar className="h-4 w-4 flex-shrink-0 sm:h-5 sm:w-5">
                  <AvatarFallback className="bg-primary/10 text-xs font-medium">
                    <Sigma className="h-3 w-3" />
                  </AvatarFallback>
                </Avatar>
                <span className="flex-1 truncate">{t('statistics.adminFilterAll')}</span>
                {value === 'all' && <Check className="h-3 w-3 text-primary" />}
              </CommandItem>

              {admins.map(admin => (
                <CommandItem
                  key={admin.username}
                  value={admin.username}
                  onSelect={() => {
                    onValueChange(admin.username)
                    onAdminSelect?.({
                      ...admin,
                      is_sudo: false,
                    })
                    setOpen(false)
                  }}
                  className={cn('flex min-w-0 items-center gap-2 px-2 py-1.5 text-xs sm:text-sm', dir === 'rtl' ? 'flex-row-reverse' : 'flex-row')}
                >
                  <Avatar className="h-4 w-4 flex-shrink-0 sm:h-5 sm:w-5">
                    <AvatarFallback className="bg-muted text-xs font-medium">{admin.username.charAt(0).toUpperCase()}</AvatarFallback>
                  </Avatar>
                  <span className="flex-1 truncate">{admin.username}</span>
                  <div className="flex flex-shrink-0 items-center gap-1">
                    <UserRound className="h-3 w-3 text-primary" />
                    {value === admin.username && <Check className="h-3 w-3 text-primary" />}
                  </div>
                </CommandItem>
              ))}

              {(isLoadingMore || (!showInitialAdminsLoading && (isLoading || isFetching))) && (
                <div className="flex justify-center py-2">
                  <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" />
                </div>
              )}
            </CommandList>
          </Command>
        </PopoverContent>
      </Popover>
    </div>
  )
}
