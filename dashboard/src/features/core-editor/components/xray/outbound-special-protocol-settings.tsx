import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Separator } from '@/components/ui/separator'
import { Textarea } from '@/components/ui/textarea'
import { normalizeSettingsFromEditor } from '@/features/core-editor/kit/outbound-editor-json'
import { useCoreEditorStore } from '@/features/core-editor/state/core-editor-store'
import type { Outbound } from '@pasarguard/xray-config-kit'
import type { TFunction } from 'i18next'
import { Globe2, ListOrdered, Plus, Radio, Scissors, Trash2 } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'

type PatchOutbound = (next: Outbound) => void

/** Same item chrome as `OutboundStreamSettingsAccordion` / mux in `xray-outbounds-section`. */
const OUTBOUND_SUBACCORDION_ITEM_CLASS =
  'rounded-sm border px-4 [&_[data-state=closed]]:no-underline [&_[data-state=open]]:no-underline'

function readSettings(ob: Outbound): Record<string, unknown> {
  return ((ob as { settings?: Record<string, unknown> }).settings ?? {}) as Record<string, unknown>
}

function commitSettings(ob: Outbound, nextSettings: Record<string, unknown>, patchOutbound: PatchOutbound) {
  const normalized = normalizeSettingsFromEditor(ob.protocol, nextSettings)
  patchOutbound({ ...(ob as object), settings: normalized } as Outbound)
}

const FREEDOM_DOMAIN_STRATEGIES = [
  'AsIs',
  'UseIP',
  'UseIPv6v4',
  'UseIPv6',
  'UseIPv4v6',
  'UseIPv4',
  'ForceIP',
  'ForceIPv6v4',
  'ForceIPv6',
  'ForceIPv4v6',
  'ForceIPv4',
] as const

type NoiseRow = { type: string; packet: string; delay: string }
type FinalRuleRow = { action: 'allow' | 'block'; network: string; port: string; ipText: string; blockDelay: string }

function parseNoiseRows(settings: Record<string, unknown>): NoiseRow[] {
  const raw = settings.noises
  if (!Array.isArray(raw) || raw.length === 0) return []
  return raw.map((item): NoiseRow => {
    if (!item || typeof item !== 'object' || Array.isArray(item)) return { type: 'rand', packet: '', delay: '' }
    const o = item as Record<string, unknown>
    return {
      type: typeof o.type === 'string' ? o.type : 'rand',
      packet: o.packet != null ? String(o.packet) : '',
      delay: o.delay != null ? String(o.delay) : '',
    }
  })
}

function parseFinalRuleRows(settings: Record<string, unknown>): FinalRuleRow[] {
  const raw = settings.finalRules
  if (!Array.isArray(raw) || raw.length === 0) return []
  return raw.map((item): FinalRuleRow => {
    if (!item || typeof item !== 'object' || Array.isArray(item)) {
      return { action: 'block', network: '', port: '', ipText: '', blockDelay: '' }
    }
    const o = item as Record<string, unknown>
    const ip = o.ip
    let ipText = ''
    if (Array.isArray(ip)) ipText = ip.map(x => String(x)).join('\n')
    return {
      action: o.action === 'allow' ? 'allow' : 'block',
      network: typeof o.network === 'string' ? o.network : Array.isArray(o.network) ? o.network.join(',') : '',
      port: o.port != null ? String(o.port) : '',
      ipText,
      blockDelay: o.blockDelay != null ? String(o.blockDelay) : '',
    }
  })
}

function buildIpArray(ipText: string): string[] | undefined {
  const lines = ipText
    .split(/[\n,]+/)
    .map(s => s.trim())
    .filter(Boolean)
  return lines.length > 0 ? lines : undefined
}

function pruneFreedomSettings(s: Record<string, unknown>): Record<string, unknown> {
  const out = { ...s }

  const frag = out.fragment
  if (frag && typeof frag === 'object' && !Array.isArray(frag)) {
    const f = frag as Record<string, unknown>
    const packets = String(f.packets ?? '').trim()
    const length = String(f.length ?? '').trim()
    const interval = String(f.interval ?? '').trim()
    if (!packets && !length && !interval) delete out.fragment
    else {
      const nf: Record<string, unknown> = {}
      if (packets) nf.packets = packets
      if (length) nf.length = length
      if (interval) nf.interval = interval
      out.fragment = nf
    }
  }

  if (Array.isArray(out.noises) && out.noises.length === 0) delete out.noises

  if (Array.isArray(out.finalRules)) {
    const cleaned = (out.finalRules as unknown[]).filter(
      r => r && typeof r === 'object' && !Array.isArray(r) && Object.keys(r as object).length > 0,
    )
    if (cleaned.length === 0) delete out.finalRules
    else out.finalRules = cleaned
  }

  if (out.redirect !== undefined && String(out.redirect).trim() === '') delete out.redirect

  if (out.userLevel === '' || out.userLevel === undefined || out.userLevel === null) delete out.userLevel
  else if (typeof out.userLevel === 'string' && out.userLevel.trim() === '') delete out.userLevel

  if (out.proxyProtocol === 0 || out.proxyProtocol === '0') delete out.proxyProtocol

  // Keep explicit `domainStrategy` (including `AsIs`); only drop empty / unset values.
  if (out.domainStrategy === '' || out.domainStrategy === undefined || out.domainStrategy === null) {
    delete out.domainStrategy
  }

  return out
}

function OutboundFreedomSettings({ ob, patchOutbound, t }: { ob: Outbound; patchOutbound: PatchOutbound; t: TFunction }) {
  const s = readSettings(ob)
  const domainStrategy = (typeof s.domainStrategy === 'string' && s.domainStrategy ? s.domainStrategy : 'AsIs') as (typeof FREEDOM_DOMAIN_STRATEGIES)[number]
  const redirect = typeof s.redirect === 'string' ? s.redirect : ''
  const userLevel = s.userLevel !== undefined && s.userLevel !== null ? String(s.userLevel) : ''
  const proxyProtocol = s.proxyProtocol === 1 || s.proxyProtocol === 2 ? String(s.proxyProtocol) : '0'

  const frag = (s.fragment && typeof s.fragment === 'object' && !Array.isArray(s.fragment) ? s.fragment : {}) as Record<string, unknown>
  const fragPackets = String(frag.packets ?? '')
  const fragLength = String(frag.length ?? '')
  const fragInterval = String(frag.interval ?? '')

  const [noiseRows, setNoiseRows] = useState<NoiseRow[]>(() => parseNoiseRows(s))
  const [ruleRows, setRuleRows] = useState<FinalRuleRow[]>(() => parseFinalRuleRows(s))

  useEffect(() => {
    setNoiseRows(parseNoiseRows(readSettings(ob)))
    setRuleRows(parseFinalRuleRows(readSettings(ob)))
  }, [ob])

  const commitFreedom = (next: Record<string, unknown>) => {
    commitSettings(ob, pruneFreedomSettings(next), patchOutbound)
  }

  const syncNoisesAndRules = (nr: NoiseRow[], rr: FinalRuleRow[]) => {
    const base = readSettings(ob)
    const noises = nr
      .map(row => {
        const type = row.type.trim() || 'rand'
        const packet = row.packet.trim()
        const delay = row.delay.trim()
        if (!packet && !delay) return null
        const o: Record<string, unknown> = { type }
        if (packet) o.packet = packet
        if (delay) o.delay = delay
        return o
      })
      .filter(Boolean) as Record<string, unknown>[]

    const finalRules = rr
      .map(row => {
        const o: Record<string, unknown> = { action: row.action }
        const net = row.network.trim()
        if (net) o.network = net.includes(',') ? net.split(',').map(x => x.trim()).filter(Boolean) : net
        if (row.port.trim()) o.port = row.port.trim()
        const ips = buildIpArray(row.ipText)
        if (ips) o.ip = ips
        if (row.blockDelay.trim()) o.blockDelay = row.blockDelay.trim()
        return o
      })
      .filter(o => {
        if (o.action === 'allow') return true
        return !!(o.network || o.port || (Array.isArray(o.ip) && o.ip.length > 0) || o.blockDelay)
      })

    const next = { ...base }
    if (noises.length > 0) next.noises = noises
    else delete next.noises
    if (finalRules.length > 0) next.finalRules = finalRules
    else delete next.finalRules
    commitFreedom(next)
  }

  return (
    <div className="flex flex-col gap-4">
      <p className="text-xs text-muted-foreground">
        {t('coreEditor.outbound.freedom.blurb', {
          defaultValue:
            'Freedom forwards traffic as-is. Fragment, noises, and final rules are optional; use JSON tab for edge cases.',
        })}
      </p>

      <div className="grid w-full gap-4 sm:grid-cols-2">
        <div className="flex min-w-0 w-full flex-col gap-2">
          <Label className="text-xs font-medium">{t('coreEditor.outbound.freedom.domainStrategy', { defaultValue: 'Domain strategy' })}</Label>
          <Select
            dir="ltr"
            value={domainStrategy}
            onValueChange={v => {
              const cur = readSettings(ob)
              const next = { ...cur }
              next.domainStrategy = v
              commitFreedom(next)
            }}
          >
            <SelectTrigger className="h-10 w-full min-w-0" dir="ltr">
              <SelectValue />
            </SelectTrigger>
            <SelectContent dir="ltr">
              {FREEDOM_DOMAIN_STRATEGIES.map(ds => (
                <SelectItem key={ds} value={ds}>
                  {ds}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="flex min-w-0 w-full flex-col gap-2">
          <Label className="text-xs font-medium">{t('coreEditor.outbound.freedom.proxyProtocol', { defaultValue: 'PROXY protocol' })}</Label>
          <Select
            dir="ltr"
            value={proxyProtocol}
            onValueChange={v => {
              const cur = readSettings(ob)
              const next = { ...cur }
              if (v === '0') delete next.proxyProtocol
              else next.proxyProtocol = Number(v)
              commitFreedom(next)
            }}
          >
            <SelectTrigger className="h-10 w-full min-w-0" dir="ltr">
              <SelectValue />
            </SelectTrigger>
            <SelectContent dir="ltr">
              <SelectItem value="0">{t('coreEditor.outbound.freedom.proxyProtocolOff', { defaultValue: 'Off (0)' })}</SelectItem>
              <SelectItem value="1">v1</SelectItem>
              <SelectItem value="2">v2</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="flex min-w-0 w-full flex-col gap-2 sm:col-span-2">
          <Label className="text-xs font-medium">{t('coreEditor.outbound.freedom.redirect', { defaultValue: 'Redirect' })}</Label>
          <Input
            dir="ltr"
            className="h-10 w-full min-w-0 text-xs"
            placeholder="127.0.0.1:3366 or :443"
            value={redirect}
            onChange={e => {
              const v = e.target.value
              const cur = readSettings(ob)
              const next = { ...cur }
              if (!v.trim()) delete next.redirect
              else next.redirect = v
              commitFreedom(next)
            }}
          />
        </div>

        <div className="flex min-w-0 w-full flex-col gap-2 sm:col-span-2">
          <Label className="text-xs font-medium">{t('coreEditor.outbound.freedom.userLevel', { defaultValue: 'User level' })}</Label>
          <Input
            type="number"
            dir="ltr"
            className="h-10 w-full min-w-0"
            placeholder="0"
            value={userLevel}
            onChange={e => {
              const v = e.target.value
              const cur = readSettings(ob)
              const next = { ...cur }
              if (v === '') delete next.userLevel
              else {
                const n = Number(v)
                next.userLevel = Number.isFinite(n) ? n : v
              }
              commitFreedom(next)
            }}
          />
        </div>
      </div>

      <Accordion type="multiple" className="!mt-0 flex w-full flex-col gap-y-3">
        <AccordionItem value="fragment" className={OUTBOUND_SUBACCORDION_ITEM_CLASS}>
          <AccordionTrigger>
            <div className="flex flex-wrap items-center gap-2">
              <Scissors className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
              <span>{t('coreEditor.outbound.freedom.fragmentTitle', { defaultValue: 'TCP fragment' })}</span>
            </div>
          </AccordionTrigger>
          <AccordionContent className="space-y-3 px-2 pb-4">
            <div className="grid gap-3 sm:grid-cols-3">
              <div className="flex flex-col gap-1.5">
                <Label className="text-xs text-muted-foreground">{t('coreEditor.outbound.freedom.fragmentPackets', { defaultValue: 'Packets' })}</Label>
                <Input
                  dir="ltr"
                  className="h-9 text-xs"
                  placeholder="tlshello"
                  value={fragPackets}
                  onChange={e => {
                    const v = e.target.value
                    const cur = readSettings(ob)
                    const next = { ...cur }
                    const f = {
                      ...(typeof next.fragment === 'object' && next.fragment && !Array.isArray(next.fragment)
                        ? (next.fragment as object)
                        : {}),
                    } as Record<string, unknown>
                    if (!v.trim() && !String(f.length ?? '').trim() && !String(f.interval ?? '').trim()) delete next.fragment
                    else {
                      f.packets = v || undefined
                      next.fragment = f
                    }
                    commitFreedom(next)
                  }}
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label className="text-xs text-muted-foreground">{t('coreEditor.outbound.freedom.fragmentLength', { defaultValue: 'Length (bytes)' })}</Label>
                <Input
                  dir="ltr"
                  className="h-9 text-xs"
                  placeholder="100-200"
                  value={fragLength}
                  onChange={e => {
                    const v = e.target.value
                    const cur = readSettings(ob)
                    const next = { ...cur }
                    const prev = (typeof next.fragment === 'object' && next.fragment && !Array.isArray(next.fragment) ? next.fragment : {}) as Record<string, unknown>
                    const f = { ...prev, length: v || undefined } as Record<string, unknown>
                    if (!String(f.packets ?? '').trim() && !v.trim() && !String(f.interval ?? '').trim()) delete next.fragment
                    else next.fragment = f
                    commitFreedom(next)
                  }}
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label className="text-xs text-muted-foreground">{t('coreEditor.outbound.freedom.fragmentInterval', { defaultValue: 'Interval (ms)' })}</Label>
                <Input
                  dir="ltr"
                  className="h-9 text-xs"
                  placeholder="10-20"
                  value={fragInterval}
                  onChange={e => {
                    const v = e.target.value
                    const cur = readSettings(ob)
                    const next = { ...cur }
                    const prev = (typeof next.fragment === 'object' && next.fragment && !Array.isArray(next.fragment) ? next.fragment : {}) as Record<string, unknown>
                    const f = { ...prev, interval: v || undefined } as Record<string, unknown>
                    if (!String(f.packets ?? '').trim() && !String(f.length ?? '').trim() && !v.trim()) delete next.fragment
                    else next.fragment = f
                    commitFreedom(next)
                  }}
                />
              </div>
            </div>
          </AccordionContent>
        </AccordionItem>

        <AccordionItem value="noises" className={OUTBOUND_SUBACCORDION_ITEM_CLASS}>
          <AccordionTrigger>
            <div className="flex flex-wrap items-center gap-2">
              <Radio className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
              <span>{t('coreEditor.outbound.freedom.noisesTitle', { defaultValue: 'UDP noises' })}</span>
            </div>
          </AccordionTrigger>
          <AccordionContent className="space-y-4 px-2 pb-4">
            {noiseRows.map((row, i) => (
              <div
                key={i}
                className="rounded-lg border border-border bg-muted/15 p-4 shadow-sm"
              >
                <div className="mb-3 flex items-center justify-between gap-2">
                  <span className="text-xs font-medium text-muted-foreground">
                    {t('coreEditor.outbound.freedom.noiseRowLabel', { index: i + 1, defaultValue: 'Noise {{index}}' })}
                  </span>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8 shrink-0 text-muted-foreground hover:text-destructive"
                    aria-label={t('coreEditor.outbound.freedom.removeNoise', { defaultValue: 'Remove noise' })}
                    onClick={() => {
                      const nr = noiseRows.filter((_, j) => j !== i)
                      setNoiseRows(nr)
                      syncNoisesAndRules(nr, ruleRows)
                    }}
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-12 sm:items-end">
                  <div className="flex flex-col gap-1.5 sm:col-span-3">
                    <Label className="text-xs font-medium text-muted-foreground">
                      {t('coreEditor.outbound.freedom.noiseType', { defaultValue: 'Type' })}
                    </Label>
                    <Select
                      dir="ltr"
                      value={row.type || 'rand'}
                      onValueChange={v => {
                        const nr = noiseRows.map((x, j) => (j === i ? { ...x, type: v } : x))
                        setNoiseRows(nr)
                        syncNoisesAndRules(nr, ruleRows)
                      }}
                    >
                      <SelectTrigger className="h-10" dir="ltr">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent dir="ltr">
                        <SelectItem value="rand">rand</SelectItem>
                        <SelectItem value="str">str</SelectItem>
                        <SelectItem value="base64">base64</SelectItem>
                        <SelectItem value="hex">hex</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="flex min-w-0 flex-col gap-1.5 sm:col-span-6">
                    <Label className="text-xs font-medium text-muted-foreground">
                      {t('coreEditor.outbound.freedom.noisePacket', { defaultValue: 'Packet' })}
                    </Label>
                    <Input
                      dir="ltr"
                      className="h-10 text-xs"
                      placeholder={t('coreEditor.outbound.freedom.noisePacketHint', {
                        defaultValue: 'Length, text, base64, or hex (see docs)',
                      })}
                      value={row.packet}
                      onChange={e => {
                        const v = e.target.value
                        const nr = noiseRows.map((x, j) => (j === i ? { ...x, packet: v } : x))
                        setNoiseRows(nr)
                        syncNoisesAndRules(nr, ruleRows)
                      }}
                    />
                  </div>
                  <div className="flex flex-col gap-1.5 sm:col-span-3">
                    <Label className="text-xs font-medium text-muted-foreground">
                      {t('coreEditor.outbound.freedom.noiseDelay', { defaultValue: 'Delay (ms)' })}
                    </Label>
                    <Input
                      dir="ltr"
                      className="h-10 text-xs"
                      placeholder="10-16"
                      value={row.delay}
                      onChange={e => {
                        const v = e.target.value
                        const nr = noiseRows.map((x, j) => (j === i ? { ...x, delay: v } : x))
                        setNoiseRows(nr)
                        syncNoisesAndRules(nr, ruleRows)
                      }}
                    />
                  </div>
                </div>
              </div>
            ))}
            <Button
              type="button"
              variant="secondary"
              size="sm"
              className="w-full gap-1.5"
              onClick={() => {
                const nr = [...noiseRows, { type: 'rand', packet: '', delay: '' }]
                setNoiseRows(nr)
              }}
            >
              <Plus className="h-4 w-4" />
              {t('coreEditor.outbound.freedom.addNoise', { defaultValue: 'Add noise' })}
            </Button>
          </AccordionContent>
        </AccordionItem>

        <AccordionItem value="finalRules" className={OUTBOUND_SUBACCORDION_ITEM_CLASS}>
          <AccordionTrigger>
            <div className="flex flex-wrap items-center gap-2">
              <ListOrdered className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
              <span>{t('coreEditor.outbound.freedom.finalRulesTitle', { defaultValue: 'Final rules' })}</span>
            </div>
          </AccordionTrigger>
          <AccordionContent className="space-y-4 px-2 pb-4">
            <p className="text-xs leading-relaxed text-muted-foreground">
              {t('coreEditor.outbound.freedom.finalRulesHint', {
                defaultValue:
                  'Rules are matched in order (AND across fields). IP list: one CIDR or geoip tag per line.',
              })}
            </p>
            {ruleRows.map((row, i) => (
              <div key={i} className="rounded-lg border border-border bg-muted/15 p-4 shadow-sm">
                <div className="mb-3 flex items-center justify-between gap-2">
                  <span className="text-xs font-medium text-muted-foreground">
                    {t('coreEditor.outbound.freedom.ruleRowLabel', { index: i + 1, defaultValue: 'Rule {{index}}' })}
                  </span>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8 shrink-0 text-muted-foreground hover:text-destructive"
                    aria-label={t('coreEditor.outbound.freedom.removeRule', { defaultValue: 'Remove rule' })}
                    onClick={() => {
                      const rr = ruleRows.filter((_, j) => j !== i)
                      setRuleRows(rr)
                      syncNoisesAndRules(noiseRows, rr)
                    }}
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>

                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
                  <div className="flex min-w-0 flex-col gap-1.5">
                    <Label className="text-xs font-medium text-muted-foreground">
                      {t('coreEditor.outbound.freedom.ruleAction', { defaultValue: 'Action' })}
                    </Label>
                    <Select
                      dir="ltr"
                      value={row.action}
                      onValueChange={v => {
                        const rr = ruleRows.map((x, j) => (j === i ? { ...x, action: v as 'allow' | 'block' } : x))
                        setRuleRows(rr)
                        syncNoisesAndRules(noiseRows, rr)
                      }}
                    >
                      <SelectTrigger className="h-10" dir="ltr">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent dir="ltr">
                        <SelectItem value="allow">allow</SelectItem>
                        <SelectItem value="block">block</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="flex min-w-0 flex-col gap-1.5">
                    <Label className="text-xs font-medium text-muted-foreground">
                      {t('coreEditor.outbound.freedom.ruleNetwork', { defaultValue: 'Network' })}
                    </Label>
                    <Input
                      dir="ltr"
                      className="h-10 w-full min-w-0 text-xs"
                      placeholder="tcp, udp, tcp,udp"
                      value={row.network}
                      onChange={e => {
                        const v = e.target.value
                        const rr = ruleRows.map((x, j) => (j === i ? { ...x, network: v } : x))
                        setRuleRows(rr)
                        syncNoisesAndRules(noiseRows, rr)
                      }}
                    />
                  </div>
                  <div className="flex min-w-0 flex-col gap-1.5">
                    <Label className="text-xs font-medium text-muted-foreground">
                      {t('coreEditor.outbound.freedom.rulePort', { defaultValue: 'Port' })}
                    </Label>
                    <Input
                      dir="ltr"
                      className="h-10 w-full min-w-0 text-xs"
                      placeholder="22, 443"
                      value={row.port}
                      onChange={e => {
                        const v = e.target.value
                        const rr = ruleRows.map((x, j) => (j === i ? { ...x, port: v } : x))
                        setRuleRows(rr)
                        syncNoisesAndRules(noiseRows, rr)
                      }}
                    />
                  </div>
                  <div className="flex min-w-0 flex-col gap-1.5">
                    <Label className="text-xs font-medium text-muted-foreground">
                      {t('coreEditor.outbound.freedom.ruleBlockDelay', { defaultValue: 'Block delay (s)' })}
                    </Label>
                    <Input
                      dir="ltr"
                      className="h-10 w-full min-w-0 text-xs"
                      placeholder="30 or 30-90"
                      value={row.blockDelay}
                      onChange={e => {
                        const v = e.target.value
                        const rr = ruleRows.map((x, j) => (j === i ? { ...x, blockDelay: v } : x))
                        setRuleRows(rr)
                        syncNoisesAndRules(noiseRows, rr)
                      }}
                    />
                  </div>
                </div>

                <div className="mt-3 flex flex-col gap-1.5">
                  <Label className="text-xs font-medium text-muted-foreground">
                    {t('coreEditor.outbound.freedom.ruleIpList', { defaultValue: 'IP / CIDR / geoip' })}
                  </Label>
                  <Textarea
                    dir="ltr"
                    className="min-h-[72px] resize-y text-xs"
                    placeholder={'10.0.0.0/8\ngeoip:cn'}
                    value={row.ipText}
                    onChange={e => {
                      const v = e.target.value
                      const rr = ruleRows.map((x, j) => (j === i ? { ...x, ipText: v } : x))
                      setRuleRows(rr)
                      syncNoisesAndRules(noiseRows, rr)
                    }}
                  />
                </div>
              </div>
            ))}
            <Button
              type="button"
              variant="secondary"
              size="sm"
              className="w-full gap-1.5"
              onClick={() => {
                const rr = [...ruleRows, { action: 'block' as const, network: '', port: '', ipText: '', blockDelay: '' }]
                setRuleRows(rr)
              }}
            >
              <Plus className="h-4 w-4" />
              {t('coreEditor.outbound.freedom.addRule', { defaultValue: 'Add rule' })}
            </Button>
          </AccordionContent>
        </AccordionItem>
      </Accordion>
    </div>
  )
}

type DnsRuleRow = { action: string; qtype: string; domainText: string }

const DNS_ACTIONS = ['direct', 'hijack', 'drop', 'reject'] as const

function parseDnsRuleRows(settings: Record<string, unknown>): DnsRuleRow[] {
  const raw = settings.rules
  if (!Array.isArray(raw) || raw.length === 0) return []
  return raw.map((item): DnsRuleRow => {
    if (!item || typeof item !== 'object' || Array.isArray(item)) {
      return { action: 'hijack', qtype: '', domainText: '' }
    }
    const o = item as Record<string, unknown>
    const dom = o.domain
    let domainText = ''
    if (Array.isArray(dom)) domainText = dom.map(x => String(x)).join('\n')
    const q = o.qtype
    const qtype = q === undefined || q === null ? '' : String(q)
    const act = o.action
    const action =
      typeof act === 'string' && (DNS_ACTIONS as readonly string[]).includes(act) ? act : 'hijack'
    return { action, qtype, domainText }
  })
}

function buildDnsRuleObject(row: DnsRuleRow): Record<string, unknown> | null {
  const action = row.action.trim()
  if (!action) return null
  const o: Record<string, unknown> = { action }
  const qt = row.qtype.trim()
  if (qt) {
    if (/^\d+$/.test(qt)) o.qtype = Number(qt)
    else o.qtype = qt
  }
  const domains = row.domainText
    .split(/[\n,]+/)
    .map(s => s.trim())
    .filter(Boolean)
  if (domains.length > 0) o.domain = domains
  return o
}

function OutboundDnsSettings({ ob, patchOutbound, t }: { ob: Outbound; patchOutbound: PatchOutbound; t: TFunction }) {
  const s = readSettings(ob)
  /** Xray `DNSOutboundConfig` uses `network` / `address` / `port` (not `rewrite*`). Accept legacy keys when reading. */
  const networkRaw = s.network ?? s.rewriteNetwork
  const networkSelect =
    networkRaw === 'tcp' || networkRaw === 'udp'
      ? networkRaw
      : Array.isArray(networkRaw) &&
          networkRaw.length > 0 &&
          (networkRaw[0] === 'tcp' || networkRaw[0] === 'udp')
        ? String(networkRaw[0])
        : '__preserve__'
  const addrRaw = s.address ?? s.rewriteAddress
  const dnsAddress = typeof addrRaw === 'string' ? addrRaw : ''
  const dnsPort = s.port ?? s.rewritePort
  const dnsPortStr = dnsPort !== undefined && dnsPort !== null ? String(dnsPort) : ''
  const userLevel = s.userLevel !== undefined && s.userLevel !== null ? String(s.userLevel) : ''

  const [ruleRows, setRuleRows] = useState<DnsRuleRow[]>(() => parseDnsRuleRows(s))

  useEffect(() => {
    setRuleRows(parseDnsRuleRows(readSettings(ob)))
  }, [ob])

  const commitDns = (next: Record<string, unknown>) => {
    commitSettings(ob, next, patchOutbound)
  }

  const syncDnsRules = (rr: DnsRuleRow[]) => {
    const base = readSettings(ob)
    const rules = rr.map(buildDnsRuleObject).filter(Boolean) as Record<string, unknown>[]
    const next = { ...base }
    if (rules.length > 0) next.rules = rules
    else delete next.rules
    commitDns(next)
  }

  return (
    <div className="flex flex-col gap-4">
      <p className="text-xs text-muted-foreground">
        {t('coreEditor.outbound.dns.blurb', {
          defaultValue:
            'DNS outbound handles plaintext DNS from routing (e.g. TUN / transparent / dokodemo). Optional rewrites and ordered rules; see Xray docs for full syntax.',
        })}
      </p>

      <div className="grid w-full gap-4 sm:grid-cols-2">
        <div className="flex min-w-0 w-full flex-col gap-2">
          <Label className="text-xs font-medium">
            {t('coreEditor.outbound.dns.rewriteNetwork', { defaultValue: 'Rewrite transport' })}
          </Label>
          <Select
            dir="ltr"
            value={networkSelect}
            onValueChange={v => {
              const cur = readSettings(ob)
              const next = { ...cur }
              delete next.rewriteNetwork
              if (v === '__preserve__') delete next.network
              else next.network = v
              commitDns(next)
            }}
          >
            <SelectTrigger className="h-10 w-full min-w-0" dir="ltr">
              <SelectValue />
            </SelectTrigger>
            <SelectContent dir="ltr">
              <SelectItem value="__preserve__">
                {t('coreEditor.outbound.dns.rewriteNetworkPreserve', { defaultValue: 'Keep original' })}
              </SelectItem>
              <SelectItem value="tcp">tcp</SelectItem>
              <SelectItem value="udp">udp</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="flex min-w-0 w-full flex-col gap-2">
          <Label className="text-xs font-medium">{t('coreEditor.outbound.dns.userLevel', { defaultValue: 'User level' })}</Label>
          <Input
            type="number"
            dir="ltr"
            className="h-10 w-full min-w-0"
            placeholder="0"
            value={userLevel}
            onChange={e => {
              const v = e.target.value
              const cur = readSettings(ob)
              const next = { ...cur }
              if (v === '') delete next.userLevel
              else {
                const n = Number(v)
                next.userLevel = Number.isFinite(n) ? n : v
              }
              commitDns(next)
            }}
          />
        </div>

        <div className="flex min-w-0 w-full flex-col gap-2 sm:col-span-2">
          <Label className="text-xs font-medium">{t('coreEditor.outbound.dns.rewriteAddress', { defaultValue: 'Rewrite address' })}</Label>
          <Input
            dir="ltr"
            className="h-10 w-full min-w-0 text-xs"
            placeholder="1.1.1.1"
            value={dnsAddress}
            onChange={e => {
              const v = e.target.value
              const cur = readSettings(ob)
              const next = { ...cur }
              delete next.rewriteAddress
              if (!v.trim()) delete next.address
              else next.address = v
              commitDns(next)
            }}
          />
        </div>

        <div className="flex min-w-0 w-full flex-col gap-2 sm:col-span-2">
          <Label className="text-xs font-medium">{t('coreEditor.outbound.dns.rewritePort', { defaultValue: 'Rewrite port' })}</Label>
          <Input
            dir="ltr"
            className="h-10 w-full min-w-0 text-xs"
            placeholder="53"
            value={dnsPortStr}
            onChange={e => {
              const v = e.target.value.trim()
              const cur = readSettings(ob)
              const next = { ...cur }
              delete next.rewritePort
              if (v === '') delete next.port
              else {
                const n = Number(v)
                next.port = Number.isFinite(n) ? n : v
              }
              commitDns(next)
            }}
          />
        </div>
      </div>

      <Accordion type="multiple" className="!mt-0 flex w-full flex-col gap-y-3">
        <AccordionItem value="dns-rules" className={OUTBOUND_SUBACCORDION_ITEM_CLASS}>
          <AccordionTrigger>
            <div className="flex flex-wrap items-center gap-2">
              <Globe2 className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
              <span>{t('coreEditor.outbound.dns.rulesTitle', { defaultValue: 'DNS rules' })}</span>
            </div>
          </AccordionTrigger>
          <AccordionContent className="space-y-4 px-2 pb-4">
            <p className="text-xs leading-relaxed text-muted-foreground">
              {t('coreEditor.outbound.dns.rulesHint', {
                defaultValue: 'Conditions combine with AND. Domain: same syntax as routing (one per line). Qtype: number, range string, or comma list.',
              })}
            </p>
            {ruleRows.map((row, i) => (
              <div
                key={i}
                className="rounded-lg border border-border bg-muted/15 p-4 shadow-sm"
              >
                <div className="mb-3 flex items-center justify-between gap-2">
                  <span className="text-xs font-medium text-muted-foreground">
                    {t('coreEditor.outbound.dns.ruleRowLabel', { index: i + 1, defaultValue: 'Rule {{index}}' })}
                  </span>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8 shrink-0 text-muted-foreground hover:text-destructive"
                    aria-label={t('coreEditor.outbound.dns.removeRule', { defaultValue: 'Remove rule' })}
                    onClick={() => {
                      const rr = ruleRows.filter((_, j) => j !== i)
                      setRuleRows(rr)
                      syncDnsRules(rr)
                    }}
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <div className="flex min-w-0 flex-col gap-1.5">
                    <Label className="text-xs font-medium text-muted-foreground">
                      {t('coreEditor.outbound.dns.ruleAction', { defaultValue: 'Action' })}
                    </Label>
                    <Select
                      dir="ltr"
                      value={row.action}
                      onValueChange={v => {
                        const rr = ruleRows.map((x, j) => (j === i ? { ...x, action: v } : x))
                        setRuleRows(rr)
                        syncDnsRules(rr)
                      }}
                    >
                      <SelectTrigger className="h-10 w-full min-w-0" dir="ltr">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent dir="ltr">
                        {DNS_ACTIONS.map(a => (
                          <SelectItem key={a} value={a}>
                            {a}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="flex min-w-0 flex-col gap-1.5">
                    <Label className="text-xs font-medium text-muted-foreground">
                      {t('coreEditor.outbound.dns.ruleQtype', { defaultValue: 'Qtype' })}
                    </Label>
                    <Input
                      dir="ltr"
                      className="h-10 w-full min-w-0 text-xs"
                      placeholder={t('coreEditor.outbound.dns.qtypePlaceholder', { defaultValue: 'e.g. 1 or 5-10' })}
                      value={row.qtype}
                      onChange={e => {
                        const v = e.target.value
                        const rr = ruleRows.map((x, j) => (j === i ? { ...x, qtype: v } : x))
                        setRuleRows(rr)
                        syncDnsRules(rr)
                      }}
                    />
                  </div>
                </div>
                <div className="mt-3 flex flex-col gap-1.5">
                  <Label className="text-xs font-medium text-muted-foreground">
                    {t('coreEditor.outbound.dns.ruleDomainList', {
                      defaultValue: 'Domain matchers (one per line)',
                    })}
                  </Label>
                  <Textarea
                    dir="ltr"
                    className="min-h-[88px] resize-y text-xs"
                    placeholder={t('coreEditor.outbound.dns.domainPlaceholder', {
                      defaultValue: 'geosite:cn\ndomain:example.com',
                    })}
                    value={row.domainText}
                    onChange={e => {
                      const v = e.target.value
                      const rr = ruleRows.map((x, j) => (j === i ? { ...x, domainText: v } : x))
                      setRuleRows(rr)
                      syncDnsRules(rr)
                    }}
                  />
                </div>
              </div>
            ))}
            <Button
              type="button"
              variant="secondary"
              size="sm"
              className="w-full gap-1.5"
              onClick={() => {
                const rr = [...ruleRows, { action: 'hijack', qtype: '', domainText: '' }]
                setRuleRows(rr)
              }}
            >
              <Plus className="h-4 w-4" />
              {t('coreEditor.outbound.dns.addRule', { defaultValue: 'Add rule' })}
            </Button>
          </AccordionContent>
        </AccordionItem>
      </Accordion>
    </div>
  )
}

function OutboundLoopbackInboundTagSelect({ ob, patchOutbound, t }: { ob: Outbound; patchOutbound: PatchOutbound; t: TFunction }) {
  const profile = useCoreEditorStore(s => s.xrayProfile)
  const inboundTags = useMemo(() => {
    const list = profile?.inbounds ?? []
    const seen = new Set<string>()
    const out: string[] = []
    for (const ib of list as Array<{ tag?: string }>) {
      const tag = String(ib.tag ?? '').trim()
      if (!tag || seen.has(tag)) continue
      seen.add(tag)
      out.push(tag)
    }
    out.sort((a, b) => a.localeCompare(b, undefined, { sensitivity: 'base' }))
    return out
  }, [profile])

  const s = readSettings(ob)
  const inboundTag = typeof s.inboundTag === 'string' ? s.inboundTag.trim() : ''
  const selectValue = inboundTag || '__none__'
  const orphan = Boolean(inboundTag && !inboundTags.includes(inboundTag))

  return (
    <div className="flex max-w-xl flex-col gap-2">
      <Label className="text-xs font-medium">
        {t('coreEditor.outbound.loopback.inboundTag', { defaultValue: 'Inbound tag' })}
      </Label>
      <Select
        dir="ltr"
        value={selectValue}
        onValueChange={v => {
          const cur = readSettings(ob)
          const next = { ...cur }
          if (v === '__none__') delete next.inboundTag
          else next.inboundTag = v
          commitSettings(ob, next, patchOutbound)
        }}
      >
        <SelectTrigger className="h-10 text-xs" dir="ltr">
          <SelectValue
            placeholder={t('coreEditor.outbound.loopback.pickInbound', { defaultValue: 'Choose an inbound tag…' })}
          />
        </SelectTrigger>
        <SelectContent dir="ltr">
          <SelectItem value="__none__">
            {t('coreEditor.outbound.loopback.none', { defaultValue: '— None —' })}
          </SelectItem>
          {orphan ? (
            <SelectItem value={inboundTag}>
              {t('coreEditor.outbound.loopback.orphanTag', {
                tag: inboundTag,
                defaultValue: '{{tag}} (not in current inbounds)',
              })}
            </SelectItem>
          ) : null}
          {inboundTags.map(tag => (
            <SelectItem key={tag} value={tag}>
              {tag}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <p className="text-xs text-muted-foreground">
        {t('coreEditor.outbound.loopback.hint', {
          defaultValue: 'Traffic from this outbound is re-injected into routing using this inbound tag.',
        })}
      </p>
    </div>
  )
}

function OutboundBlackholeSettings({ ob, patchOutbound, t }: { ob: Outbound; patchOutbound: PatchOutbound; t: TFunction }) {
  const s = readSettings(ob)
  const resp = (s.response && typeof s.response === 'object' && !Array.isArray(s.response) ? s.response : {}) as Record<string, unknown>
  const responseType = resp.type === 'http' ? 'http' : 'none'

  return (
    <div className="flex flex-col gap-2">
      <Label className="text-xs font-medium">{t('coreEditor.outbound.blackhole.responseType', { defaultValue: 'Response' })}</Label>
      <Select
        dir="ltr"
        value={responseType}
        onValueChange={v => {
          const cur = readSettings(ob)
          const next = { ...cur }
          if (v === 'none') {
            delete next.response
          } else {
            next.response = { type: 'http' }
          }
          commitSettings(ob, next, patchOutbound)
        }}
      >
        <SelectTrigger className="h-10 max-w-md" dir="ltr">
          <SelectValue />
        </SelectTrigger>
        <SelectContent dir="ltr">
          <SelectItem value="none">{t('coreEditor.outbound.blackhole.responseNone', { defaultValue: 'Close immediately (none)' })}</SelectItem>
          <SelectItem value="http">{t('coreEditor.outbound.blackhole.responseHttp', { defaultValue: 'HTTP 403 then close' })}</SelectItem>
        </SelectContent>
      </Select>
    </div>
  )
}

export function OutboundSpecialProtocolSettings({
  ob,
  patchOutbound,
  t,
}: {
  ob: Outbound
  patchOutbound: PatchOutbound
  t: TFunction
}) {
  if (ob.protocol === 'freedom') {
    return (
      <>
        <Separator className="my-1" />
        <OutboundFreedomSettings ob={ob} patchOutbound={patchOutbound} t={t} />
      </>
    )
  }
  if (ob.protocol === 'dns') {
    return (
      <>
        <Separator className="my-1" />
        <OutboundDnsSettings ob={ob} patchOutbound={patchOutbound} t={t} />
      </>
    )
  }
  if (ob.protocol === 'blackhole') {
    return (
      <>
        <Separator className="my-1" />
        <OutboundBlackholeSettings ob={ob} patchOutbound={patchOutbound} t={t} />
      </>
    )
  }
  if (ob.protocol === 'loopback') {
    return (
      <>
        <Separator className="my-1" />
        <OutboundLoopbackInboundTagSelect ob={ob} patchOutbound={patchOutbound} t={t} />
      </>
    )
  }
  return null
}
