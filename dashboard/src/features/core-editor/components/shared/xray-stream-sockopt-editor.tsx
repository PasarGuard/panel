import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { cn } from '@/lib/utils'
import { Plus, SlidersHorizontal, Trash2 } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'

export type SockoptJson = Record<string, unknown>

const DOMAIN_STRATEGIES = ['AsIs', 'UseIP', 'UseIPv6v4', 'UseIPv6', 'UseIPv4v6', 'UseIPv4', 'ForceIP', 'ForceIPv6v4', 'ForceIPv6', 'ForceIPv4v6', 'ForceIPv4'] as const

const ADDRESS_PORT_STRATEGIES = ['none', 'SrvPortOnly', 'SrvAddressOnly', 'SrvPortAndAddress', 'TxtPortOnly', 'TxtAddressOnly', 'TxtPortAndAddress'] as const

const TPROXY_VALUES = ['off', 'redirect', 'tproxy'] as const

const CUSTOM_SOCKOPT_SYSTEMS = ['any', 'linux', 'windows', 'darwin'] as const
const CUSTOM_SOCKOPT_TYPES = ['int', 'str'] as const

function pruneHappyEyeballs(h: Record<string, unknown>): Record<string, unknown> | undefined {
  const out: Record<string, unknown> = {}
  if (typeof h.tryDelayMs === 'number' && Number.isFinite(h.tryDelayMs)) out.tryDelayMs = h.tryDelayMs
  if (typeof h.prioritizeIPv6 === 'boolean') out.prioritizeIPv6 = h.prioritizeIPv6
  if (typeof h.interleave === 'number' && Number.isFinite(h.interleave)) out.interleave = h.interleave
  if (typeof h.maxConcurrentTry === 'number' && Number.isFinite(h.maxConcurrentTry)) out.maxConcurrentTry = h.maxConcurrentTry
  return Object.keys(out).length > 0 ? out : undefined
}

/** Drop empty / unset sockopt keys before persisting. */
export function pruneSockoptObject(raw: SockoptJson | undefined): SockoptJson | undefined {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return undefined
  const out: SockoptJson = {}
  for (const [k, v] of Object.entries(raw)) {
    if (v === undefined || v === null) continue
    if (v === '') continue
    if (k === 'happyEyeballs' && typeof v === 'object' && v !== null && !Array.isArray(v)) {
      const pr = pruneHappyEyeballs(v as Record<string, unknown>)
      if (pr) out[k] = pr
      continue
    }
    if (k === 'customSockopt' && Array.isArray(v)) {
      if (v.length > 0) out[k] = v
      continue
    }
    if (typeof v === 'number' && !Number.isFinite(v)) continue
    out[k] = v
  }
  return Object.keys(out).length > 0 ? out : undefined
}

function numOrUndef(raw: string): number | undefined {
  const t = raw.trim()
  if (t === '') return undefined
  const n = Number(t)
  return Number.isFinite(n) ? n : undefined
}

function stringValue(v: unknown): string {
  return typeof v === 'string' ? v : ''
}

function numberValue(v: unknown): string {
  return typeof v === 'number' && Number.isFinite(v) ? String(v) : ''
}

function tcpFastOpenSelectValue(v: unknown): 'default' | 'false' | 'true' | 'number' {
  if (v === undefined) return 'default'
  if (v === false) return 'false'
  if (v === true) return 'true'
  if (typeof v === 'number' && Number.isFinite(v)) return 'number'
  return 'default'
}

export interface XrayStreamSockoptFieldsProps {
  variant: 'inbound' | 'outbound'
  /** Current `streamSettings.sockopt` (outbound) or `streamAdvanced.sockopt` (inbound). */
  value: SockoptJson | undefined
  onChange: (next: SockoptJson | undefined) => void
  t: (key: string, opts?: Record<string, unknown>) => string
  /** Outbound tags for `dialerProxy` (excluding current outbound tag when applicable). */
  dialerProxyTags?: readonly string[]
  /** When false, only the enable row is shown until the user turns options on. */
  showEnableRow?: boolean
  /** Optional class on the outer wrapper (plain layout). */
  className?: string
}

/**
 * Form controls for Xray `SockoptObject` (`streamSettings.sockopt` / inbound `streamAdvanced.sockopt`).
 */
export function XrayStreamSockoptFields({ variant, value, onChange, t, dialerProxyTags = [], showEnableRow = true, className }: XrayStreamSockoptFieldsProps) {
  const cur = useMemo(() => ({ ...(value ?? {}) }) as SockoptJson, [value])
  const [tfoNumber, setTfoNumber] = useState(() => (typeof value?.tcpFastOpen === 'number' && Number.isFinite(value.tcpFastOpen) ? String(value.tcpFastOpen) : ''))

  useEffect(() => {
    if (typeof value?.tcpFastOpen === 'number' && Number.isFinite(value.tcpFastOpen)) {
      setTfoNumber(String(value.tcpFastOpen))
    } else if (value?.tcpFastOpen !== true && value?.tcpFastOpen !== false) {
      setTfoNumber('')
    }
  }, [value?.tcpFastOpen])

  const patch = useCallback(
    (partial: SockoptJson) => {
      const next = { ...(value ?? {}), ...partial } as SockoptJson
      for (const k of Object.keys(partial)) {
        if (partial[k] === undefined) delete next[k]
      }
      onChange(pruneSockoptObject(next))
    },
    [value, onChange],
  )

  const sockoptConfigured = pruneSockoptObject(value) != null

  const domainStrategy = typeof cur.domainStrategy === 'string' && (DOMAIN_STRATEGIES as readonly string[]).includes(cur.domainStrategy) ? cur.domainStrategy : 'AsIs'
  const tproxy = typeof cur.tproxy === 'string' && (TPROXY_VALUES as readonly string[]).includes(cur.tproxy) ? cur.tproxy : 'off'
  const addrPort = typeof cur.addressPortStrategy === 'string' && (ADDRESS_PORT_STRATEGIES as readonly string[]).includes(cur.addressPortStrategy) ? cur.addressPortStrategy : 'none'
  const hb = (cur.happyEyeballs && typeof cur.happyEyeballs === 'object' && !Array.isArray(cur.happyEyeballs) ? (cur.happyEyeballs as Record<string, unknown>) : {}) as Record<string, unknown>
  const happyEnabled = pruneHappyEyeballs(hb) != null
  const customSockoptRows = Array.isArray(cur.customSockopt)
    ? cur.customSockopt.filter((item): item is Record<string, unknown> => item != null && typeof item === 'object' && !Array.isArray(item))
    : []

  const patchCustomSockopt = (rows: Record<string, unknown>[]) => {
    const cleaned = rows
      .map(row => {
        const next: Record<string, unknown> = {}
        const system = typeof row.system === 'string' && row.system !== 'any' ? row.system.trim() : ''
        const type = typeof row.type === 'string' ? row.type.trim() : ''
        const level = row.level != null ? String(row.level).trim() : ''
        const opt = row.opt != null ? String(row.opt).trim() : ''
        const val = row.value != null ? String(row.value).trim() : ''
        if (system) next.system = system
        if (type) next.type = type
        if (level) next.level = level
        if (opt) next.opt = opt
        if (val) next.value = val
        return next
      })
      .filter(row => Object.keys(row).length > 0)
    patch({ customSockopt: cleaned.length > 0 ? cleaned : undefined })
  }

  return (
    <div className={cn('flex flex-col gap-4', className)}>
      {showEnableRow ? (
        <div className="flex items-center justify-between rounded-lg border px-3 py-2.5">
          <div>
            <p className="text-sm font-medium">{t('coreEditor.sockopt.enable')}</p>
          </div>
          <Switch
            checked={sockoptConfigured}
            onCheckedChange={checked => {
              if (checked) onChange({ domainStrategy: 'AsIs' })
              else {
                setTfoNumber('')
                onChange(undefined)
              }
            }}
          />
        </div>
      ) : null}

      {sockoptConfigured ? (
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="flex flex-col gap-2">
            <Label>{t('coreEditor.sockopt.domainStrategy')}</Label>
            <Select dir="ltr" value={domainStrategy} onValueChange={v => patch({ domainStrategy: v })}>
              <SelectTrigger className="h-10 w-full min-w-0" dir="ltr">
                <SelectValue />
              </SelectTrigger>
              <SelectContent dir="ltr" className="max-h-72">
                {DOMAIN_STRATEGIES.map(ds => (
                  <SelectItem key={ds} value={ds}>
                    {ds}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="flex flex-col gap-2">
            <Label>{t('coreEditor.sockopt.tproxy')}</Label>
            <Select dir="ltr" value={tproxy} onValueChange={v => patch({ tproxy: v })}>
              <SelectTrigger className="h-10 w-full min-w-0" dir="ltr">
                <SelectValue />
              </SelectTrigger>
              <SelectContent dir="ltr">
                {TPROXY_VALUES.map(x => (
                  <SelectItem key={x} value={x}>
                    {x}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="flex flex-col gap-2">
            <Label>{t('coreEditor.sockopt.addressPortStrategy')}</Label>
            <Select dir="ltr" value={addrPort} onValueChange={v => patch({ addressPortStrategy: v })}>
              <SelectTrigger className="h-10 w-full min-w-0" dir="ltr">
                <SelectValue />
              </SelectTrigger>
              <SelectContent dir="ltr">
                {ADDRESS_PORT_STRATEGIES.map(x => (
                  <SelectItem key={x} value={x}>
                    {x}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {variant === 'inbound' ? (
            <div className="flex items-center justify-between rounded-lg border px-3 py-2.5 sm:col-span-2">
              <div>
                <p className="text-sm font-medium">{t('coreEditor.sockopt.acceptProxyProtocol')}</p>
              </div>
              <Switch checked={cur.acceptProxyProtocol === true} onCheckedChange={checked => patch({ acceptProxyProtocol: checked ? true : undefined })} />
            </div>
          ) : null}

          {variant === 'outbound' ? (
            <div className="flex flex-col gap-2 sm:col-span-2">
              <Label>{t('coreEditor.sockopt.dialerProxy')}</Label>
              {dialerProxyTags.length > 0 ? (
                <Select
                  dir="ltr"
                  value={typeof cur.dialerProxy === 'string' && cur.dialerProxy ? cur.dialerProxy : '__none'}
                  onValueChange={v => patch({ dialerProxy: v === '__none' ? undefined : v })}
                >
                  <SelectTrigger className="h-10 w-full min-w-0" dir="ltr">
                    <SelectValue placeholder={t('coreEditor.sockopt.dialerProxyPlaceholder')} />
                  </SelectTrigger>
                  <SelectContent dir="ltr">
                    <SelectItem value="__none">{t('coreEditor.sockopt.dialerProxyNone')}</SelectItem>
                    {dialerProxyTags.map(tag => (
                      <SelectItem key={tag} value={tag}>
                        {tag}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              ) : (
                <Input
                  dir="ltr"
                  className="h-10 font-mono text-xs"
                  placeholder={t('coreEditor.sockopt.dialerProxyPlaceholder')}
                  value={stringValue(cur.dialerProxy)}
                  onChange={e => {
                    const v = e.target.value.trim()
                    patch({ dialerProxy: v === '' ? undefined : v })
                  }}
                />
              )}
            </div>
          ) : null}

          <div className="flex flex-col gap-2">
            <Label>{t('coreEditor.sockopt.mark')}</Label>
            <Input
              dir="ltr"
              className="h-10 font-mono text-xs"
              inputMode="numeric"
              placeholder="0"
              value={numberValue(cur.mark)}
              onChange={e => {
                const n = numOrUndef(e.target.value)
                patch({ mark: n === undefined || n === 0 ? undefined : Math.trunc(n) })
              }}
            />
          </div>

          <div className="flex flex-col gap-2">
            <Label>{t('coreEditor.sockopt.interface')}</Label>
            <Input
              dir="ltr"
              className="h-10 font-mono text-xs"
              placeholder="wg0"
              value={stringValue(cur.interface)}
              onChange={e => {
                const v = e.target.value.trim()
                patch({ interface: v === '' ? undefined : v })
              }}
            />
          </div>

          <div className="flex flex-col gap-2">
            <Label>{t('coreEditor.sockopt.tcpFastOpen')}</Label>
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
              <Select
                dir="ltr"
                value={tcpFastOpenSelectValue(cur.tcpFastOpen)}
                onValueChange={mode => {
                  if (mode === 'default') {
                    setTfoNumber('')
                    patch({ tcpFastOpen: undefined })
                  } else if (mode === 'false') {
                    setTfoNumber('')
                    patch({ tcpFastOpen: false })
                  } else if (mode === 'true') {
                    setTfoNumber('')
                    patch({ tcpFastOpen: true })
                  } else {
                    patch({ tcpFastOpen: numOrUndef(tfoNumber) ?? 0 })
                  }
                }}
              >
                <SelectTrigger className="h-10 w-full min-w-0 sm:max-w-xs" dir="ltr">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent dir="ltr">
                  <SelectItem value="default">{t('coreEditor.sockopt.tcpFastOpenDefault')}</SelectItem>
                  <SelectItem value="false">{t('coreEditor.sockopt.tcpFastOpenOff')}</SelectItem>
                  <SelectItem value="true">{t('coreEditor.sockopt.tcpFastOpenOn')}</SelectItem>
                  <SelectItem value="number">{t('coreEditor.sockopt.tcpFastOpenNumber')}</SelectItem>
                </SelectContent>
              </Select>
              {tcpFastOpenSelectValue(cur.tcpFastOpen) === 'number' ? (
                <Input
                  dir="ltr"
                  className="h-10 font-mono text-xs sm:max-w-[10rem]"
                  inputMode="numeric"
                  placeholder="256"
                  value={tfoNumber}
                  onChange={e => {
                    const raw = e.target.value
                    setTfoNumber(raw)
                    patch({ tcpFastOpen: numOrUndef(raw) ?? 0 })
                  }}
                />
              ) : null}
            </div>
          </div>

          <div className="flex flex-col gap-2">
            <Label>{t('coreEditor.sockopt.tcpCongestion')}</Label>
            <Input
              dir="ltr"
              className="h-10 font-mono text-xs"
              placeholder="bbr"
              value={stringValue(cur.tcpcongestion ?? cur.tcpCongestion)}
              onChange={e => {
                const v = e.target.value.trim()
                patch({ tcpcongestion: v === '' ? undefined : v, tcpCongestion: undefined })
              }}
            />
          </div>

          <div className="flex flex-col gap-2">
            <Label>{t('coreEditor.sockopt.tcpMaxSeg')}</Label>
            <Input
              dir="ltr"
              className="h-10 font-mono text-xs"
              inputMode="numeric"
              placeholder="1440"
              value={numberValue(cur.tcpMaxSeg)}
              onChange={e => patch({ tcpMaxSeg: numOrUndef(e.target.value) })}
            />
          </div>

          <div className="flex flex-col gap-2">
            <Label>{t('coreEditor.sockopt.tcpUserTimeout')}</Label>
            <Input
              dir="ltr"
              className="h-10 font-mono text-xs"
              inputMode="numeric"
              placeholder="10000"
              value={numberValue(cur.tcpUserTimeout)}
              onChange={e => patch({ tcpUserTimeout: numOrUndef(e.target.value) })}
            />
          </div>

          <div className="flex flex-col gap-2">
            <Label>{t('coreEditor.sockopt.tcpKeepAliveIdle')}</Label>
            <Input
              dir="ltr"
              className="h-10 font-mono text-xs"
              inputMode="numeric"
              placeholder="300"
              value={numberValue(cur.tcpKeepAliveIdle)}
              onChange={e => patch({ tcpKeepAliveIdle: numOrUndef(e.target.value) })}
            />
          </div>

          <div className="flex flex-col gap-2">
            <Label>{t('coreEditor.sockopt.tcpKeepAliveInterval')}</Label>
            <Input
              dir="ltr"
              className="h-10 font-mono text-xs"
              inputMode="numeric"
              placeholder="45"
              value={numberValue(cur.tcpKeepAliveInterval)}
              onChange={e => patch({ tcpKeepAliveInterval: numOrUndef(e.target.value) })}
            />
          </div>

          <div className="flex flex-col gap-2">
            <Label>{t('coreEditor.sockopt.tcpWindowClamp')}</Label>
            <Input
              dir="ltr"
              className="h-10 font-mono text-xs"
              inputMode="numeric"
              placeholder="600"
              value={numberValue(cur.tcpWindowClamp)}
              onChange={e => patch({ tcpWindowClamp: numOrUndef(e.target.value) })}
            />
          </div>

          <div className="flex flex-col gap-2 sm:col-span-2">
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="flex items-center justify-between rounded-lg border px-3 py-2.5">
                <p className="text-sm font-medium">{t('coreEditor.sockopt.tcpMptcp')}</p>
                <Switch checked={cur.tcpMptcp === true} onCheckedChange={checked => patch({ tcpMptcp: checked ? true : undefined })} />
              </div>
              <div className="flex items-center justify-between rounded-lg border px-3 py-2.5">
                <p className="text-sm font-medium">{t('coreEditor.sockopt.v6only')}</p>
                <Switch checked={(cur.V6Only ?? cur.v6only) === true} onCheckedChange={checked => patch({ V6Only: checked ? true : undefined, v6only: undefined })} />
              </div>
            </div>
          </div>

          <div className="space-y-3 rounded-md border p-3 sm:col-span-2">
            <div className="flex items-center justify-between gap-3">
              <Label>{t('coreEditor.sockopt.happyEyeballs')}</Label>
              <Switch
                checked={happyEnabled}
                onCheckedChange={checked => {
                  if (!checked) patch({ happyEyeballs: undefined })
                  else patch({ happyEyeballs: { tryDelayMs: 250, prioritizeIPv6: false, interleave: 1, maxConcurrentTry: 4 } })
                }}
              />
            </div>
            {happyEnabled ? (
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="flex flex-col gap-2">
                  <Label>{t('coreEditor.sockopt.hbTryDelayMs')}</Label>
                  <Input
                    dir="ltr"
                    className="h-9 font-mono text-xs"
                    inputMode="numeric"
                    placeholder="250"
                    value={numberValue(hb.tryDelayMs) || '250'}
                    onChange={e => patch({ happyEyeballs: { ...hb, tryDelayMs: numOrUndef(e.target.value) ?? 250 } })}
                  />
                </div>
                <div className="flex flex-col gap-2">
                  <Label>{t('coreEditor.sockopt.hbInterleave')}</Label>
                  <Input
                    dir="ltr"
                    className="h-9 font-mono text-xs"
                    inputMode="numeric"
                    placeholder="1"
                    value={numberValue(hb.interleave) || '1'}
                    onChange={e => patch({ happyEyeballs: { ...hb, interleave: numOrUndef(e.target.value) ?? 1 } })}
                  />
                </div>
                <div className="flex flex-col gap-2">
                  <Label>{t('coreEditor.sockopt.hbMaxConcurrentTry')}</Label>
                  <Input
                    dir="ltr"
                    className="h-9 font-mono text-xs"
                    inputMode="numeric"
                    placeholder="4"
                    value={numberValue(hb.maxConcurrentTry) || '4'}
                    onChange={e => patch({ happyEyeballs: { ...hb, maxConcurrentTry: numOrUndef(e.target.value) ?? 4 } })}
                  />
                </div>
                <div className="flex items-center justify-between rounded-md border px-3 py-2">
                  <span className="text-xs font-medium">{t('coreEditor.sockopt.hbPrioritizeIPv6')}</span>
                  <Switch checked={hb.prioritizeIPv6 === true} onCheckedChange={checked => patch({ happyEyeballs: { ...hb, prioritizeIPv6: checked } })} />
                </div>
              </div>
            ) : null}
          </div>

          <div className="space-y-3 rounded-md border p-3 sm:col-span-2">
            <div className="flex items-center justify-between gap-3">
              <Label>{t('coreEditor.sockopt.customSockopt')}</Label>
              <Button type="button" size="sm" variant="secondary" className="h-8 gap-1.5" onClick={() => patchCustomSockopt([...customSockoptRows, { system: 'any', type: 'int', level: '6', opt: '', value: '' }])}>
                <Plus className="h-3.5 w-3.5" />
                {t('coreEditor.sockopt.addCustomSockopt')}
              </Button>
            </div>
            {customSockoptRows.length > 0 ? (
              <div className="flex flex-col gap-3">
                {customSockoptRows.map((row, index) => {
                  const systemValue = typeof row.system === 'string' && (CUSTOM_SOCKOPT_SYSTEMS as readonly string[]).includes(row.system) ? row.system : 'any'
                  const typeValue = typeof row.type === 'string' && (CUSTOM_SOCKOPT_TYPES as readonly string[]).includes(row.type) ? row.type : 'int'
                  const updateRow = (patchRow: Record<string, unknown>) => patchCustomSockopt(customSockoptRows.map((r, i) => (i === index ? { ...r, ...patchRow } : r)))
                  return (
                    <div key={index} className="grid gap-2 rounded-md border border-dashed p-2 sm:grid-cols-[1fr_1fr_1fr_1fr_1fr_auto]">
                      <Select dir="ltr" value={systemValue} onValueChange={v => updateRow({ system: v })}>
                        <SelectTrigger className="h-9 min-w-0" dir="ltr">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent dir="ltr">
                          {CUSTOM_SOCKOPT_SYSTEMS.map(system => (
                            <SelectItem key={system} value={system}>
                              {system}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <Select dir="ltr" value={typeValue} onValueChange={v => updateRow({ type: v })}>
                        <SelectTrigger className="h-9 min-w-0" dir="ltr">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent dir="ltr">
                          {CUSTOM_SOCKOPT_TYPES.map(type => (
                            <SelectItem key={type} value={type}>
                              {type}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <Input dir="ltr" className="h-9 font-mono text-xs" placeholder="6" value={row.level != null ? String(row.level) : ''} onChange={e => updateRow({ level: e.target.value.trim() || undefined })} />
                      <Input dir="ltr" className="h-9 font-mono text-xs" placeholder="13" value={row.opt != null ? String(row.opt) : ''} onChange={e => updateRow({ opt: e.target.value.trim() || undefined })} />
                      <Input dir="ltr" className="h-9 font-mono text-xs" placeholder="bbr" value={row.value != null ? String(row.value) : ''} onChange={e => updateRow({ value: e.target.value.trim() || undefined })} />
                      <Button type="button" variant="ghost" size="icon" className="h-9 w-9 text-muted-foreground hover:text-destructive" onClick={() => patchCustomSockopt(customSockoptRows.filter((_, i) => i !== index))}>
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  )
                })}
              </div>
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  )
}

export interface XrayStreamSockoptInboundAccordionProps {
  accordionItemClassName: string
  value: SockoptJson | undefined
  onChange: (next: SockoptJson | undefined) => void
  t: (key: string, opts?: Record<string, unknown>) => string
  dialerProxyTags?: readonly string[]
}

export function XrayStreamSockoptInboundAccordion({ accordionItemClassName, value, onChange, t }: XrayStreamSockoptInboundAccordionProps) {
  return (
    <Accordion type="single" collapsible className="mt-0! sm:col-span-2">
      <AccordionItem value="sockopt" className={accordionItemClassName}>
        <AccordionTrigger>
          <div className="flex items-center gap-2">
            <SlidersHorizontal className="text-muted-foreground h-3.5 w-3.5 shrink-0" aria-hidden />
            <span>{t('coreEditor.sockopt.section')}</span>
          </div>
        </AccordionTrigger>
        <AccordionContent className="pt-0 pb-3">
          <XrayStreamSockoptFields variant="inbound" value={value} onChange={onChange} t={t} />
        </AccordionContent>
      </AccordionItem>
    </Accordion>
  )
}
