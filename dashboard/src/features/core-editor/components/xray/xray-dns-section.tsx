import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { StringArrayPopoverInput } from '@/components/common/string-array-popover-input'
import { CoreEditorDataTable } from '@/features/core-editor/components/shared/core-editor-data-table'
import { CoreEditorFormDialog } from '@/features/core-editor/components/shared/core-editor-form-dialog'
import { useSectionHeaderAddPulseEffect, type SectionHeaderAddPulse } from '@/features/core-editor/hooks/use-section-header-add-pulse'
import { useXrayPersistModifyGuard } from '@/features/core-editor/hooks/use-xray-persist-modify-guard'
import { remapIndexAfterArrayMove } from '@/features/core-editor/kit/remap-index-after-move'
import { useCoreEditorStore } from '@/features/core-editor/state/core-editor-store'
import useDirDetection from '@/hooks/use-dir-detection'
import { cn } from '@/lib/utils'
import type { Dns, NameServer, Profile } from '@pasarguard/xray-config-kit'
import { arrayMove } from '@dnd-kit/sortable'
import type { ColumnDef } from '@tanstack/react-table'
import { Globe, Pencil, Plus, Trash2 } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useForm } from 'react-hook-form'
import { useTranslation } from 'react-i18next'

/** Kit-supported global DNS query strategies. `UseSystem` is intentionally absent (see {@link Dns}). */
const QUERY_STRATEGY_OPTIONS = ['UseIP', 'UseIPv4', 'UseIPv6'] as const
type QueryStrategy = (typeof QUERY_STRATEGY_OPTIONS)[number]
const QUERY_STRATEGY_INHERIT = '__inherit'

type DnsServerEntry = string | NameServer

interface ServerFormValues {
  address: string
  port: string
  tag: string
  domains: string[]
  expectedIPs: string[]
  skipFallback: boolean
  queryStrategy: QueryStrategy | typeof QUERY_STRATEGY_INHERIT
}

interface HostFormValues {
  domain: string
  addresses: string[]
}

type DialogMode = 'add' | 'edit'

interface XrayDnsSectionProps {
  headerAddPulse?: SectionHeaderAddPulse
  headerAddEpoch?: number
}

function defaultDns(): Dns {
  return { servers: [] }
}

function serverAddress(v: DnsServerEntry): string {
  return typeof v === 'string' ? v : (v.address ?? '')
}

function serverPortDisplay(v: DnsServerEntry): string {
  if (typeof v === 'string') return ''
  return v.port !== undefined && v.port !== null ? String(v.port) : ''
}

function serverDomainsSummary(v: DnsServerEntry): string {
  if (typeof v === 'string') return ''
  const d = v.domains ?? []
  if (d.length === 0) return ''
  if (d.length <= 2) return d.join(', ')
  return `${d.slice(0, 2).join(', ')} (+${d.length - 2})`
}

function serverStrategyDisplay(v: DnsServerEntry): string {
  if (typeof v === 'string') return ''
  return v.queryStrategy ?? ''
}

function serverSearchHaystack(v: DnsServerEntry): string {
  if (typeof v === 'string') return v
  const parts: string[] = [
    v.address ?? '',
    v.port !== undefined ? String(v.port) : '',
    v.tag ?? '',
    v.queryStrategy ?? '',
    ...(v.domains ?? []),
    ...(v.expectedIPs ?? []),
  ]
  try {
    parts.push(JSON.stringify(v))
  } catch {
    /* ignore */
  }
  return parts.join(' ')
}

function entryToForm(entry: DnsServerEntry | null): ServerFormValues {
  if (entry == null) {
    return {
      address: '',
      port: '',
      tag: '',
      domains: [],
      expectedIPs: [],
      skipFallback: false,
      queryStrategy: QUERY_STRATEGY_INHERIT,
    }
  }
  if (typeof entry === 'string') {
    return {
      address: entry,
      port: '',
      tag: '',
      domains: [],
      expectedIPs: [],
      skipFallback: false,
      queryStrategy: QUERY_STRATEGY_INHERIT,
    }
  }
  return {
    address: entry.address ?? '',
    port: entry.port !== undefined && entry.port !== null ? String(entry.port) : '',
    tag: entry.tag ?? '',
    domains: entry.domains ? [...entry.domains] : [],
    expectedIPs: entry.expectedIPs ? [...entry.expectedIPs] : [],
    skipFallback: entry.skipFallback === true,
    queryStrategy: (entry.queryStrategy as QueryStrategy | undefined) ?? QUERY_STRATEGY_INHERIT,
  }
}

/** Collapses a {@link ServerFormValues} back into the kit type. Only `address` set → returns a plain string. */
function formToEntry(form: ServerFormValues): DnsServerEntry | null {
  const address = form.address.trim()
  if (!address) return null
  const domains = form.domains.map(s => s.trim()).filter(s => s.length > 0)
  const expectedIPs = form.expectedIPs.map(s => s.trim()).filter(s => s.length > 0)
  const tag = form.tag.trim()
  const portRaw = form.port.trim()
  let port: number | undefined
  if (portRaw !== '') {
    const n = Number(portRaw)
    if (Number.isFinite(n) && Number.isInteger(n) && n >= 0 && n <= 65535) port = n
  }
  const queryStrategy = form.queryStrategy === QUERY_STRATEGY_INHERIT ? undefined : form.queryStrategy
  const ns: NameServer = {
    address,
    ...(port !== undefined ? { port } : {}),
    ...(domains.length > 0 ? { domains } : {}),
    ...(expectedIPs.length > 0 ? { expectedIPs } : {}),
    ...(form.skipFallback ? { skipFallback: true } : {}),
    ...(queryStrategy ? { queryStrategy } : {}),
    ...(tag ? { tag } : {}),
  }
  const onlyAddress =
    port === undefined &&
    domains.length === 0 &&
    expectedIPs.length === 0 &&
    !form.skipFallback &&
    queryStrategy === undefined &&
    !tag
  return onlyAddress ? address : ns
}

function updateDns(profile: Profile, updater: (dns: Dns) => Dns): Profile {
  const next = updater(profile.dns ?? defaultDns())
  return { ...profile, dns: next }
}

function replaceServer(profile: Profile, index: number, entry: DnsServerEntry): Profile {
  return updateDns(profile, dns => {
    const servers = [...dns.servers]
    servers[index] = entry
    return { ...dns, servers }
  })
}

function removeServer(profile: Profile, index: number): Profile {
  return updateDns(profile, dns => ({ ...dns, servers: dns.servers.filter((_, i) => i !== index) }))
}

function setHostMapping(profile: Profile, domain: string, addresses: string[], previousDomain?: string): Profile {
  return updateDns(profile, dns => {
    const hosts: Record<string, string | string[]> = { ...(dns.hosts ?? {}) }
    if (previousDomain && previousDomain !== domain) delete hosts[previousDomain]
    const cleaned = addresses.map(a => a.trim()).filter(a => a.length > 0)
    if (cleaned.length === 0) {
      delete hosts[domain]
    } else {
      hosts[domain] = cleaned.length === 1 ? cleaned[0] : cleaned
    }
    const next: Dns = { ...dns }
    if (Object.keys(hosts).length === 0) {
      delete (next as { hosts?: unknown }).hosts
    } else {
      ;(next as { hosts?: Record<string, string | string[]> }).hosts = hosts
    }
    return next
  })
}

function removeHostMapping(profile: Profile, domain: string): Profile {
  return updateDns(profile, dns => {
    const hosts: Record<string, string | string[]> = { ...(dns.hosts ?? {}) }
    delete hosts[domain]
    const next: Dns = { ...dns }
    if (Object.keys(hosts).length === 0) {
      delete (next as { hosts?: unknown }).hosts
    } else {
      ;(next as { hosts?: Record<string, string | string[]> }).hosts = hosts
    }
    return next
  })
}

function hostsToList(hosts: Record<string, string | string[]> | undefined): Array<{ domain: string; addresses: string[] }> {
  if (!hosts) return []
  return Object.entries(hosts).map(([domain, value]) => ({
    domain,
    addresses: Array.isArray(value) ? [...value] : [value],
  }))
}

export function XrayDnsSection({ headerAddPulse, headerAddEpoch }: XrayDnsSectionProps) {
  const { t } = useTranslation()
  const dir = useDirDetection()
  const profile = useCoreEditorStore(s => s.xrayProfile)
  const updateXrayProfile = useCoreEditorStore(s => s.updateXrayProfile)
  const { assertNoPersistBlockingErrors } = useXrayPersistModifyGuard()

  const dns = profile?.dns
  const enabled = dns != null

  const servers = useMemo<DnsServerEntry[]>(() => dns?.servers ?? [], [dns])
  const hostsList = useMemo(() => hostsToList(dns?.hosts), [dns])

  // ── Server dialog ──────────────────────────────────────────────────────────
  const [serverDialogOpen, setServerDialogOpen] = useState(false)
  const [dialogMode, setDialogMode] = useState<DialogMode>('edit')
  const [selectedServerIdx, setSelectedServerIdx] = useState(0)
  const [draftServer, setDraftServer] = useState<DnsServerEntry | null>(null)
  const [discardDraftOpen, setDiscardDraftOpen] = useState(false)
  const [blockAddWhileDraftOpen, setBlockAddWhileDraftOpen] = useState(false)

  const serverForm = useForm<ServerFormValues>({ defaultValues: entryToForm(null) })

  const profileRef = useRef(profile)
  profileRef.current = profile

  // Reset form whenever the dialog opens or the selected row changes.
  useEffect(() => {
    if (!serverDialogOpen) return
    const p = profileRef.current
    if (dialogMode === 'add') {
      serverForm.reset(entryToForm(draftServer))
      return
    }
    const row = p?.dns?.servers?.[selectedServerIdx]
    serverForm.reset(entryToForm(row ?? null))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [serverDialogOpen, dialogMode, selectedServerIdx])

  const beginAddServer = useCallback(() => {
    if (!profile) return
    if (serverDialogOpen && dialogMode === 'add') {
      setBlockAddWhileDraftOpen(true)
      return
    }
    if (!enabled) {
      // Auto-enable DNS so the new server is reachable.
      updateXrayProfile(p => ({ ...p, dns: p.dns ?? defaultDns() }))
    }
    setDraftServer('')
    setDialogMode('add')
    setServerDialogOpen(true)
  }, [profile, serverDialogOpen, dialogMode, enabled, updateXrayProfile])

  useSectionHeaderAddPulseEffect(headerAddPulse, headerAddEpoch, 'dns', beginAddServer)

  const finalizeServerDialogClose = () => {
    setServerDialogOpen(false)
    setDialogMode('edit')
    setDraftServer(null)
  }

  const handleServerDialogOpenChange = (open: boolean) => {
    if (open) {
      setServerDialogOpen(true)
      return
    }
    if (dialogMode === 'add' && draftServer !== null) {
      setDiscardDraftOpen(true)
      return
    }
    finalizeServerDialogClose()
  }

  const commitServer = () => {
    const values = serverForm.getValues()
    const entry = formToEntry(values)
    if (!entry) {
      serverForm.setError('address', {
        type: 'validate',
        message: t('coreEditor.dns.server.addressRequired', { defaultValue: 'Address is required.' }),
      })
      return
    }
    if (!assertNoPersistBlockingErrors()) return
    if (dialogMode === 'add') {
      updateXrayProfile(p => updateDns(p, dns => ({ ...dns, servers: [...dns.servers, entry] })))
      setSelectedServerIdx(servers.length)
    } else {
      updateXrayProfile(p => replaceServer(p, selectedServerIdx, entry))
    }
    finalizeServerDialogClose()
  }

  const serverColumns = useMemo<ColumnDef<DnsServerEntry, unknown>[]>(
    () => [
      {
        id: 'index',
        header: '#',
        cell: ({ row }) => row.index + 1,
      },
      {
        id: 'address',
        header: () => t('coreEditor.dns.server.address', { defaultValue: 'Address' }),
        cell: ({ row }) => (
          <span className="text-xs break-all">{serverAddress(row.original) || '—'}</span>
        ),
      },
      {
        id: 'port',
        header: () => t('coreEditor.dns.server.port', { defaultValue: 'Port' }),
        cell: ({ row }) => <span className="text-xs">{serverPortDisplay(row.original) || '—'}</span>,
      },
      {
        id: 'domains',
        header: () => t('coreEditor.dns.server.domains', { defaultValue: 'Domains' }),
        cell: ({ row }) => {
          const summary = serverDomainsSummary(row.original)
          return (
            <span className="line-clamp-2 min-w-0 max-w-56 text-xs" title={summary || undefined}>
              {summary || '—'}
            </span>
          )
        },
      },
      {
        id: 'strategy',
        header: () => t('coreEditor.dns.server.queryStrategy', { defaultValue: 'Strategy' }),
        cell: ({ row }) => (
          <span className="text-xs">{serverStrategyDisplay(row.original) || '—'}</span>
        ),
      },
    ],
    [t],
  )

  // ── Hosts dialog ───────────────────────────────────────────────────────────
  const [hostDialogOpen, setHostDialogOpen] = useState(false)
  const [hostDialogMode, setHostDialogMode] = useState<DialogMode>('edit')
  const [selectedHostDomain, setSelectedHostDomain] = useState<string | null>(null)
  const hostForm = useForm<HostFormValues>({ defaultValues: { domain: '', addresses: [] } })

  useEffect(() => {
    if (!hostDialogOpen) return
    if (hostDialogMode === 'add') {
      hostForm.reset({ domain: '', addresses: [] })
      return
    }
    const entry = hostsList.find(h => h.domain === selectedHostDomain)
    hostForm.reset({ domain: entry?.domain ?? '', addresses: entry?.addresses ?? [] })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hostDialogOpen, hostDialogMode, selectedHostDomain])

  const beginAddHost = useCallback(() => {
    if (!enabled) {
      updateXrayProfile(p => ({ ...p, dns: p.dns ?? defaultDns() }))
    }
    setHostDialogMode('add')
    setSelectedHostDomain(null)
    setHostDialogOpen(true)
  }, [enabled, updateXrayProfile])

  const beginEditHost = (domain: string) => {
    setHostDialogMode('edit')
    setSelectedHostDomain(domain)
    setHostDialogOpen(true)
  }

  const commitHost = () => {
    const values = hostForm.getValues()
    const domain = values.domain.trim()
    if (!domain) {
      hostForm.setError('domain', {
        type: 'validate',
        message: t('coreEditor.dns.host.domainRequired', { defaultValue: 'Domain is required.' }),
      })
      return
    }
    if (values.addresses.length === 0) {
      hostForm.setError('addresses', {
        type: 'validate',
        message: t('coreEditor.dns.host.addressesRequired', { defaultValue: 'At least one address is required.' }),
      })
      return
    }
    if (!assertNoPersistBlockingErrors()) return
    const prev = hostDialogMode === 'edit' ? (selectedHostDomain ?? undefined) : undefined
    if (hostDialogMode === 'add') {
      const existing = profileRef.current?.dns?.hosts ?? {}
      if (Object.prototype.hasOwnProperty.call(existing, domain)) {
        hostForm.setError('domain', {
          type: 'validate',
          message: t('coreEditor.dns.host.duplicateDomain', { defaultValue: 'A mapping for that domain already exists.' }),
        })
        return
      }
    }
    updateXrayProfile(p => setHostMapping(p, domain, values.addresses, prev))
    setHostDialogOpen(false)
    setSelectedHostDomain(null)
  }

  // ── Top-level patch helpers ────────────────────────────────────────────────
  const setEnabled = (next: boolean) => {
    updateXrayProfile(p => {
      if (next) {
        return { ...p, dns: p.dns ?? defaultDns() }
      }
      const { dns: _omit, ...rest } = p
      return rest as Profile
    })
  }

  const patchDns = (patch: Partial<Dns>) => {
    updateXrayProfile(p => updateDns(p, dns => ({ ...dns, ...patch })))
  }

  if (!profile) return null

  const queryStrategyValue: QueryStrategy | '__inherit' = (dns?.queryStrategy as QueryStrategy | undefined) ?? '__inherit'

  return (
    <div className="space-y-6">
      {/* Enable DNS toggle — always visible. */}
      <Card>
        <CardContent className="flex items-start justify-between gap-4 py-4">
          <div className="space-y-1">
            <Label className="text-sm font-medium">
              {t('coreEditor.dns.enable', { defaultValue: 'Enable DNS' })}
            </Label>
            <p className="text-xs text-muted-foreground">
              {t('coreEditor.dns.enableHint', { defaultValue: 'Enable built-in DNS server.' })}
            </p>
          </div>
          <Switch checked={enabled} onCheckedChange={setEnabled} aria-label={t('coreEditor.dns.enable', { defaultValue: 'Enable DNS' })} />
        </CardContent>
      </Card>

      {enabled && (
        <>
          {/* Global DNS options */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-medium">
                {t('coreEditor.dns.globalTitle', { defaultValue: 'Global settings' })}
              </CardTitle>
            </CardHeader>
            <CardContent className="grid gap-5 sm:grid-cols-2">
              <div className="flex min-w-0 flex-col gap-2 sm:col-span-2">
                <Label className="text-xs font-medium">
                  {t('coreEditor.dns.queryStrategy', { defaultValue: 'Query Strategy' })}
                </Label>
                <Select
                  value={queryStrategyValue}
                  onValueChange={v => {
                    if (v === '__inherit') {
                      patchDns({ queryStrategy: undefined })
                      return
                    }
                    patchDns({ queryStrategy: v as QueryStrategy })
                  }}
                >
                  <SelectTrigger className="h-10" dir="ltr">
                    <SelectValue
                      placeholder={t('coreEditor.dns.queryStrategyPlaceholder', { defaultValue: 'Default (UseIP)' })}
                    />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="__inherit">
                      {t('coreEditor.dns.queryStrategyDefault', { defaultValue: 'Default (UseIP)' })}
                    </SelectItem>
                    {QUERY_STRATEGY_OPTIONS.map(opt => (
                      <SelectItem key={opt} value={opt}>{opt}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="text-xs text-muted-foreground">
                  {t('coreEditor.dns.queryStrategyHint', {
                    defaultValue: 'Overall strategy to resolve domain names.',
                  })}
                </p>
              </div>

              <div className="flex items-start justify-between gap-3 rounded-md border p-3 sm:col-span-1">
                <div className="space-y-1 min-w-0">
                  <Label className="text-xs font-medium">
                    {t('coreEditor.dns.disableCache', { defaultValue: 'Disable cache' })}
                  </Label>
                  <p className="text-[11px] text-muted-foreground">
                    {t('coreEditor.dns.disableCacheHint', { defaultValue: 'Disables DNS caching.' })}
                  </p>
                </div>
                <Switch
                  checked={dns?.disableCache === true}
                  onCheckedChange={v => patchDns({ disableCache: v || undefined })}
                  aria-label={t('coreEditor.dns.disableCache', { defaultValue: 'Disable cache' })}
                />
              </div>

              <div className="flex items-start justify-between gap-3 rounded-md border p-3 sm:col-span-1">
                <div className="space-y-1 min-w-0">
                  <Label className="text-xs font-medium">
                    {t('coreEditor.dns.disableFallback', { defaultValue: 'Disable fallback' })}
                  </Label>
                  <p className="text-[11px] text-muted-foreground">
                    {t('coreEditor.dns.disableFallbackHint', { defaultValue: 'Disables fallback DNS queries.' })}
                  </p>
                </div>
                <Switch
                  checked={dns?.disableFallback === true}
                  onCheckedChange={v => patchDns({ disableFallback: v || undefined })}
                  aria-label={t('coreEditor.dns.disableFallback', { defaultValue: 'Disable fallback' })}
                />
              </div>
            </CardContent>
          </Card>

          {/* Servers */}
          <Card>
            <CardHeader className="flex flex-row items-center justify-between gap-3 pb-3">
              <CardTitle className="flex items-center gap-2 text-sm font-medium">
                <Globe className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
                {t('coreEditor.dns.serversTitle', { defaultValue: 'Servers' })}
              </CardTitle>
              <Button type="button" size="sm" variant="outline" onClick={beginAddServer}>
                <Plus className="h-4 w-4" />
                <span className="ms-1">{t('coreEditor.dns.addServer', { defaultValue: 'Add server' })}</span>
              </Button>
            </CardHeader>
            <CardContent>
              <CoreEditorDataTable
                columns={serverColumns}
                data={servers}
                getSearchableText={serverSearchHaystack}
                searchPlaceholder={t('coreEditor.dns.serverSearchPlaceholder', {
                  defaultValue: 'Search by address, tag, domain, strategy…',
                })}
                bulkDeleteTitle={t('coreEditor.dns.serverBulkDeleteTitle', {
                  defaultValue: 'Remove selected DNS servers',
                })}
                emptyLabel={t('coreEditor.dns.emptyServers', { defaultValue: 'No DNS servers' })}
                getRowId={(_, i) => String(i)}
                onRowClick={(_row, rowIndex) => {
                  if (serverDialogOpen && dialogMode === 'add') {
                    setBlockAddWhileDraftOpen(true)
                    return
                  }
                  setDraftServer(null)
                  setDialogMode('edit')
                  setSelectedServerIdx(rowIndex)
                  setServerDialogOpen(true)
                }}
                onRemoveRow={i => {
                  updateXrayProfile(p => removeServer(p, i))
                  setSelectedServerIdx(0)
                }}
                onBulkRemove={indices => {
                  const rm = new Set(indices)
                  updateXrayProfile(p =>
                    updateDns(p, dns => ({ ...dns, servers: dns.servers.filter((_, idx) => !rm.has(idx)) })),
                  )
                  setSelectedServerIdx(0)
                }}
                enableReorder
                onReorder={(from, to) => {
                  updateXrayProfile(p =>
                    updateDns(p, dns => ({ ...dns, servers: arrayMove([...dns.servers], from, to) })),
                  )
                  setSelectedServerIdx(sel => remapIndexAfterArrayMove(sel, from, to))
                }}
              />
            </CardContent>
          </Card>

          {/* Hosts */}
          <Card>
            <CardHeader className="flex flex-row items-center justify-between gap-3 pb-3">
              <CardTitle className="text-sm font-medium">
                {t('coreEditor.dns.hostsTitle', { defaultValue: 'Hosts' })}
              </CardTitle>
              <Button type="button" size="sm" variant="outline" onClick={beginAddHost}>
                <Plus className="h-4 w-4" />
                <span className="ms-1">{t('coreEditor.dns.addHost', { defaultValue: 'Add host' })}</span>
              </Button>
            </CardHeader>
            <CardContent>
              {hostsList.length === 0 ? (
                <div className="text-muted-foreground rounded-md border px-4 py-8 text-center text-sm">
                  {t('coreEditor.dns.emptyHosts', { defaultValue: 'No host mappings' })}
                </div>
              ) : (
                <ul className="divide-y rounded-md border">
                  {hostsList.map(entry => (
                    <li
                      key={entry.domain}
                      className={cn(
                        'flex flex-col gap-2 px-3 py-2 sm:flex-row sm:items-center sm:justify-between',
                      )}
                    >
                      <div className="min-w-0">
                        <div className="text-xs font-medium break-all">{entry.domain}</div>
                        <div className="text-[11px] text-muted-foreground break-all">
                          {entry.addresses.join(', ')}
                        </div>
                      </div>
                      <div className="flex shrink-0 gap-1.5">
                        <Button
                          type="button"
                          size="sm"
                          variant="ghost"
                          onClick={() => beginEditHost(entry.domain)}
                          title={t('edit')}
                        >
                          <Pencil className="h-4 w-4" />
                        </Button>
                        <Button
                          type="button"
                          size="sm"
                          variant="ghost"
                          onClick={() => updateXrayProfile(p => removeHostMapping(p, entry.domain))}
                          title={t('delete')}
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        </>
      )}

      {/* ── Server add/edit dialog ──────────────────────────────────────────── */}
      <CoreEditorFormDialog
        isDialogOpen={serverDialogOpen}
        onOpenChange={handleServerDialogOpenChange}
        leadingIcon={dialogMode === 'add' ? <Plus className="h-5 w-5 shrink-0" /> : <Pencil className="h-5 w-5 shrink-0" />}
        title={
          dialogMode === 'add'
            ? t('coreEditor.dns.dialogAddServer', { defaultValue: 'Add DNS server' })
            : t('coreEditor.dns.dialogEditServer', { defaultValue: 'Edit DNS server' })
        }
        size="md"
        footerExtra={
          <Button type="button" className="sm:min-w-[88px]" onClick={commitServer}>
            {dialogMode === 'add'
              ? t('coreEditor.dns.addToList', { defaultValue: 'Add to list' })
              : t('modify')}
          </Button>
        }
      >
        <Form {...serverForm}>
          <form className="grid gap-4 pb-2 sm:grid-cols-2" onSubmit={e => e.preventDefault()}>
            <FormField
              control={serverForm.control}
              name="address"
              render={({ field }) => (
                <FormItem className="sm:col-span-2 min-w-0">
                  <FormLabel className="text-xs font-medium">
                    {t('coreEditor.dns.server.address', { defaultValue: 'Address' })}
                  </FormLabel>
                  <FormControl>
                    <Input
                      {...field}
                      dir="ltr"
                      placeholder="8.8.8.8 / https://1.1.1.1/dns-query / tcp://1.1.1.1"
                      className="text-xs"
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={serverForm.control}
              name="port"
              render={({ field }) => (
                <FormItem className="min-w-0">
                  <FormLabel className="text-xs font-medium">
                    {t('coreEditor.dns.server.port', { defaultValue: 'Port' })}
                  </FormLabel>
                  <FormControl>
                    <Input
                      {...field}
                      dir="ltr"
                      inputMode="numeric"
                      placeholder="53"
                      className="text-xs"
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={serverForm.control}
              name="tag"
              render={({ field }) => (
                <FormItem className="min-w-0">
                  <FormLabel className="text-xs font-medium">
                    {t('coreEditor.dns.server.tag', { defaultValue: 'Tag' })}
                  </FormLabel>
                  <FormControl>
                    <Input
                      {...field}
                      dir="ltr"
                      placeholder={t('coreEditor.dns.server.tagPlaceholder', { defaultValue: 'optional' })}
                      className="text-xs"
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={serverForm.control}
              name="queryStrategy"
              render={({ field }) => (
                <FormItem className="sm:col-span-2 min-w-0">
                  <FormLabel className="text-xs font-medium">
                    {t('coreEditor.dns.server.queryStrategy', { defaultValue: 'Query Strategy' })}
                  </FormLabel>
                  <Select value={field.value} onValueChange={v => field.onChange(v)}>
                    <SelectTrigger className="h-10" dir="ltr">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value={QUERY_STRATEGY_INHERIT}>
                        {t('coreEditor.dns.server.inheritGlobal', { defaultValue: 'Inherit global' })}
                      </SelectItem>
                      {QUERY_STRATEGY_OPTIONS.map(opt => (
                        <SelectItem key={opt} value={opt}>{opt}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={serverForm.control}
              name="domains"
              render={({ field }) => (
                <FormItem className="sm:col-span-2 min-w-0">
                  <FormLabel className="text-xs font-medium">
                    {t('coreEditor.dns.server.domains', { defaultValue: 'Domains' })}
                  </FormLabel>
                  <FormControl>
                    <StringArrayPopoverInput
                      value={field.value}
                      onChange={field.onChange}
                      placeholder={t('coreEditor.dns.server.domainsPlaceholder', {
                        defaultValue: 'Add domain (e.g. geosite:netflix)',
                      })}
                      addPlaceholder={t('coreEditor.dns.server.domainsAddPlaceholder', {
                        defaultValue: 'domain:example.com',
                      })}
                      addButtonLabel={t('add', { defaultValue: 'Add' })}
                      itemsLabel={t('coreEditor.dns.server.domainsItemsLabel', { defaultValue: 'Domains' })}
                      emptyMessage={t('coreEditor.dns.server.domainsEmpty', { defaultValue: 'No domains added.' })}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={serverForm.control}
              name="expectedIPs"
              render={({ field }) => (
                <FormItem className="sm:col-span-2 min-w-0">
                  <FormLabel className="text-xs font-medium">
                    {t('coreEditor.dns.server.expectedIPs', { defaultValue: 'Expected IPs' })}
                  </FormLabel>
                  <FormControl>
                    <StringArrayPopoverInput
                      value={field.value}
                      onChange={field.onChange}
                      placeholder={t('coreEditor.dns.server.expectedIPsPlaceholder', {
                        defaultValue: 'Add IP / CIDR (e.g. geoip:cn)',
                      })}
                      addPlaceholder="geoip:cn"
                      addButtonLabel={t('add', { defaultValue: 'Add' })}
                      itemsLabel={t('coreEditor.dns.server.expectedIPsItemsLabel', { defaultValue: 'IPs' })}
                      emptyMessage={t('coreEditor.dns.server.expectedIPsEmpty', { defaultValue: 'No IPs added.' })}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={serverForm.control}
              name="skipFallback"
              render={({ field }) => (
                <FormItem className="flex flex-row items-start justify-between gap-3 rounded-md border p-3 sm:col-span-2">
                  <div className="space-y-1 min-w-0">
                    <FormLabel className="text-xs font-medium">
                      {t('coreEditor.dns.server.skipFallback', { defaultValue: 'Skip fallback' })}
                    </FormLabel>
                    <p className="text-[11px] text-muted-foreground">
                      {t('coreEditor.dns.server.skipFallbackHint', {
                        defaultValue: 'Skip this server during DNS fallback queries.',
                      })}
                    </p>
                  </div>
                  <FormControl>
                    <Switch checked={!!field.value} onCheckedChange={field.onChange} />
                  </FormControl>
                </FormItem>
              )}
            />
          </form>
        </Form>
      </CoreEditorFormDialog>

      {/* ── Host add/edit dialog ────────────────────────────────────────────── */}
      <CoreEditorFormDialog
        isDialogOpen={hostDialogOpen}
        onOpenChange={setHostDialogOpen}
        leadingIcon={hostDialogMode === 'add' ? <Plus className="h-5 w-5 shrink-0" /> : <Pencil className="h-5 w-5 shrink-0" />}
        title={
          hostDialogMode === 'add'
            ? t('coreEditor.dns.dialogAddHost', { defaultValue: 'Add host mapping' })
            : t('coreEditor.dns.dialogEditHost', { defaultValue: 'Edit host mapping' })
        }
        size="md"
        footerExtra={
          <Button type="button" className="sm:min-w-[88px]" onClick={commitHost}>
            {hostDialogMode === 'add'
              ? t('coreEditor.dns.addToList', { defaultValue: 'Add to list' })
              : t('modify')}
          </Button>
        }
      >
        <Form {...hostForm}>
          <form className="grid gap-4 pb-2" onSubmit={e => e.preventDefault()}>
            <FormField
              control={hostForm.control}
              name="domain"
              render={({ field }) => (
                <FormItem className="min-w-0">
                  <FormLabel className="text-xs font-medium">
                    {t('coreEditor.dns.host.domain', { defaultValue: 'Domain' })}
                  </FormLabel>
                  <FormControl>
                    <Input
                      {...field}
                      dir="ltr"
                      placeholder="domain:example.com / dns.google"
                      className="text-xs"
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={hostForm.control}
              name="addresses"
              render={({ field }) => (
                <FormItem className="min-w-0">
                  <FormLabel className="text-xs font-medium">
                    {t('coreEditor.dns.host.addresses', { defaultValue: 'Addresses' })}
                  </FormLabel>
                  <FormControl>
                    <StringArrayPopoverInput
                      value={field.value}
                      onChange={field.onChange}
                      placeholder={t('coreEditor.dns.host.addressesPlaceholder', {
                        defaultValue: 'Add IP or domain (one or more)',
                      })}
                      addPlaceholder="8.8.8.8 / 127.0.0.1"
                      addButtonLabel={t('add', { defaultValue: 'Add' })}
                      itemsLabel={t('coreEditor.dns.host.addressesItemsLabel', { defaultValue: 'Addresses' })}
                      emptyMessage={t('coreEditor.dns.host.addressesEmpty', { defaultValue: 'No addresses added.' })}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
          </form>
        </Form>
      </CoreEditorFormDialog>

      <AlertDialog open={discardDraftOpen} onOpenChange={setDiscardDraftOpen}>
        <AlertDialogContent dir={dir}>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {t('coreEditor.dns.discardDraftTitle', { defaultValue: 'Discard new DNS server?' })}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {t('coreEditor.dns.discardDraftDescription', {
                defaultValue: 'This server is not in the list yet. Closing without adding will discard your changes.',
              })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('cancel')}</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                setDiscardDraftOpen(false)
                finalizeServerDialogClose()
              }}
            >
              {t('coreEditor.dns.discardDraftAction', { defaultValue: 'Discard' })}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={blockAddWhileDraftOpen} onOpenChange={setBlockAddWhileDraftOpen}>
        <AlertDialogContent dir={dir}>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {t('coreEditor.dns.finishCurrentTitle', { defaultValue: 'Finish the current DNS server first' })}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {t('coreEditor.dns.finishCurrentDescription', {
                defaultValue: 'Add it to the list, or close the dialog and discard the draft, before starting another DNS server.',
              })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogAction type="button" className="sm:min-w-[88px]" onClick={() => setBlockAddWhileDraftOpen(false)}>
              {t('close', { defaultValue: 'Close' })}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
