import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { getGetInboundRatiosQueryKey, type InboundRatio, updateInboundRatio } from '@/service/inbound-ratio'
import useDirDetection from '@/hooks/use-dir-detection'
import { cn } from '@/lib/utils'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Loader2, SearchIcon, X } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'

interface InboundRatioTableProps {
  data?: InboundRatio[]
  isLoading?: boolean
  canUpdate: boolean
}

interface PendingChange {
  tag: string
  value: number
}

const parseDraft = (draft: string | undefined): number | null => {
  if (draft === undefined || draft.trim() === '') return null
  const parsed = Number(draft)
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : null
}

const errorDetail = (error: unknown): string | undefined => {
  if (typeof error !== 'object' || error === null) return undefined
  const data = (error as { data?: { detail?: unknown } }).data
  const response = (error as { response?: { _data?: { detail?: unknown } } }).response
  const detail = data?.detail ?? response?._data?.detail
  return typeof detail === 'string' ? detail : undefined
}

/**
 * A count that reveals its items in a popover: hover on mouse devices, tap on touch.
 * Radix tooltips never open on tap, so a popover keeps both inputs working.
 */
function CountCell({
  count,
  items,
  label,
  canHover,
}: {
  count: number
  items: string[]
  label: string
  canHover: boolean
}) {
  const [open, setOpen] = useState(false)

  if (!count) return <span className="text-muted-foreground">—</span>

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <span
        className="inline-flex"
        onMouseEnter={canHover ? () => setOpen(true) : undefined}
        onMouseLeave={canHover ? () => setOpen(false) : undefined}
      >
        <PopoverTrigger asChild>
          <button
            type="button"
            aria-label={`${count} ${label}`}
            onClick={event => {
              // preventDefault suppresses the trigger's own toggle so tap and hover stay in sync.
              event.preventDefault()
              setOpen(current => !current)
            }}
            className="cursor-pointer rounded px-1 py-0.5 underline decoration-dotted underline-offset-2"
          >
            {count}
          </button>
        </PopoverTrigger>
      </span>
      <PopoverContent align="start" className="w-auto max-w-[260px] p-2">
        <div className="space-y-0.5">
          {items.map(item => (
            <div key={item} className="break-all">
              {item}
            </div>
          ))}
        </div>
      </PopoverContent>
    </Popover>
  )
}

export default function InboundRatioTable({ data, isLoading, canUpdate }: InboundRatioTableProps) {
  const { t } = useTranslation()
  const dir = useDirDetection()
  // TableHead ships with text-left, so RTL needs an explicit override or the labels sit at the
  // opposite edge of their column while the cells align to the start edge.
  const headAlign = dir === 'rtl' ? 'text-right' : 'text-left'
  const queryClient = useQueryClient()
  const [drafts, setDrafts] = useState<Record<string, string>>({})
  const [search, setSearch] = useState('')
  const canHover = useMemo(() => (typeof window === 'undefined' ? false : window.matchMedia('(hover: hover)').matches), [])

  const rows = useMemo(() => {
    const term = search.trim().toLowerCase()
    const list = data ?? []
    if (!term) return list
    // Only the tag is searched: protocol/network would make a term like "tcp" match every inbound.
    return list.filter(row => (row.tag ?? '').toLowerCase().includes(term))
  }, [data, search])

  const pending = useMemo<PendingChange[]>(() => {
    const changes: PendingChange[] = []
    for (const row of data ?? []) {
      const value = parseDraft(drafts[row.tag])
      if (value === null) continue
      if (Math.abs(value - (row.usage_coefficient ?? 1)) <= 1e-9) continue
      changes.push({ tag: row.tag, value })
    }
    return changes
  }, [data, drafts])

  const hasInvalid = useMemo(() => Object.values(drafts).some(draft => parseDraft(draft) === null), [drafts])
  const isDirty = Object.keys(drafts).length > 0

  const mutation = useMutation({
    mutationFn: (changes: PendingChange[]) => Promise.all(changes.map(change => updateInboundRatio(change.tag, change.value))),
    onSuccess: (updated: InboundRatio[]) => {
      // Write the returned rows straight into the cache so the inputs do not flicker back.
      queryClient.setQueryData<InboundRatio[]>(getGetInboundRatiosQueryKey(), previous => {
        if (!previous) return previous
        const byTag = new Map(updated.map(item => [item.tag, item]))
        return previous.map(row => byTag.get(row.tag) ?? row)
      })
      setDrafts({})
      queryClient.invalidateQueries({ queryKey: getGetInboundRatiosQueryKey() })
      toast.success(t('inboundsratioPage.saved', { defaultValue: 'Usage ratio saved' }))
    },
    onError: (error: unknown) => {
      queryClient.invalidateQueries({ queryKey: getGetInboundRatiosQueryKey() })
      toast.error(errorDetail(error) || t('inboundsratioPage.saveFailed', { defaultValue: 'Failed to save the usage ratio' }))
    },
  })

  const handleSubmit = () => {
    if (hasInvalid) {
      toast.error(t('inboundsratioPage.invalidRatio', { defaultValue: 'Usage ratio must be zero or a positive number' }))
      return
    }
    if (!pending.length) return
    mutation.mutate(pending)
  }

  const handleCancel = () => setDrafts({})

  return (
    <>
      <Card>
        <CardContent className="p-4">
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <div className="relative w-full sm:w-56">
              <SearchIcon
                className={cn(
                  'absolute',
                  dir === 'rtl' ? 'right-2' : 'left-2',
                  'text-muted-foreground top-1/2 h-4 w-4 -translate-y-1/2',
                )}
              />
              <Input
                value={search}
                onChange={event => setSearch(event.target.value)}
                placeholder={t('inboundsratioPage.searchPlaceholder', { defaultValue: 'Search inbounds…' })}
                className="h-8 pr-8 pl-8"
              />
              {search && (
                <button
                  type="button"
                  onClick={() => setSearch('')}
                  aria-label={t('clear', { defaultValue: 'Clear' })}
                  className={cn(
                    'absolute',
                    dir === 'rtl' ? 'left-2' : 'right-2',
                    'text-muted-foreground hover:text-foreground top-1/2 -translate-y-1/2',
                  )}
                >
                  <X className="h-4 w-4" />
                </button>
              )}
            </div>
          </div>

          <form
            onSubmit={event => {
              event.preventDefault()
              handleSubmit()
            }}
          >
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className={cn(headAlign, 'min-w-[100px]')}>{t('inboundsratioPage.tag', { defaultValue: 'Tag' })}</TableHead>
                    <TableHead className={cn(headAlign, 'hidden min-w-[80px] sm:table-cell')}>{t('inboundsratioPage.protocol', { defaultValue: 'Protocol' })}</TableHead>
                    <TableHead className={cn(headAlign, 'hidden min-w-[90px] sm:table-cell')}>{t('inboundsratioPage.network', { defaultValue: 'Network' })}</TableHead>
                    <TableHead className={cn(headAlign, 'min-w-[110px]')}>{t('inboundsratioPage.cores', { defaultValue: 'Core' })}</TableHead>
                    <TableHead className={cn(headAlign, 'w-[70px]')}>{t('inboundsratioPage.groups', { defaultValue: 'Groups' })}</TableHead>
                    <TableHead className={cn(headAlign, 'hidden w-[80px] md:table-cell')}>{t('inboundsratioPage.hosts', { defaultValue: 'Hosts' })}</TableHead>
                    <TableHead className={cn(headAlign, 'w-[110px] sm:w-[140px]')}>{t('inboundsratioPage.usageRatio', { defaultValue: 'Usage Ratio' })}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {rows.map(row => {
                    const draft = drafts[row.tag]
                    const draftValue = parseDraft(draft)
                    const stored = row.usage_coefficient ?? 1
                    const effective = draftValue ?? stored
                    const invalid = draft !== undefined && draftValue === null
                    const groups = row.groups ?? []
                    const cores = row.cores ?? []

                    return (
                      <TableRow key={row.tag}>
                        <TableCell className="font-medium">
                          <div className="flex items-center gap-2">
                            <span className="break-all">{row.tag}</span>
                            {Math.abs(effective - 1) > 1e-9 && (
                              <Badge variant="secondary" className="shrink-0">
                                ×{effective}
                              </Badge>
                            )}
                          </div>
                        </TableCell>
                        <TableCell className="text-muted-foreground hidden sm:table-cell">{row.protocol || '—'}</TableCell>
                        <TableCell className="text-muted-foreground hidden sm:table-cell">{row.network || '—'}</TableCell>
                        <TableCell className="text-muted-foreground min-w-[110px] break-words">
                          {cores.length ? cores.join(', ') : '—'}
                        </TableCell>
                        <TableCell className="text-muted-foreground">
                          <CountCell
                            count={groups.length}
                            items={groups}
                            label={t('inboundsratioPage.groups', { defaultValue: 'Groups' })}
                            canHover={canHover}
                          />
                        </TableCell>
                        <TableCell className="text-muted-foreground hidden md:table-cell">{row.hosts_count ?? 0}</TableCell>
                        <TableCell>
                          <Input
                            type="number"
                            inputMode="decimal"
                            min={0}
                            step="any"
                            disabled={!canUpdate}
                            aria-label={`${t('inboundsratioPage.usageRatio', { defaultValue: 'Usage Ratio' })} ${row.tag}`}
                            value={draft ?? String(stored)}
                            onChange={event => setDrafts(previous => ({ ...previous, [row.tag]: event.target.value }))}
                            onKeyDown={event => {
                              if (event.key === 'Escape') {
                                event.preventDefault()
                                setDrafts(previous => {
                                  const next = { ...previous }
                                  delete next[row.tag]
                                  return next
                                })
                              }
                            }}
                            className={`h-8 w-20 tabular-nums sm:w-24 ${invalid ? 'border-destructive focus-visible:ring-destructive' : ''}`}
                          />
                        </TableCell>
                      </TableRow>
                    )
                  })}
                  {!rows.length && (
                    <TableRow>
                      <TableCell colSpan={7} className="text-muted-foreground py-8 text-center text-sm">
                        {isLoading
                          ? t('loading', { defaultValue: 'Loading…' })
                          : t('inboundsratioPage.empty', { defaultValue: 'No inbounds found. Add an inbound to a core config first.' })}
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </div>

            <div className="mt-3 flex flex-col gap-2 border-t pt-3 sm:mt-6 sm:flex-row sm:gap-3 sm:pt-6">
              <div className="flex-1"></div>
              <div className="flex flex-col-reverse gap-2 sm:flex-row sm:gap-3">
                <Button
                  type="button"
                  variant="outline"
                  onClick={handleCancel}
                  disabled={!isDirty || mutation.isPending}
                  className="w-full min-w-[100px] sm:w-auto"
                >
                  {t('cancel')}
                </Button>
                <Button
                  type="submit"
                  disabled={!canUpdate || !pending.length || hasInvalid || mutation.isPending}
                  className="w-full min-w-[100px] sm:w-auto"
                >
                  {mutation.isPending ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin" />
                      {t('saving')}
                    </>
                  ) : (
                    t('save')
                  )}
                </Button>
              </div>
            </div>
          </form>
        </CardContent>
      </Card>
    </>
  )
}
