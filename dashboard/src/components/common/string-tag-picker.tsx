import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Separator } from '@/components/ui/separator'
import { cn } from '@/lib/utils'
import { Check, ChevronDown, Plus, Search, X } from 'lucide-react'
import type { ReactNode } from 'react'
import { useCallback, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'

export type StringTagPickerMode = 'single' | 'multi'

export interface StringTagPickerProps {
  mode: StringTagPickerMode
  options: readonly string[]
  disabled?: boolean
  className?: string
  /** single */
  valueSingle?: string
  onChangeSingle?: (next: string) => void
  /** multi */
  valueMulti?: string[]
  onChangeMulti?: (next: string[]) => void
  /** Shown when there are no profile tags (multi) — inside popover / trigger context. */
  emptyHint?: ReactNode
  placeholder?: string
  clearAllLabel?: string
  addButtonLabel?: string
}

function sortUniqueOptions(options: readonly string[]): string[] {
  return [...new Set(options.filter(t => typeof t === 'string' && t.trim() !== ''))].sort((a, b) => a.localeCompare(b))
}

function normalizeQuery(q: string): string {
  return q.trim().toLowerCase()
}

/** Tag picker: single (search + list + custom) or multi (checkboxes + chips + custom). */
export function StringTagPicker({
  mode,
  options,
  disabled,
  className,
  valueSingle = '',
  onChangeSingle,
  valueMulti = [],
  onChangeMulti,
  emptyHint,
  placeholder,
  clearAllLabel,
  addButtonLabel,
}: StringTagPickerProps) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [customDraft, setCustomDraft] = useState('')

  const sorted = useMemo(() => sortUniqueOptions(options), [options])

  const resetPopoverUi = useCallback(() => {
    setQuery('')
    setCustomDraft('')
  }, [])

  const handleOpenChange = useCallback(
    (next: boolean) => {
      setOpen(next)
      if (!next) resetPopoverUi()
    },
    [resetPopoverUi],
  )

  if (mode === 'single') {
    const trimmed = valueSingle.trim()
    const q = normalizeQuery(query)
    const filtered = q === '' ? sorted : sorted.filter(tag => tag.toLowerCase().includes(q))
    const canAddCustom =
      query.trim() !== '' && !sorted.some(t => t.toLowerCase() === query.trim().toLowerCase()) && query.trim() !== trimmed

    return (
      <Popover open={open} onOpenChange={handleOpenChange}>
        <PopoverTrigger asChild>
          <Button
            type="button"
            variant="outline"
            role="combobox"
            aria-expanded={open}
            disabled={disabled}
            dir="ltr"
            className={cn(
              'h-10 w-full min-w-0 justify-between gap-2 px-3 font-normal',
              !trimmed && 'text-muted-foreground',
              className,
            )}
          >
            <span className={cn('min-w-0 flex-1 truncate text-start text-sm', trimmed && 'text-foreground')}>
              {trimmed || placeholder || t('coreEditor.tagPicker.chooseTag', { defaultValue: 'Choose tag…' })}
            </span>
            <ChevronDown className="h-4 w-4 shrink-0 opacity-60" aria-hidden />
          </Button>
        </PopoverTrigger>
        <PopoverContent
          className="w-[var(--radix-popover-trigger-width)] min-w-[280px] max-w-[min(96vw,420px)] p-0"
          align="start"
          onWheel={e => e.stopPropagation()}
          onTouchMove={e => e.stopPropagation()}
        >
          <div className="flex flex-col gap-0">
            <div className="border-b p-2">
              <div className="relative">
                <Search className="pointer-events-none absolute start-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
                <Input
                  dir="ltr"
                  className="h-9 ps-8 text-sm"
                  placeholder={t('coreEditor.tagPicker.searchTags', { defaultValue: 'Search or type a tag…' })}
                  value={query}
                  onChange={e => setQuery(e.target.value)}
                  disabled={disabled}
                  autoFocus
                />
              </div>
            </div>

            <ScrollArea className="max-h-[min(50dvh,240px)]">
              <div className="p-1.5" dir="ltr">
                <button
                  type="button"
                  disabled={disabled}
                  onClick={() => {
                    onChangeSingle?.('')
                    setOpen(false)
                  }}
                  className={cn(
                    'flex w-full items-center gap-2 rounded-sm px-2 py-2 text-start text-xs transition-colors hover:bg-accent',
                    trimmed === '' && 'bg-accent/60',
                  )}
                >
                  <span className="text-muted-foreground">{placeholder ?? '—'}</span>
                  {trimmed === '' ? <Check className="ms-auto h-3.5 w-3.5 shrink-0" /> : null}
                </button>

                {trimmed !== '' && !sorted.some(t => t === trimmed) ? (
                  <div className="rounded-sm border border-dashed px-2 py-1.5 text-[11px] text-muted-foreground">
                    {t('coreEditor.tagPicker.customValueActive', {
                      defaultValue: 'Using custom tag (not in profile list):',
                    })}{' '}
                    <span className=" text-foreground">{trimmed}</span>
                  </div>
                ) : null}

                {filtered.length === 0 && q !== '' ? (
                  <p className="px-2 py-3 text-center text-xs text-muted-foreground">
                    {t('coreEditor.tagPicker.noMatches', { defaultValue: 'No matching tags.' })}
                  </p>
                ) : (
                  filtered.map(tag => {
                    const selected = tag === trimmed
                    return (
                      <button
                        key={tag}
                        type="button"
                        disabled={disabled}
                        onClick={() => {
                          onChangeSingle?.(tag)
                          setOpen(false)
                        }}
                        className={cn(
                          'flex w-full items-center gap-2 rounded-sm px-2 py-2 text-start text-sm transition-colors hover:bg-accent',
                          selected && 'bg-accent/70',
                        )}
                      >
                        <span className="min-w-0 flex-1 truncate">{tag}</span>
                        {selected ? <Check className="h-3.5 w-3.5 shrink-0" /> : null}
                      </button>
                    )
                  })
                )}
              </div>
            </ScrollArea>

            <Separator />

            <div className="space-y-2 p-2">
              <p className="text-[11px] font-medium text-muted-foreground">
                {t('coreEditor.tagPicker.customTag', { defaultValue: 'Custom tag' })}
              </p>
              <div className="flex gap-2">
                <Input
                  dir="ltr"
                  className="h-9 text-sm"
                  placeholder={t('coreEditor.tagPicker.customPlaceholder', { defaultValue: 'e.g. proxy-1' })}
                  value={customDraft}
                  onChange={e => setCustomDraft(e.target.value)}
                  disabled={disabled}
                  onKeyDown={e => {
                    if (e.key === 'Enter') {
                      e.preventDefault()
                      const v = customDraft.trim()
                      if (v && onChangeSingle) {
                        onChangeSingle(v)
                        setOpen(false)
                        setCustomDraft('')
                      }
                    }
                  }}
                />
                <Button
                  type="button"
                  size="sm"
                  className="h-9 shrink-0"
                  disabled={disabled || customDraft.trim() === ''}
                  onClick={() => {
                    const v = customDraft.trim()
                    if (!v || !onChangeSingle) return
                    onChangeSingle(v)
                    setOpen(false)
                    setCustomDraft('')
                  }}
                >
                  {t('coreEditor.tagPicker.apply', { defaultValue: 'Apply' })}
                </Button>
              </div>
              {canAddCustom ? (
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  className="h-8 w-full text-xs"
                  disabled={disabled}
                  onClick={() => {
                    onChangeSingle?.(query.trim())
                    setOpen(false)
                  }}
                >
                  {t('coreEditor.tagPicker.useSearchAsTag', {
                    defaultValue: 'Use "{{tag}}" as tag',
                    tag: query.trim(),
                  })}
                </Button>
              ) : null}
            </div>
          </div>
        </PopoverContent>
      </Popover>
    )
  }

  const list = valueMulti ?? []
  const qn = normalizeQuery(query)
  const available = sorted.filter(t => !list.includes(t))
  const filteredAvailable = qn === '' ? available : available.filter(t => t.toLowerCase().includes(qn))
  const queryTrim = query.trim()
  const canAddFromSearch =
    queryTrim !== '' &&
    !list.some(t => t.toLowerCase() === queryTrim.toLowerCase()) &&
    !sorted.some(t => t.toLowerCase() === queryTrim.toLowerCase())

  return (
    <Popover open={open} onOpenChange={handleOpenChange}>
      <PopoverTrigger asChild>
        <Button
          type="button"
          variant="outline"
          role="combobox"
          aria-expanded={open}
          disabled={disabled}
          dir="ltr"
          className={cn('h-auto min-h-10 w-full min-w-0 justify-between gap-2 p-2 text-left font-normal', className)}
        >
          <div className="flex min-w-0 flex-1 flex-wrap items-center gap-1.5">
            {list.length === 0 ? (
              <span className="text-sm text-muted-foreground">{placeholder}</span>
            ) : (
              list.map(tag => (
                <Badge key={tag} variant="secondary" className="max-w-full gap-1 py-0.5 pl-2 pr-1  text-[11px] font-normal">
                  <span className="truncate">{tag}</span>
                  <span
                    role="button"
                    tabIndex={0}
                    className="inline-flex shrink-0 rounded p-0.5 hover:bg-muted-foreground/20"
                    onClick={e => {
                      e.preventDefault()
                      e.stopPropagation()
                      if (disabled) return
                      onChangeMulti?.(list.filter(x => x !== tag))
                    }}
                    onKeyDown={e => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault()
                        e.stopPropagation()
                        if (disabled) return
                        onChangeMulti?.(list.filter(x => x !== tag))
                      }
                    }}
                    aria-label={t('coreEditor.tagPicker.removeTag', { defaultValue: 'Remove {{tag}}', tag })}
                  >
                    <X className="h-3 w-3" />
                  </span>
                </Badge>
              ))
            )}
          </div>
          <div className="flex shrink-0 items-center gap-1.5">
            {list.length > 0 ? (
              <span className="rounded-md bg-muted px-1.5 py-0.5 text-[10px] font-medium tabular-nums text-muted-foreground">
                {list.length}
              </span>
            ) : null}
            <ChevronDown className="h-4 w-4 shrink-0 opacity-60" aria-hidden />
          </div>
        </Button>
      </PopoverTrigger>
      <PopoverContent
        className="w-[min(96vw,400px)] p-0"
        align="start"
        side="bottom"
        onWheel={e => e.stopPropagation()}
        onTouchMove={e => e.stopPropagation()}
      >
        <div className="flex max-h-[min(72dvh,28rem)] flex-col">
          <div className="border-b p-2">
            <div className="relative">
              <Search className="pointer-events-none absolute start-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
              <Input
                dir="ltr"
                className="h-9 ps-8 text-sm"
                placeholder={t('coreEditor.tagPicker.searchOrAdd', { defaultValue: 'Search tags or type to add…' })}
                value={query}
                onChange={e => setQuery(e.target.value)}
                disabled={disabled}
              />
            </div>
          </div>

          {sorted.length === 0 && !queryTrim ? (
            <div className="px-3 py-4 text-xs leading-snug text-muted-foreground">{emptyHint}</div>
          ) : (
            <>
              <ScrollArea className="min-h-0 flex-1">
                <div className="space-y-0.5 p-2" dir="ltr">
                  {filteredAvailable.length === 0 && queryTrim && sorted.length > 0 ? (
                    <p className="px-1 py-2 text-center text-xs text-muted-foreground">
                      {t('coreEditor.tagPicker.allMatchingAdded', { defaultValue: 'All matching tags are already selected.' })}
                    </p>
                  ) : null}

                  {filteredAvailable.map(tag => (
                    <button
                      key={tag}
                      type="button"
                      disabled={disabled}
                      onClick={() => onChangeMulti?.([...list, tag])}
                      className="flex w-full items-center gap-2 rounded-md px-2 py-2 text-start transition-colors hover:bg-accent/80 disabled:pointer-events-none disabled:opacity-50"
                    >
                      <Plus className="h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-hidden />
                      <span className="min-w-0 flex-1 truncate text-sm">{tag}</span>
                    </button>
                  ))}

                  {sorted.length === 0 && queryTrim ? (
                    <p className="px-1 py-2 text-xs text-muted-foreground">
                      {t('coreEditor.tagPicker.noProfileTags', {
                        defaultValue: 'No tags from the profile. Add a custom tag below.',
                      })}
                    </p>
                  ) : null}
                </div>
              </ScrollArea>

              {canAddFromSearch ? (
                <div className="border-t px-2 py-2">
                  <Button
                    type="button"
                    variant="secondary"
                    size="sm"
                    className="h-8 w-full text-sm"
                    disabled={disabled}
                    onClick={() => {
                      onChangeMulti?.([...list, queryTrim])
                      setQuery('')
                    }}
                  >
                    {addButtonLabel ??
                      t('coreEditor.tagPicker.addCustomTag', {
                        defaultValue: 'Add "{{tag}}"',
                        tag: queryTrim,
                      })}
                  </Button>
                </div>
              ) : null}

              {list.length > 0 ? (
                <>
                  <Separator />
                  <div className="space-y-2 px-2 py-2">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-xs font-medium text-muted-foreground">
                        {t('coreEditor.tagPicker.selectedTags', { count: list.length, defaultValue: 'Selected ({{count}})' })}
                      </span>
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        className="h-7 text-xs text-muted-foreground hover:text-destructive"
                        disabled={disabled}
                        onClick={() => onChangeMulti?.([])}
                      >
                        {clearAllLabel}
                      </Button>
                    </div>
                    <div className="flex max-h-24 flex-wrap gap-1 overflow-y-auto overscroll-contain">
                      {list.map(tag => (
                        <Badge key={tag} variant="outline" className="gap-1 py-0.5 pl-2 pr-1  text-[11px] font-normal">
                          <span className="max-w-[200px] truncate">{tag}</span>
                          <button
                            type="button"
                            className="rounded p-0.5 hover:bg-destructive/15 hover:text-destructive"
                            disabled={disabled}
                            onClick={() => onChangeMulti?.(list.filter(x => x !== tag))}
                            aria-label={t('coreEditor.tagPicker.removeTag', { defaultValue: 'Remove {{tag}}', tag })}
                          >
                            <X className="h-3 w-3" />
                          </button>
                        </Badge>
                      ))}
                    </div>
                  </div>
                </>
              ) : null}
            </>
          )}
        </div>
      </PopoverContent>
    </Popover>
  )
}
