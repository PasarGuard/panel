import { FormControl } from '@/components/ui/form'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { StringArrayPopoverInput } from '@/components/common/string-array-popover-input'
import { StringTagPicker } from '@/components/common/string-tag-picker'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import { Button } from '@/components/ui/button'
import { TcpHeaderObfuscationForm } from '@/features/core-editor/components/shared/tcp-header-obfuscation-form'
import type { XrayGeneratedFormField } from '@pasarguard/xray-config-kit'
import {
  inferParityFieldMode,
  stringifyJsonFormRecord,
  TLS_CURVE_PREFERENCE_OPTIONS,
  type ParityFieldMode,
} from '@/features/core-editor/kit/xray-parity-value'
import { cn } from '@/lib/utils'
import { Plus, Trash2, X } from 'lucide-react'
import { useTranslation } from 'react-i18next'

/** Tags available from the current profile — used to render pickers for routing / balancer parity fields. */
export type XrayProfileTagOptions = {
  readonly outboundTags: readonly string[]
  readonly inboundTags: readonly string[]
  readonly balancerTags: readonly string[]
}

export interface XrayParityFormControlProps {
  field: XrayGeneratedFormField
  value: string
  onChange: (next: string) => void
  disabled?: boolean
  className?: string
  renderBooleanAsToggleRow?: boolean
  profileTagOptions?: XrayProfileTagOptions
  /** Optional input placeholder (plain text; not i18n). Used for scalar inputs, string lists, and JSON textarea fallback. */
  placeholder?: string
}

/** Normalizes Go/JSON field names for `coreEditor.transportFields.<key>` labels. */
export function normalizeXrayParityFieldKey(field: XrayGeneratedFormField): string {
  return String(field.go || field.json || '')
    .replace(/[^a-zA-Z0-9]/g, '')
    .toLowerCase()
}

/** Product / protocol names spelled the same in every locale — omit from JSON, render as plain text. */
const TRANSPORT_FIELD_LOCALE_INVARIANT_LABELS: Readonly<Record<string, string>> = {
  spiderx: 'Spider X',
}

export function transportParityFieldLabel(field: XrayGeneratedFormField, t: (key: string, o?: { defaultValue?: string }) => string): string {
  const key = normalizeXrayParityFieldKey(field)
  const invariant = TRANSPORT_FIELD_LOCALE_INVARIANT_LABELS[key]
  if (invariant !== undefined) return invariant
  return t(`coreEditor.transportFields.${key}`, { defaultValue: field.go || field.json || '' })
}

function normalizeFieldName(field: XrayGeneratedFormField): string {
  return normalizeXrayParityFieldKey(field)
}

function parseRangeValue(value: string): { min: string; max: string } {
  const raw = value.trim()
  if (!raw) return { min: '', max: '' }
  try {
    const parsed = JSON.parse(raw) as unknown
    if (typeof parsed === 'object' && parsed !== null) {
      const record = parsed as Record<string, unknown>
      const min = record.min ?? record.from ?? record.start ?? ''
      const max = record.max ?? record.to ?? record.end ?? ''
      return { min: String(min), max: String(max) }
    }
  } catch {
    // Keep parsing with text format.
  }

  const match = raw.match(/^\s*(-?\d+)\s*[-,:]\s*(-?\d+)\s*$/)
  if (!match) return { min: raw, max: '' }
  return { min: match[1], max: match[2] }
}

function buildRangeValue(min: string, max: string): string {
  const left = min.trim()
  const right = max.trim()
  if (!left && !right) return ''
  if (!right) return left
  if (!left) return right
  return `${left}-${right}`
}

function parseStringListValue(value: string): string[] {
  const raw = value.trim()
  if (!raw) return []
  try {
    const parsed = JSON.parse(raw) as unknown
    if (Array.isArray(parsed)) {
      return parsed.map(item => String(item).trim()).filter(Boolean)
    }
  } catch {
    // Keep parsing with text format.
  }
  return value
    .split(/[\n,]+/)
    .map(item => item.trim())
    .filter(Boolean)
}

function stringifyStringListValue(items: string[]): string {
  return items.join('\n')
}

function selectOptionsForField(field: XrayGeneratedFormField): string[] | null {
  const key = normalizeFieldName(field)

  if (key === 'mode') {
    return ['auto', 'packet-up', 'stream-up', 'stream-one']
  }

  if (key.includes('minversion') || key.includes('maxversion') || key === 'version') {
    return ['1.0', '1.1', '1.2', '1.3']
  }

  if (key.includes('fingerprint')) {
    return [
      'chrome',
      'firefox',
      'safari',
      'ios',
      'android',
      'edge',
      '360',
      'qq',
      'random',
      'randomized',
      'randomizednoalpn',
      'unsafe',
    ]
  }

  if (key === 'uplinkhttpmethod') {
    return ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS']
  }

  if (key === 'xpaddingmethod') {
    return ['repeat-x', 'tokenish']
  }

  if (key === 'xpaddingplacement' || key === 'sessionplacement' || key === 'seqplacement') {
    if (key === 'xpaddingplacement') return ['queryInHeader', 'query', 'header', 'cookie']
    return ['path', 'query', 'header', 'cookie']
  }

  return null
}

export function isBooleanParityField(field: XrayGeneratedFormField): boolean {
  const key = normalizeFieldName(field)
  return field.type === 'bool' || key === 'xpaddingobfsmode'
}

export function isStringMapField(field: XrayGeneratedFormField): boolean {
  const key = normalizeFieldName(field)
  return key === 'requestheaders' || key === 'responseheaders' || key === 'headers' || key === 'attributes'
}

export function isWebhookField(field: XrayGeneratedFormField): boolean {
  const key = normalizeFieldName(field)
  return key === 'webhook'
}

export function isJsonRawMessageField(field: XrayGeneratedFormField): boolean {
  const key = normalizeFieldName(field)
  return key === 'obfuscationheaders' || key === 'headerconfig'
}

function parseStringMapEntries(value: string): Array<{ key: string; value: string }> | null {
  const raw = value.trim()
  if (!raw) return []
  try {
    const parsed = JSON.parse(raw) as unknown
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return null
    return Object.entries(parsed as Record<string, unknown>).map(([k, v]) => ({
      key: String(k),
      value: v == null ? '' : String(v),
    }))
  } catch {
    return null
  }
}

function stringifyStringMapEntries(entries: Array<{ key: string; value: string }>): string {
  const next: Record<string, string> = {}
  for (const entry of entries) {
    const key = entry.key.trim()
    if (!key) continue
    next[key] = entry.value
  }
  if (Object.keys(next).length === 0) return ''
  return JSON.stringify(next, null, 2)
}

function parseJsonObject(value: string): Record<string, unknown> | null {
  const raw = value.trim()
  if (!raw) return null
  try {
    const parsed = JSON.parse(raw) as unknown
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return null
    return parsed as Record<string, unknown>
  } catch {
    return null
  }
}

function parsePrimitive(raw: string): unknown {
  const t = raw.trim()
  if (!t) return ''
  if (t === 'true') return true
  if (t === 'false') return false
  if (t === 'null') return null
  const num = Number(t)
  if (Number.isFinite(num) && /^-?\d+(\.\d+)?$/.test(t)) return num
  return raw
}

function tagPickerSpec(
  normalizedKey: string,
  mode: ParityFieldMode,
  o: XrayProfileTagOptions | undefined,
): { kind: 'single' | 'multi'; options: readonly string[] } | null {
  if (!o) return null
  if (normalizedKey === 'outboundtag' && mode === 'scalar') {
    return { kind: 'single', options: o.outboundTags }
  }
  if (normalizedKey === 'balancertag' && mode === 'scalar') {
    return { kind: 'single', options: o.balancerTags }
  }
  if (normalizedKey === 'fallbacktag' && mode === 'scalar') {
    return { kind: 'single', options: o.outboundTags }
  }
  if ((normalizedKey === 'inboundtag' || normalizedKey === 'sourcetag') && mode === 'stringList') {
    return { kind: 'multi', options: o.inboundTags }
  }
  if (normalizedKey === 'selector' && mode === 'stringList') {
    return { kind: 'multi', options: o.outboundTags }
  }
  return null
}

const ALPN_OPTIONS = ['h3', 'h2', 'http/1.1'] as const
const TLS_CIPHER_SUITES_RECOMMENDED =
  'TLS_ECDHE_ECDSA_WITH_CHACHA20_POLY1305_SHA256:TLS_ECDHE_RSA_WITH_CHACHA20_POLY1305_SHA256:TLS_ECDHE_ECDSA_WITH_AES_256_GCM_SHA384:TLS_ECDHE_RSA_WITH_AES_256_GCM_SHA384:TLS_ECDHE_ECDSA_WITH_AES_128_GCM_SHA256:TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256'

/** Renders a single parity metadata field (scalar input, multiline list, or JSON). */
export function XrayParityFormControl({
  field,
  value,
  onChange,
  disabled,
  className,
  renderBooleanAsToggleRow = false,
  profileTagOptions,
  placeholder,
}: XrayParityFormControlProps) {
  const { t } = useTranslation()
  const key = normalizeFieldName(field)

  if (isBooleanParityField(field)) {
    const checked = value === 'true' || value === '1'
    if (renderBooleanAsToggleRow) {
      return (
        <FormControl>
          <div
            className={cn('flex h-10 cursor-pointer items-center justify-between gap-3 rounded-lg border px-3', className)}
            onClick={() => {
              if (!disabled) onChange(checked ? 'false' : 'true')
            }}
          >
            <span className="truncate text-sm font-medium">{transportParityFieldLabel(field, t)}</span>
            <div className="flex shrink-0 items-center" onClick={e => e.stopPropagation()}>
              <Switch checked={checked} onCheckedChange={next => onChange(next ? 'true' : 'false')} disabled={disabled} />
            </div>
          </div>
        </FormControl>
      )
    }
    return (
      <FormControl>
        <div className={cn('flex h-10 items-center rounded-md border px-3', className)}>
          <Switch checked={checked} onCheckedChange={next => onChange(next ? 'true' : 'false')} disabled={disabled} />
        </div>
      </FormControl>
    )
  }

  if (field.type === 'Int32Range' || key === 'xpaddingbytes') {
    const { min, max } = parseRangeValue(value)
    return (
      <FormControl>
        <div className={cn('grid min-w-0 w-full grid-cols-2 gap-2', className)}>
          <Input
            type="number"
            dir="ltr"
            inputMode="numeric"
            placeholder={t('coreEditor.parityUi.rangeMinPlaceholder', { defaultValue: 'Min' })}
            value={min}
            onChange={e => onChange(buildRangeValue(e.target.value, max))}
            disabled={disabled}
            className="min-w-0 w-full text-xs"
          />
          <Input
            type="number"
            dir="ltr"
            inputMode="numeric"
            placeholder={t('coreEditor.parityUi.rangeMaxPlaceholder', { defaultValue: 'Max' })}
            value={max}
            onChange={e => onChange(buildRangeValue(min, e.target.value))}
            disabled={disabled}
            className="min-w-0 w-full text-xs"
          />
        </div>
      </FormControl>
    )
  }

  const selectOptions = selectOptionsForField(field)
  if (selectOptions) {
    const hasCustomValue = value.trim().length > 0 && !selectOptions.includes(value)
    return (
      <FormControl>
        <Select value={value || '__empty__'} onValueChange={next => onChange(next === '__empty__' ? '' : next)} disabled={disabled}>
          <SelectTrigger className={cn('h-10 w-full min-w-0', className)}>
            <SelectValue
              placeholder={placeholder ?? t('coreEditor.parityUi.selectValuePlaceholder', { defaultValue: 'Select value' })}
            />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__empty__">{t('coreEditor.parityUi.selectDefault', { defaultValue: 'Default' })}</SelectItem>
            {hasCustomValue && <SelectItem value={value}>{value}</SelectItem>}
            {selectOptions.map(option => (
              <SelectItem key={option} value={option}>
                {option}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </FormControl>
    )
  }

  // TCP header obfuscation prettier UI
  if (isJsonRawMessageField(field)) {
    try {
      const parsed = value.trim() ? JSON.parse(value) : null
      if (key === 'obfuscationheaders') {
        return (
          <FormControl className={className}>
            <TcpHeaderObfuscationForm
              currentValue={parsed}
              onValueChange={next => {
                if (next == null) onChange('')
                else if (typeof next === 'object' && !Array.isArray(next))
                  onChange(stringifyJsonFormRecord(next as Record<string, unknown>))
                else onChange(JSON.stringify(next, null, 2))
              }}
            />
          </FormControl>
        )
      }
    } catch {
      // Fall through to JSON textarea
    }
  }

  if (isStringMapField(field)) {
    const entries = parseStringMapEntries(value)
    if (entries) {
      const updateEntry = (index: number, patch: Partial<{ key: string; value: string }>) => {
        const next = entries.map((entry, i) => (i === index ? { ...entry, ...patch } : entry))
        onChange(stringifyStringMapEntries(next))
      }
      const removeEntry = (index: number) => {
        onChange(stringifyStringMapEntries(entries.filter((_, i) => i !== index)))
      }
      const addEntry = () => {
        const nextKey = `header_${entries.length + 1}`
        onChange(stringifyStringMapEntries([...entries, { key: nextKey, value: '' }]))
      }

      return (
        <FormControl>
          <div className={cn('flex flex-col gap-2', className)}>
            <div className="flex items-center justify-end">
              <Button type="button" variant="outline" size="icon" className="size-7" onClick={addEntry}>
                <Plus />
              </Button>
            </div>
            <div className="flex flex-col gap-2">
              {entries.length === 0 ? (
                <div className="rounded-md border border-dashed px-3 py-2 text-xs text-muted-foreground">
                  {t('coreEditor.inbound.tcp.stringMapNoHeaders', {
                    defaultValue: 'No headers yet. Click + to add one.',
                  })}
                </div>
              ) : (
                entries.map((entry, index) => (
                  <div
                    key={`${entry.key}-${index}`}
                    className="flex w-full min-w-0 flex-wrap items-center gap-2 sm:flex-nowrap"
                  >
                    <Input
                      dir="ltr"
                      className="min-h-9 min-w-[7rem] flex-1 text-xs sm:min-w-[8rem]"
                      defaultValue={entry.key}
                      onBlur={e => {
                        if (e.target.value !== entry.key) updateEntry(index, { key: e.target.value })
                      }}
                      disabled={disabled}
                      placeholder={t('coreEditor.inbound.tcp.header.name', { defaultValue: 'Header name' })}
                    />
                    <Input
                      dir="ltr"
                      className="min-h-9 min-w-0 flex-[2] text-xs"
                      defaultValue={entry.value}
                      onBlur={e => {
                        if (e.target.value !== entry.value) updateEntry(index, { value: e.target.value })
                      }}
                      disabled={disabled}
                      placeholder={t('coreEditor.inbound.tcp.header.value', { defaultValue: 'Header value' })}
                    />
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      className="size-9 shrink-0 self-center border-red-500/20 transition-colors hover:border-red-500 hover:bg-red-50 dark:hover:bg-red-950/20"
                      onClick={() => removeEntry(index)}
                      disabled={disabled}
                    >
                      <Trash2 className="text-red-500" />
                    </Button>
                  </div>
                ))
              )}
            </div>
          </div>
        </FormControl>
      )
    }
  }

  if (key === 'curvepreferences') {
    const selected = parseStringListValue(value)
    const allowed = new Set<string>(TLS_CURVE_PREFERENCE_OPTIONS as readonly string[])
    const unknown = selected.filter(s => !allowed.has(s))
    const knownOrdered = (TLS_CURVE_PREFERENCE_OPTIONS as readonly string[]).filter(opt => selected.includes(opt))
    const display = [...knownOrdered, ...unknown]

    return (
      <FormControl>
        <Popover>
          <PopoverTrigger asChild>
            <Button variant="outline" role="combobox" className={cn('h-auto min-h-[40px] w-full justify-between p-2', className)} disabled={disabled}>
              <div className="flex flex-1 flex-wrap gap-2">
                {display.length > 0 ? (
                  display.map(curve => (
                    <Badge
                      key={curve}
                      variant={allowed.has(curve) ? 'secondary' : 'outline'}
                      className="flex items-center gap-1"
                    >
                      {curve}
                      <X
                        className="h-3 w-3 cursor-pointer hover:text-destructive"
                        onClick={e => {
                          e.stopPropagation()
                          onChange(stringifyStringListValue(selected.filter(p => p !== curve)))
                        }}
                      />
                    </Badge>
                  ))
                ) : (
                  <span className="text-sm text-muted-foreground">
                    {t('coreEditor.field.curvePreferencesPlaceholder', {
                      defaultValue: 'Select TLS curves (ECDHE)',
                    })}
                  </span>
                )}
              </div>
            </Button>
          </PopoverTrigger>
          <PopoverContent className="min-w-56 p-1 sm:min-w-72" align="start">
            <p className="px-2 pb-1 pt-1 text-[11px] leading-snug text-muted-foreground">
              {t('coreEditor.field.curvePreferencesHint', {
                defaultValue: 'Only documented Xray curve names can be added. Unsupported values from JSON are shown above and can be removed.',
              })}
            </p>
            <div className="space-y-1">
              {TLS_CURVE_PREFERENCE_OPTIONS.map(curve => {
                const isSelected = selected.includes(curve)
                return (
                  <div
                    key={curve}
                    onClick={() => {
                      if (disabled) return
                      const next = isSelected ? selected.filter(p => p !== curve) : [...selected, curve]
                      onChange(stringifyStringListValue(next))
                    }}
                    className="flex cursor-pointer items-center gap-2 rounded-sm p-2 hover:bg-accent"
                  >
                    <div
                      className={cn(
                        'flex h-4 w-4 shrink-0 items-center justify-center rounded-sm border',
                        isSelected ? 'border-primary bg-primary' : 'border-muted',
                      )}
                    >
                      {isSelected && <X className="h-3 w-3 text-primary-foreground" />}
                    </div>
                    <span className="text-sm">{curve}</span>
                  </div>
                )
              })}
            </div>
          </PopoverContent>
        </Popover>
      </FormControl>
    )
  }

  if (key === 'alpn') {
    const selected = parseStringListValue(value)
    return (
      <FormControl>
        <Popover>
          <PopoverTrigger asChild>
            <Button variant="outline" role="combobox" className={cn('h-auto min-h-[40px] w-full justify-between p-2', className)} disabled={disabled}>
              <div className="flex flex-1 flex-wrap gap-2">
                {selected.length > 0 ? (
                  selected.map(protocol => (
                    <Badge key={protocol} variant="secondary" className="flex items-center gap-1">
                      {protocol}
                      <X
                        className="h-3 w-3 cursor-pointer hover:text-destructive"
                        onClick={e => {
                          e.stopPropagation()
                          onChange(stringifyStringListValue(selected.filter(p => p !== protocol)))
                        }}
                      />
                    </Badge>
                  ))
                ) : (
                  <span className="text-sm text-muted-foreground">
                    {t('coreEditor.field.selectAlpnProtocols', { defaultValue: 'Select ALPN protocols' })}
                  </span>
                )}
              </div>
            </Button>
          </PopoverTrigger>
          <PopoverContent className="w-full p-1" align="start">
            <div className="space-y-1">
              {ALPN_OPTIONS.map(protocol => {
                const isSelected = selected.includes(protocol)
                return (
                  <div
                    key={protocol}
                    onClick={() => {
                      if (disabled) return
                      const next = isSelected ? selected.filter(p => p !== protocol) : [...selected, protocol]
                      onChange(stringifyStringListValue(next))
                    }}
                    className="flex cursor-pointer items-center gap-2 rounded-sm p-2 hover:bg-accent"
                  >
                    <div className={cn('mr-2 flex h-4 w-4 items-center justify-center rounded-sm border', isSelected ? 'border-primary bg-primary' : 'border-muted')}>
                      {isSelected && <X className="h-3 w-3 text-primary-foreground" />}
                    </div>
                    {protocol}
                  </div>
                )
              })}
            </div>
          </PopoverContent>
        </Popover>
      </FormControl>
    )
  }

  if (key === 'ciphersuites') {
    const current = value.trim()
    const resolvedValue = !current ? '__auto__' : current === TLS_CIPHER_SUITES_RECOMMENDED ? '__recommended__' : '__custom__'
    return (
      <FormControl>
        <Select
          value={resolvedValue}
          onValueChange={next => {
            if (next === '__auto__') onChange('')
            else if (next === '__recommended__') onChange(TLS_CIPHER_SUITES_RECOMMENDED)
          }}
          disabled={disabled}
        >
          <SelectTrigger className={cn('h-10 w-full min-w-0', className)}>
            <SelectValue placeholder={t('coreEditor.parityUi.selectAuto', { defaultValue: 'Auto' })} />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__auto__">{t('coreEditor.parityUi.selectAuto', { defaultValue: 'Auto' })}</SelectItem>
            <SelectItem value="__recommended__">{t('coreEditor.parityUi.selectRecommended', { defaultValue: 'Recommended' })}</SelectItem>
            {resolvedValue === '__custom__' && (
              <SelectItem value="__custom__">{t('coreEditor.parityUi.selectCustomFromJson', { defaultValue: 'Custom (from JSON)' })}</SelectItem>
            )}
          </SelectContent>
        </Select>
      </FormControl>
    )
  }

  // PortList → plain text input for comma-separated port ranges like "53,443,1000-2000"
  if (field.type.includes('PortList')) {
    return (
      <FormControl>
        <Input
          className={cn('w-full min-w-0 text-xs', className)}
          dir="ltr"
          placeholder={t('coreEditor.parityUi.portListPlaceholder', { defaultValue: 'e.g. 53,443,1000-2000' })}
          value={value}
          onChange={e => onChange(e.target.value)}
          disabled={disabled}
        />
      </FormControl>
    )
  }

  // NetworkList → select: tcp / udp / tcp,udp
  if (field.type.includes('NetworkList')) {
    return (
      <FormControl>
        <Select
          value={value || '__empty__'}
          onValueChange={next => onChange(next === '__empty__' ? '' : next)}
          disabled={disabled}
        >
          <SelectTrigger className={cn('h-10 w-full min-w-0', className)}>
            <SelectValue placeholder={t('coreEditor.parityUi.networkAny', { defaultValue: 'Any' })} />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__empty__">{t('coreEditor.parityUi.networkAny', { defaultValue: 'Any' })}</SelectItem>
            <SelectItem value="tcp">TCP</SelectItem>
            <SelectItem value="udp">UDP</SelectItem>
            <SelectItem value="tcp,udp">TCP + UDP</SelectItem>
          </SelectContent>
        </Select>
      </FormControl>
    )
  }

  // Routing protocol field (go: "Protocols") → multi-badge picker for sniffed protocol types
  if (key === 'protocols') {
    const ROUTING_PROTOCOL_OPTIONS = ['http', 'tls', 'quic', 'bittorrent'] as const
    const selected = parseStringListValue(value)
    return (
      <FormControl>
        <Popover>
          <PopoverTrigger asChild>
            <Button
              variant="outline"
              role="combobox"
              className={cn('h-auto min-h-[40px] w-full justify-between p-2', className)}
              disabled={disabled}
            >
              <div className="flex flex-1 flex-wrap gap-1.5">
                {selected.length > 0 ? (
                  selected.map(p => (
                    <Badge key={p} variant="secondary" className="flex items-center gap-1">
                      {p}
                      <X
                        className="h-3 w-3 cursor-pointer hover:text-destructive"
                        onClick={e => {
                          e.stopPropagation()
                          onChange(stringifyStringListValue(selected.filter(x => x !== p)))
                        }}
                      />
                    </Badge>
                  ))
                ) : (
                  <span className="text-sm text-muted-foreground">{t('coreEditor.parityUi.protocolAny', { defaultValue: 'Any protocol' })}</span>
                )}
              </div>
            </Button>
          </PopoverTrigger>
          <PopoverContent className="w-full p-1" align="start">
            <div className="space-y-1">
              {ROUTING_PROTOCOL_OPTIONS.map(p => {
                const isSelected = selected.includes(p)
                return (
                  <div
                    key={p}
                    onClick={() => {
                      if (disabled) return
                      const next = isSelected ? selected.filter(x => x !== p) : [...selected, p]
                      onChange(stringifyStringListValue(next))
                    }}
                    className="flex cursor-pointer items-center gap-2 rounded-sm p-2 hover:bg-accent"
                  >
                    <div
                      className={cn(
                        'flex h-4 w-4 items-center justify-center rounded-sm border',
                        isSelected ? 'border-primary bg-primary' : 'border-muted',
                      )}
                    >
                      {isSelected && <X className="h-3 w-3 text-primary-foreground" />}
                    </div>
                    <span className="text-sm">{p}</span>
                  </div>
                )
              })}
            </div>
          </PopoverContent>
        </Popover>
      </FormControl>
    )
  }

  const mode = inferParityFieldMode(field)
  if (mode === 'stringList') {
    const pick = tagPickerSpec(key, mode, profileTagOptions)
    if (pick?.kind === 'multi') {
      return (
        <FormControl>
          <StringTagPicker
            mode="multi"
            options={pick.options}
            valueMulti={parseStringListValue(value)}
            onChangeMulti={next => onChange(stringifyStringListValue(next))}
            emptyHint={t('coreEditor.tagPicker.emptyMulti', { defaultValue: 'No inbound tags in this profile. Type below to add custom tags.' })}
            placeholder={t('coreEditor.tagPicker.addFromList', { defaultValue: 'Choose or add tags…' })}
            clearAllLabel={t('coreEditor.tagPicker.clearAll', { defaultValue: 'Clear all' })}
            addButtonLabel={t('coreEditor.tagPicker.addCustomTagShort', { defaultValue: 'Add tag' })}
            disabled={disabled}
            className={className}
          />
        </FormControl>
      )
    }
    return (
      <FormControl>
        <StringArrayPopoverInput
          value={parseStringListValue(value)}
          onChange={next => onChange(stringifyStringListValue(next))}
          placeholder={placeholder ?? t('coreEditor.stringArrayPopover.noValuesPlaceholder', { defaultValue: 'No values' })}
          addPlaceholder={t('arrayInput.addPlaceholder')}
          addButtonLabel={t('arrayInput.addButton')}
          itemsLabel={t('arrayInput.items')}
          emptyMessage={t('coreEditor.stringArrayPopover.emptyNoItems', { defaultValue: 'No items added.' })}
          duplicateErrorMessage={t('arrayInput.duplicateError')}
          clickToEditTitle={t('arrayInput.clickToEdit')}
          editItemTitle={t('arrayInput.editItem')}
          removeItemTitle={t('arrayInput.removeItem')}
          saveEditTitle={t('arrayInput.saveEdit')}
          cancelEditTitle={t('arrayInput.cancelEdit')}
          className={className}
          disabled={disabled}
        />
      </FormControl>
    )
  }

  if (isWebhookField(field)) {
    const parsed = parseJsonObject(value) ?? {}
    const url = typeof parsed.url === 'string' ? parsed.url : ''
    const deduplicationRaw = parsed.deduplication
    const deduplication =
      typeof deduplicationRaw === 'number' && Number.isFinite(deduplicationRaw)
        ? String(deduplicationRaw)
        : typeof deduplicationRaw === 'string'
          ? deduplicationRaw
          : ''
    const headersObj =
      parsed.headers && typeof parsed.headers === 'object' && !Array.isArray(parsed.headers)
        ? (parsed.headers as Record<string, unknown>)
        : null
    const headerEntries: Array<{ key: string; value: string }> = headersObj
      ? Object.entries(headersObj).map(([k, v]) => ({ key: String(k), value: v == null ? '' : String(v) }))
      : []

    const writeNext = (next: Record<string, unknown>) => {
      const cleaned: Record<string, unknown> = {}
      for (const [k, v] of Object.entries(next)) {
        if (v === undefined || v === null) continue
        if (typeof v === 'string' && v.trim() === '') continue
        if (typeof v === 'object' && !Array.isArray(v) && Object.keys(v as object).length === 0) continue
        cleaned[k] = v
      }
      if (Object.keys(cleaned).length === 0) {
        onChange('')
        return
      }
      onChange(stringifyJsonFormRecord(cleaned))
    }

    const setUrl = (next: string) => writeNext({ ...parsed, url: next })
    const setDeduplication = (next: string) => {
      const trimmed = next.trim()
      if (!trimmed) {
        const { deduplication: _drop, ...rest } = parsed
        void _drop
        writeNext(rest)
        return
      }
      const num = Number(trimmed)
      writeNext({ ...parsed, deduplication: Number.isFinite(num) && /^-?\d+(\.\d+)?$/.test(trimmed) ? num : trimmed })
    }
    const writeHeaders = (next: Array<{ key: string; value: string }>) => {
      const headers: Record<string, string> = {}
      for (const entry of next) {
        const k = entry.key.trim()
        if (!k) continue
        headers[k] = entry.value
      }
      const { headers: _drop, ...rest } = parsed
      void _drop
      if (Object.keys(headers).length === 0) {
        writeNext(rest)
        return
      }
      writeNext({ ...rest, headers })
    }
    const updateHeader = (index: number, patch: Partial<{ key: string; value: string }>) => {
      writeHeaders(headerEntries.map((entry, i) => (i === index ? { ...entry, ...patch } : entry)))
    }
    const removeHeader = (index: number) => {
      writeHeaders(headerEntries.filter((_, i) => i !== index))
    }
    const addHeader = () => {
      writeHeaders([...headerEntries, { key: `Header_${headerEntries.length + 1}`, value: '' }])
    }

    return (
      <FormControl>
        <div className={cn('flex flex-col gap-3 rounded-md border bg-muted/20 p-3', className)}>
          <div className="flex flex-col gap-1.5">
            <span className="text-xs font-medium">
              {t('coreEditor.routing.webhook.url', { defaultValue: 'URL' })}
            </span>
            <Input
              dir="ltr"
              className="h-9 min-w-0 text-xs"
              value={url}
              placeholder={t('coreEditor.routing.webhook.urlPlaceholder', {
                defaultValue: 'https://example.com/alert or /var/run/webhook.sock',
              })}
              onChange={e => setUrl(e.target.value)}
              disabled={disabled}
            />
            <span className="text-[11px] leading-snug text-muted-foreground">
              {t('coreEditor.routing.webhook.urlHint', {
                defaultValue: 'HTTP(S) URL or a Unix socket path. Use sock:/path for the root, sock:/path:/endpoint to target a specific endpoint.',
              })}
            </span>
          </div>

          <div className="flex flex-col gap-1.5">
            <span className="text-xs font-medium">
              {t('coreEditor.routing.webhook.deduplication', { defaultValue: 'Deduplication (seconds)' })}
            </span>
            <Input
              type="number"
              dir="ltr"
              inputMode="numeric"
              className="h-9 min-w-0 text-xs"
              value={deduplication}
              placeholder="0"
              onChange={e => setDeduplication(e.target.value)}
              disabled={disabled}
            />
            <span className="text-[11px] leading-snug text-muted-foreground">
              {t('coreEditor.routing.webhook.deduplicationHint', {
                defaultValue: 'Time window for ignoring duplicate events. Leave empty to disable.',
              })}
            </span>
          </div>

          <div className="flex flex-col gap-1.5">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium">
                {t('coreEditor.routing.webhook.headers', { defaultValue: 'Headers' })}
              </span>
              <Button type="button" variant="outline" size="icon" className="size-7" onClick={addHeader} disabled={disabled}>
                <Plus />
              </Button>
            </div>
            {headerEntries.length === 0 ? (
              <div className="rounded-md border border-dashed px-3 py-2 text-xs text-muted-foreground">
                {t('coreEditor.routing.webhook.headersEmpty', { defaultValue: 'No headers. Click + to add one.' })}
              </div>
            ) : (
              <div className="flex flex-col gap-2">
                {headerEntries.map((entry, index) => (
                  <div
                    key={`${entry.key}-${index}`}
                    className="flex w-full min-w-0 flex-wrap items-center gap-2 sm:flex-nowrap"
                  >
                    <Input
                      dir="ltr"
                      className="min-h-9 min-w-[7rem] flex-1 text-xs sm:min-w-[8rem]"
                      defaultValue={entry.key}
                      onBlur={e => {
                        if (e.target.value !== entry.key) updateHeader(index, { key: e.target.value })
                      }}
                      disabled={disabled}
                      placeholder={t('coreEditor.inbound.tcp.header.name', { defaultValue: 'Header name' })}
                    />
                    <Input
                      dir="ltr"
                      className="min-h-9 min-w-0 flex-[2] text-xs"
                      defaultValue={entry.value}
                      onBlur={e => {
                        if (e.target.value !== entry.value) updateHeader(index, { value: e.target.value })
                      }}
                      disabled={disabled}
                      placeholder={t('coreEditor.inbound.tcp.header.value', { defaultValue: 'Header value' })}
                    />
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      className="size-9 shrink-0 self-center border-red-500/20 transition-colors hover:border-red-500 hover:bg-red-50 dark:hover:bg-red-950/20"
                      onClick={() => removeHeader(index)}
                      disabled={disabled}
                    >
                      <Trash2 className="text-red-500" />
                    </Button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </FormControl>
    )
  }

  if (mode === 'json') {
    const objectValue = parseJsonObject(value)
    if (objectValue && Object.keys(objectValue).length > 0) {
      const entries = Object.entries(objectValue)
      const updateKey = (oldKey: string, newKeyRaw: string) => {
        const newKey = newKeyRaw.trim()
        if (!newKey || newKey === oldKey) return
        const next: Record<string, unknown> = {}
        for (const [k, v] of Object.entries(objectValue)) {
          next[k === oldKey ? newKey : k] = v
        }
        onChange(stringifyJsonFormRecord(next))
      }
      const updateValue = (entryKey: string, raw: string) => {
        const next: Record<string, unknown> = { ...objectValue }
        const trimmed = raw.trim()
        if (!trimmed) {
          delete next[entryKey]
          onChange(stringifyJsonFormRecord(next))
          return
        }
        if (trimmed.startsWith('{') || trimmed.startsWith('[') || trimmed.startsWith('"')) {
          try {
            next[entryKey] = JSON.parse(trimmed)
            onChange(stringifyJsonFormRecord(next))
            return
          } catch {
            // Keep as primitive text below.
          }
        }
        next[entryKey] = parsePrimitive(raw)
        onChange(stringifyJsonFormRecord(next))
      }
      const removeEntry = (entryKey: string) => {
        const next: Record<string, unknown> = { ...objectValue }
        delete next[entryKey]
        onChange(stringifyJsonFormRecord(next))
      }
      const addEntry = () => {
        const base = 'key'
        let i = 1
        let nextKey = `${base}_${i}`
        while (Object.prototype.hasOwnProperty.call(objectValue, nextKey)) {
          i += 1
          nextKey = `${base}_${i}`
        }
        onChange(stringifyJsonFormRecord({ ...objectValue, [nextKey]: '' }))
      }

      return (
        <FormControl>
          <div className={cn('flex flex-col gap-2', className)}>
            <div className="flex items-center justify-end">
              <Button type="button" variant="outline" size="icon" className="size-7" onClick={addEntry} disabled={disabled}>
                <Plus />
              </Button>
            </div>
            <div className="flex flex-col gap-2">
              {entries.length === 0 ? (
                <div className="rounded-md border border-dashed px-3 py-2 text-xs text-muted-foreground">
                  {t('coreEditor.parityUi.jsonMapEmpty', { defaultValue: 'No fields yet. Click + to add one.' })}
                </div>
              ) : (
                entries.map(([entryKey, entryValue]) => (
                  <div
                    key={entryKey}
                    className="flex w-full min-w-0 flex-wrap items-center gap-2 sm:flex-nowrap"
                  >
                    <Input
                      dir="ltr"
                      className="min-h-9 min-w-[7rem] flex-1 text-xs sm:min-w-[8rem]"
                      defaultValue={entryKey}
                      onBlur={e => {
                        if (e.target.value !== entryKey) updateKey(entryKey, e.target.value)
                      }}
                      disabled={disabled}
                      placeholder={t('coreEditor.parityUi.jsonMapKeyPlaceholder', { defaultValue: 'Key' })}
                    />
                    <Input
                      dir="ltr"
                      className="min-h-9 min-w-0 flex-[2] text-xs"
                      defaultValue={typeof entryValue === 'string' ? entryValue : JSON.stringify(entryValue)}
                      onBlur={e => {
                        const prev = typeof entryValue === 'string' ? entryValue : JSON.stringify(entryValue)
                        if (e.target.value !== prev) updateValue(entryKey, e.target.value)
                      }}
                      disabled={disabled}
                      placeholder={t('coreEditor.parityUi.jsonMapValuePlaceholder', { defaultValue: 'Value' })}
                    />
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      className="size-9 shrink-0 self-center border-red-500/20 transition-colors hover:border-red-500 hover:bg-red-50 dark:hover:bg-red-950/20"
                      onClick={() => removeEntry(entryKey)}
                      disabled={disabled}
                    >
                      <Trash2 className="text-red-500" />
                    </Button>
                  </div>
                ))
              )}
            </div>
          </div>
        </FormControl>
      )
    }

    return (
      <FormControl>
        <Textarea
          rows={8}
          className={cn('min-w-0 w-full text-xs', className)}
          dir="ltr"
          value={value}
          onChange={e => onChange(e.target.value)}
          disabled={disabled}
          spellCheck={false}
          placeholder={placeholder}
        />
      </FormControl>
    )
  }
  const pickScalar = tagPickerSpec(key, mode, profileTagOptions)
  if (pickScalar?.kind === 'single') {
    return (
      <FormControl>
        <StringTagPicker
          mode="single"
          options={pickScalar.options}
          valueSingle={value}
          onChangeSingle={onChange}
          placeholder={t('coreEditor.tagPicker.chooseTag', { defaultValue: 'Choose tag…' })}
          disabled={disabled}
          className={className}
        />
      </FormControl>
    )
  }
  return (
    <FormControl>
      <Input
        className={cn('h-10 w-full min-w-0 text-xs', className)}
        dir="ltr"
        value={value}
        onChange={e => onChange(e.target.value)}
        disabled={disabled}
        placeholder={placeholder}
      />
    </FormControl>
  )
}
