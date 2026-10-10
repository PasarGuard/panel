import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { Button } from '@/components/ui/button'
import { Command, CommandEmpty, CommandInput, CommandItem, CommandList } from '@/components/ui/command'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import useDirDetection from '@/hooks/use-dir-detection'
import { useDebouncedSearch } from '@/hooks/use-debounced-search'
import { cn } from '@/lib/utils'
import { type AdminSimple, useGetAdminsSimple } from '@/service/api'
import { Check, ChevronDown, Loader2, Sigma, UserRound } from 'lucide-react'
import { type UIEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

interface AdminFilterComboboxProps {
  value: string
  onValueChange: (username: string) => void
  onAdminSelect?: (admin: AdminSimple | null) => void
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
  const requestedOffsetRef = useRef(0)
  const { debouncedSearch: adminSearch, setSearch: setAdminSearchInput } = useDebouncedSearch('', 300)

  useEffect(() => {
    setOffset(0)
    setAdmins([])
    setHasMore(true)
    setIsLoadingMore(false)
    requestedOffsetRef.current = 0
  }, [adminSearch])

  const {
    data: fetchedAdminsResponse,
    isLoading,
    isFetching,
  } = useGetAdminsSimple(
    {
      limit: PAGE_SIZE,
      offset,
      sort: 'username',
      ...(adminSearch ? { search: adminSearch } : {}),
    },
    {
      query: {
        enabled: open,
      },
    },
  )

  useEffect(() => {
    if (!fetchedAdminsResponse) return

    const fetchedAdminsPage = fetchedAdminsResponse.admins || []
    const fetchedAdmins = fetchedAdminsPage.filter(admin => admin.username !== 'system')
    setAdmins(prev => {
      const merged = offset === 0 ? fetchedAdmins : [...prev, ...fetchedAdmins]
      const byUsername = new Map<string, AdminSimple>()
      merged.forEach(admin => {
        byUsername.set(admin.username, admin)
      })
      return Array.from(byUsername.values())
    })
    setHasMore(fetchedAdminsPage.length > 0 && offset + fetchedAdminsPage.length < fetchedAdminsResponse.total)
    setIsLoadingMore(false)
  }, [fetchedAdminsResponse, offset])

  const handleScroll = useCallback((event: UIEvent<HTMLDivElement>) => {
    if (isLoadingMore || isFetching || !hasMore) return
    const { scrollTop, scrollHeight, clientHeight } = event.currentTarget
    if (scrollHeight - scrollTop - clientHeight < 90) {
      const nextOffset = requestedOffsetRef.current + PAGE_SIZE
      requestedOffsetRef.current = nextOffset
      setIsLoadingMore(true)
      setOffset(nextOffset)
    }
  }, [hasMore, isFetching, isLoadingMore])

  const selectedAdmin = useMemo(() => admins.find(admin => admin.username === value), [admins, value])
  const triggerLabel = value === 'all' ? t('statistics.adminFilterAll') : selectedAdmin?.username || value
  const showInitialAdminsLoading = open && admins.length === 0 && isFetching

  return (
    <div className={cn('w-full', className)} dir={dir}>
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button variant="outline" className="hover:bg-muted/50 h-8 w-full min-w-0 justify-between px-2 text-xs font-medium transition-colors sm:px-3 sm:text-sm">
            <div className={cn('flex min-w-0 flex-1 items-center gap-1.5 sm:gap-2', dir === 'rtl' ? 'flex-row-reverse' : 'flex-row')}>
              <Avatar className="h-4 w-4 flex-shrink-0 sm:h-5 sm:w-5">
                <AvatarFallback className="bg-muted text-xs font-medium">{value === 'all' ? <Sigma className="h-3 w-3" /> : triggerLabel.charAt(0).toUpperCase()}</AvatarFallback>
              </Avatar>
              <span className="truncate">{triggerLabel}</span>
              {value !== 'all' && selectedAdmin && (
                <div className="flex-shrink-0">
                  <UserRound className="text-primary h-3 w-3" />
                </div>
              )}
            </div>
            <ChevronDown className="text-muted-foreground ml-1 h-3 w-3 flex-shrink-0" />
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-[min(92vw,20rem)] p-1 sm:w-[20rem]" sideOffset={4} align={dir === 'rtl' ? 'end' : 'start'}>
          <Command>
            <CommandInput placeholder={t('search', { defaultValue: 'Search' })} onValueChange={setAdminSearchInput} className="h-8 text-sm" />
            <CommandList onScroll={handleScroll}>
              <CommandEmpty>
                {showInitialAdminsLoading ? (
                  <div className="text-muted-foreground flex items-center justify-center gap-2 py-3 text-xs sm:py-4 sm:text-sm">
                    <Loader2 className="h-3 w-3 animate-spin" />
                    <span>{t('loading', { defaultValue: 'Loading...' })}</span>
                  </div>
                ) : (
                  <div className="text-muted-foreground py-3 text-center text-xs sm:py-4 sm:text-sm">{t('noAdminsFound', { defaultValue: 'No admins found' })}</div>
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
                {value === 'all' && <Check className="text-primary h-3 w-3" />}
              </CommandItem>

              {admins.map(admin => (
                <CommandItem
                  key={admin.username}
                  value={admin.username}
                  onSelect={() => {
                    onValueChange(admin.username)
                    onAdminSelect?.(admin)
                    setOpen(false)
                  }}
                  className={cn('flex min-w-0 items-center gap-2 px-2 py-1.5 text-xs sm:text-sm', dir === 'rtl' ? 'flex-row-reverse' : 'flex-row')}
                >
                  <Avatar className="h-4 w-4 flex-shrink-0 sm:h-5 sm:w-5">
                    <AvatarFallback className="bg-muted text-xs font-medium">{admin.username.charAt(0).toUpperCase()}</AvatarFallback>
                  </Avatar>
                  <span className="flex-1 truncate">{admin.username}</span>
                  <div className="flex flex-shrink-0 items-center gap-1">
                    <UserRound className="text-primary h-3 w-3" />
                    {value === admin.username && <Check className="text-primary h-3 w-3" />}
                  </div>
                </CommandItem>
              ))}

              {(isLoadingMore || (!showInitialAdminsLoading && (isLoading || isFetching))) && (
                <div className="flex justify-center py-2">
                  <Loader2 className="text-muted-foreground h-3 w-3 animate-spin" />
                </div>
              )}
            </CommandList>
          </Command>
        </PopoverContent>
      </Popover>
    </div>
  )
}
