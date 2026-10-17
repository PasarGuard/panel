import AdminFilterCombobox from '@/components/common/admin-filter-combobox'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { PaginationControls } from '@/features/admins/components/filters'
import { OnlineStatus } from '@/features/users/components/online-status'
import { useDebouncedSearch } from '@/hooks/use-debounced-search'
import useDirDetection from '@/hooks/use-dir-detection'
import { cn } from '@/lib/utils'
import { AdminSimple, NodeSimple, UserStatus, useUsersRankedByIpCount } from '@/service/api'
import { formatBytes } from '@/utils/formatByte'
import { ChevronDown, Network, TriangleAlert, X } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'

interface IpRankingTableProps {
  nodesData: NodeSimple[]
  isLoadingNodes: boolean
}

function NodesFilter({ nodesData, isLoadingNodes, selectedIds, onChange }: { nodesData: NodeSimple[]; isLoadingNodes: boolean; selectedIds: number[]; onChange: (ids: number[]) => void }) {
  const { t } = useTranslation()
  const dir = useDirDetection()
  const [open, setOpen] = useState(false)

  const toggle = (id: number) => {
    onChange(selectedIds.includes(id) ? selectedIds.filter(existing => existing !== id) : [...selectedIds, id])
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="outline" disabled={isLoadingNodes} className="hover:bg-muted/50 h-8 min-w-[9rem] justify-between px-2 text-xs font-medium sm:h-9 sm:px-3 sm:text-sm">
          <span className="flex min-w-0 items-center gap-1.5">
            <Network className="text-muted-foreground h-3.5 w-3.5 shrink-0" />
            <span className="truncate">{selectedIds.length === 0 ? t('statistics.ipRanking.allNodes') : t('statistics.ipRanking.nodesSelected', { count: selectedIds.length })}</span>
          </span>
          <ChevronDown className="text-muted-foreground ml-1 h-3 w-3 shrink-0" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-64 p-1" sideOffset={4} align={dir === 'rtl' ? 'end' : 'start'}>
        <div className="max-h-64 overflow-y-auto">
          {nodesData.length === 0 ? (
            <div className="text-muted-foreground py-3 text-center text-xs">{t('statistics.noNodesAvailable')}</div>
          ) : (
            nodesData.map(node => (
              <label key={node.id} className="hover:bg-accent flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-xs sm:text-sm">
                <Checkbox checked={selectedIds.includes(node.id)} onCheckedChange={() => toggle(node.id)} />
                <span className="min-w-0 flex-1 truncate">{node.name}</span>
              </label>
            ))
          )}
        </div>
        {selectedIds.length > 0 && (
          <Button variant="ghost" size="sm" className="mt-1 h-7 w-full justify-center text-xs" onClick={() => onChange([])}>
            {t('statistics.ipRanking.clearNodes')}
          </Button>
        )}
      </PopoverContent>
    </Popover>
  )
}

function IpListPopover({ ips, distinctIpCount }: { ips: Record<string, number>; distinctIpCount: number }) {
  const { t } = useTranslation()
  const dir = useDirDetection()
  const entries = useMemo(() => Object.entries(ips).sort(([, a], [, b]) => b - a), [ips])

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="outline" size="sm" className="h-7 gap-1 px-2 text-xs">
          <Badge variant="secondary" className="tabular-nums">
            {distinctIpCount}
          </Badge>
          {t('statistics.ipRanking.viewIps')}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-72 p-2" align={dir === 'rtl' ? 'end' : 'start'}>
        <ScrollArea className="max-h-64">
          <div className="space-y-1">
            {entries.map(([ip, lastSeen]) => (
              <div key={ip} className="bg-accent/40 flex items-center justify-between gap-2 rounded px-2 py-1">
                <span className="min-w-0 truncate font-mono text-xs" dir="ltr">
                  {ip}
                </span>
                <OnlineStatus lastOnline={lastSeen} />
              </div>
            ))}
          </div>
        </ScrollArea>
      </PopoverContent>
    </Popover>
  )
}

export default function IpRankingTable({ nodesData, isLoadingNodes }: IpRankingTableProps) {
  const { t } = useTranslation()
  const dir = useDirDetection()

  const [page, setPage] = useState(0)
  const [itemsPerPage, setItemsPerPage] = useState(10)
  const [status, setStatus] = useState<UserStatus | 'all'>('all')
  const [adminFilterValue, setAdminFilterValue] = useState('all')
  const [selectedAdmin, setSelectedAdmin] = useState<AdminSimple | null>(null)
  const { search: ipCountMin, debouncedSearch: debouncedIpCountMin, setSearch: setIpCountMin } = useDebouncedSearch('', 400)
  const { search: ipCountMax, debouncedSearch: debouncedIpCountMax, setSearch: setIpCountMax } = useDebouncedSearch('', 400)
  const [selectedNodeIds, setSelectedNodeIds] = useState<number[]>([])

  const resetPage = () => setPage(0)

  const { data, isLoading, isFetching } = useUsersRankedByIpCount(
    {
      offset: page * itemsPerPage,
      limit: itemsPerPage,
      status: status === 'all' ? undefined : status,
      admin_ids: selectedAdmin ? [selectedAdmin.id] : undefined,
      ip_count_min: debouncedIpCountMin ? Number(debouncedIpCountMin) : undefined,
      ip_count_max: debouncedIpCountMax ? Number(debouncedIpCountMax) : undefined,
      node_ids: selectedNodeIds.length > 0 ? selectedNodeIds : undefined,
    },
    {
      query: {
        placeholderData: previousData => previousData,
      },
    },
  )

  const rows = data?.users ?? []
  const isLoadingData = isLoading || isFetching
  const totalItems = data?.total ?? 0
  const totalPages = Math.max(1, Math.ceil(totalItems / itemsPerPage))
  const skippedNodeCount = data?.skipped_node_count ?? 0
  const hasActiveFilters = status !== 'all' || !!selectedAdmin || !!ipCountMin || !!ipCountMax || selectedNodeIds.length > 0

  const clearFilters = () => {
    setStatus('all')
    setAdminFilterValue('all')
    setSelectedAdmin(null)
    setIpCountMin('')
    setIpCountMax('')
    setSelectedNodeIds([])
    resetPage()
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base sm:text-lg">{t('statistics.ipRanking.title')}</CardTitle>
        <p className="text-muted-foreground text-xs sm:text-sm">
          {t('statistics.ipRanking.description')}
        </p>
        {skippedNodeCount > 0 && (
          <p className="flex items-center gap-1.5 text-xs text-amber-600 sm:text-sm dark:text-amber-500">
            <TriangleAlert className="h-3.5 w-3.5 shrink-0" />
            {t('statistics.ipRanking.skippedNodes', { count: skippedNodeCount })}
          </p>
        )}
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-center gap-2" dir={dir}>
          <Select
            value={status}
            onValueChange={value => {
              setStatus(value as UserStatus | 'all')
              resetPage()
            }}
          >
            <SelectTrigger className="h-8 w-[130px] text-xs sm:h-9 sm:text-sm">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectGroup>
                <SelectItem value="all">{t('all')}</SelectItem>
                {Object.values(UserStatus).map(value => (
                  <SelectItem key={value} value={value}>
                    {t(`status.${value}`)}
                  </SelectItem>
                ))}
              </SelectGroup>
            </SelectContent>
          </Select>

          <div className="w-[180px]">
            <AdminFilterCombobox
              value={adminFilterValue}
              onValueChange={value => {
                setAdminFilterValue(value)
                resetPage()
              }}
              onAdminSelect={admin => setSelectedAdmin(admin)}
            />
          </div>

          <NodesFilter
            nodesData={nodesData}
            isLoadingNodes={isLoadingNodes}
            selectedIds={selectedNodeIds}
            onChange={ids => {
              setSelectedNodeIds(ids)
              resetPage()
            }}
          />

          <Input
            type="number"
            min={0}
            placeholder={t('statistics.ipRanking.minIps')}
            value={ipCountMin}
            onChange={e => {
              setIpCountMin(e.target.value)
              resetPage()
            }}
            className="h-8 w-24 text-xs sm:h-9 sm:text-sm"
          />
          <Input
            type="number"
            min={0}
            placeholder={t('statistics.ipRanking.maxIps')}
            value={ipCountMax}
            onChange={e => {
              setIpCountMax(e.target.value)
              resetPage()
            }}
            className="h-8 w-24 text-xs sm:h-9 sm:text-sm"
          />

          {hasActiveFilters && (
            <Button variant="ghost" size="sm" className="h-8 gap-1 text-xs sm:h-9" onClick={clearFilters}>
              <X className="h-3.5 w-3.5" />
              {t('clear')}
            </Button>
          )}
        </div>

        <div className="overflow-hidden rounded-md border">
          <Table dir={dir === 'rtl' ? 'rtl' : 'ltr'}>
            <TableHeader>
              <TableRow className="uppercase">
                <TableHead className={cn('text-xs', dir === 'rtl' && 'text-right')}>{t('username')}</TableHead>
                <TableHead className={cn('text-xs', dir === 'rtl' && 'text-right')}>{t('statistics.ipRanking.distinctIps')}</TableHead>
                <TableHead className={cn('text-xs', dir === 'rtl' && 'text-right')}>{t('statistics.trafficUsage')}</TableHead>
                <TableHead className={cn('text-xs', dir === 'rtl' && 'text-right')} />
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoadingData && rows.length === 0 ? (
                Array.from({ length: 5 }).map((_, i) => (
                  <TableRow key={`ip-ranking-skeleton-${i}`}>
                    <TableCell>
                      <Skeleton className="h-4 w-28" />
                    </TableCell>
                    <TableCell>
                      <Skeleton className="h-4 w-10" />
                    </TableCell>
                    <TableCell>
                      <Skeleton className="h-4 w-16" />
                    </TableCell>
                    <TableCell>
                      <Skeleton className="h-7 w-20" />
                    </TableCell>
                  </TableRow>
                ))
              ) : rows.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={4} className="text-muted-foreground h-24 text-center">
                    {t('noResults')}
                  </TableCell>
                </TableRow>
              ) : (
                rows.map(entry => (
                  <TableRow key={entry.user_id} className={cn(isFetching && 'opacity-70')}>
                    <TableCell className="font-medium whitespace-nowrap" dir="ltr">
                      {entry.username}
                    </TableCell>
                    <TableCell className="whitespace-nowrap tabular-nums">{entry.distinct_ip_count}</TableCell>
                    <TableCell className="whitespace-nowrap tabular-nums">{formatBytes(entry.used_traffic)}</TableCell>
                    <TableCell className="whitespace-nowrap">
                      <IpListPopover ips={entry.ips} distinctIpCount={entry.distinct_ip_count} />
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </div>

        <PaginationControls
          currentPage={page}
          totalPages={totalPages}
          itemsPerPage={itemsPerPage}
          totalItems={totalItems}
          isLoading={isLoadingData}
          onPageChange={newPage => setPage(newPage)}
          onItemsPerPageChange={value => {
            setItemsPerPage(value)
            resetPage()
          }}
        />
      </CardContent>
    </Card>
  )
}
