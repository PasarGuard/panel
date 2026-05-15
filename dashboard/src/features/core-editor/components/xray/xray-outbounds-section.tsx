import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from '@/components/ui/alert-dialog'
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion'
import { Button } from '@/components/ui/button'
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Separator } from '@/components/ui/separator'
import { Switch } from '@/components/ui/switch'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Textarea } from '@/components/ui/textarea'
import { isBooleanParityField, XrayParityFormControl } from '@/features/core-editor/components/shared/xray-parity-form-control'
import { OutboundSpecialProtocolSettings } from '@/features/core-editor/components/xray/outbound-special-protocol-settings'
import { TcpHeaderObfuscationForm } from '@/features/core-editor/components/shared/tcp-header-obfuscation-form'
import { CoreEditorDataTable } from '@/features/core-editor/components/shared/core-editor-data-table'
import { CoreEditorFormDialog } from '@/features/core-editor/components/shared/core-editor-form-dialog'
import { JsonCodeEditorPanel } from '@/features/core-editor/components/shared/json-code-editor-panel'
import { pruneSockoptObject, XrayStreamSockoptFields } from '@/features/core-editor/components/shared/xray-stream-sockopt-editor'
import { inferParityFieldMode, outboundScalarParityFieldPrefersFullGridWidth, outboundSettingToString, parseOutboundSettingValue } from '@/features/core-editor/kit/xray-parity-value'
import { useCoreEditorStore } from '@/features/core-editor/state/core-editor-store'
import { useSectionHeaderAddPulseEffect, type SectionHeaderAddPulse } from '@/features/core-editor/hooks/use-section-header-add-pulse'
import { useXrayPersistModifyGuard } from '@/features/core-editor/hooks/use-xray-persist-modify-guard'
import {
  getOutboundStreamNetworkSelectValues,
  outboundStreamNetworkCompatibleWithReality,
  outboundVlessVisionFlowAllowed,
  vlessVisionFlowIncompatibleWithStreamSecurity,
} from '@/features/core-editor/kit/outbound-stream-dynamic'
import { profileDuplicateTagMessage, profileTagHasDuplicateUsage } from '@/features/core-editor/kit/profile-tag-uniqueness'
import { remapIndexAfterArrayMove } from '@/features/core-editor/kit/remap-index-after-move'
import {
  flattenOutboundSettings,
  mergeEditorBodyIntoOutbound,
  normalizeSettingsFromEditor,
  outboundEditorBodyFromOutbound,
  stripEmptyStreamSettingsFromRecord,
  stripSparseOutboundEnvelope,
} from '@/features/core-editor/kit/outbound-editor-json'
import { createDefaultOutbound, generateXrayOutboundFromUri, getOutboundFieldVisibility, getOutboundFormCapabilities } from '@pasarguard/xray-config-kit'
import type { Outbound, Profile } from '@pasarguard/xray-config-kit'
import type { XrayGeneratedFormField } from '@pasarguard/xray-config-kit'
import type { ColumnDef } from '@tanstack/react-table'
import { arrayMove } from '@dnd-kit/sortable'
import type { ReactElement, ReactNode } from 'react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useForm } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import useDirDetection from '@/hooks/use-dir-detection'
import { cn } from '@/lib/utils'
import { ArrowDownToLine, Cable, KeyRound, Pencil, Plus, RefreshCw, Shield, SlidersHorizontal } from 'lucide-react'
import { toast } from 'sonner'

// ─── Constants ────────────────────────────────────────────────────────────────

const proxyProtocols = ['vless', 'vmess', 'trojan', 'shadowsocks', 'socks', 'http', 'wireguard', 'hysteria', 'loopback'] as const

const K_TAG = 'tag'
const K_SEND = 'sendThrough'
const K_PROTO = 'protocolUi'
const ST_PREFIX = 'st_'

/** Kit exposes `vnext` / `servers` as JSON blobs — we flatten for editing and render this section instead. */
const SETTINGS_NESTED_ENDPOINT_KEYS = new Set(['vnext', 'servers'])

const PROXY_ENDPOINT_PROTOCOLS = new Set(['vless', 'vmess', 'trojan', 'shadowsocks'])

/** Protocols with dedicated outbound UIs — do not show generic "Stream & Security" (kit may still flag `streamSettings`). */
const OUTBOUND_NO_GENERIC_STREAM_UI = new Set<string>(['freedom', 'blackhole', 'dns'])

/** Parity manifest noise (not user-facing Xray JSON) — omit from the outbound settings grid. */
const OUTBOUND_SETTINGS_KIT_BLOCKLIST = new Set(['testseed'])

/**
 * Kit parity keys to hide in the outbound form (we render dedicated controls instead), or omit from JSON.
 * - hysteria: `version: 2` is implied by Xray.
 * - loopback: inbound tag picklist is filled from profile inbounds.
 */
const OUTBOUND_HIDDEN_SETTINGS_KEYS: Partial<Record<string, ReadonlySet<string>>> = {
  hysteria: new Set(['version']),
  loopback: new Set(['inboundTag']),
  dns: new Set(['network', 'address', 'port', 'userLevel', 'rules']),
}

function outboundHiddenSettingsKeys(protocol: string): ReadonlySet<string> | undefined {
  return OUTBOUND_HIDDEN_SETTINGS_KEYS[protocol]
}

/** Scalars edited in `OutboundProxyEndpointSection` — hide from parity grid to avoid duplicates. */
const ENDPOINT_SCALAR_KEYS_BY_PROTOCOL: Record<string, Set<string>> = {
  vless: new Set(['address', 'port', 'id', 'encryption', 'flow']),
  vmess: new Set(['address', 'port', 'id', 'alterId', 'security']),
  trojan: new Set(['address', 'port', 'password']),
  shadowsocks: new Set(['address', 'port', 'password', 'method']),
}

function filterKitSettingsKeys(protocol: string, keys: readonly string[]): string[] {
  const flatSkip = ENDPOINT_SCALAR_KEYS_BY_PROTOCOL[protocol] ?? new Set<string>()
  return keys.filter(k => !SETTINGS_NESTED_ENDPOINT_KEYS.has(k) && !flatSkip.has(k) && !OUTBOUND_SETTINGS_KIT_BLOCKLIST.has(k))
}

/** RHF defaults for the outbound detail dialog (same shape as the open/row `useEffect` reset). */
function buildOutboundDetailFormValues(row: Outbound, caps: ReturnType<typeof getOutboundFormCapabilities>): Record<string, string> {
  if (row.protocol === 'unmanaged') return {}
  const protocolUi = row.protocol === 'freedom' ? 'direct' : row.protocol === 'blackhole' ? 'block' : row.protocol
  const settingsFlat = flattenOutboundSettings(row)
  const sf = caps.settingsFields[row.protocol] ?? {}
  const order = filterKitSettingsKeys(row.protocol, caps.settingsFieldOrderByProtocol[row.protocol] ?? []).filter(k => sf[k] !== false && !outboundHiddenSettingsKeys(row.protocol)?.has(k))
  const next: Record<string, string> = {
    [K_TAG]: row.tag,
    [K_SEND]: 'sendThrough' in row ? String(row.sendThrough ?? '') : '',
    [K_PROTO]: protocolUi,
  }
  for (const k of order) {
    const def = caps.settingsFieldDefinitions[row.protocol]?.[k]
    if (!def) continue
    next[`${ST_PREFIX}${k}`] = outboundSettingToString(settingsFlat[k], def)
  }
  return next
}

/** Map raw camelCase / JSON key names to human-readable labels. */
const FIELD_LABEL_MAP: Record<string, string> = {
  // Common proxy settings
  address: 'Server Address',
  port: 'Port',
  id: 'UUID',
  uuid: 'UUID',
  alterId: 'Alter ID',
  AlterID: 'Alter ID',
  security: 'Security',
  flow: 'Flow',
  encryption: 'Encryption',
  password: 'Password',
  method: 'Cipher Method',
  email: 'Email',
  level: 'User Level',
  userLevel: 'User Level',
  auth: 'Auth',
  udp: 'UDP',
  ip: 'IP',
  network: 'Network',
  tag: 'Tag',
  // WireGuard
  secretKey: 'Secret Key',
  publicKey: 'Public Key',
  preSharedKey: 'Pre-Shared Key',
  allowedIPs: 'Allowed IPs',
  // SOCKS / HTTP
  timeout: 'Timeout (s)',
  userPass: 'Accounts',
  followRedirect: 'Follow Redirect',
  // Loopback
  inboundTag: 'Inbound Tag',
  // Mux
  enabled: 'Enabled',
  concurrency: 'Concurrency',
  xudpConcurrency: 'XUDP Concurrency',
  xudpProxyUDP443: 'UDP Port 443',
  // Stream security
  serverName: 'Server Name (SNI)',
  fingerprint: 'Fingerprint',
  allowInsecure: 'Allow Insecure',
  alpn: 'ALPN Protocols',
  shortId: 'Short ID',
  spiderX: 'SpiderX',
  // Hysteria
  up: 'Upload Capacity (Mbps)',
  down: 'Download Capacity (Mbps)',
  upMbps: 'Upload (Mbps)',
  downMbps: 'Download (Mbps)',
  obfs: 'Obfuscation',
  recv_window: 'Receive Window',
  recv_window_conn: 'Receive Window (per conn)',
  disable_mtu_discovery: 'Disable MTU Discovery',
}

function humanizeFieldName(raw: string): string {
  const mapped = FIELD_LABEL_MAP[raw]
  if (mapped) return mapped
  // Split CamelCase and lowercase-start camelCase
  return raw
    .replace(/([A-Z])/g, ' $1')
    .trim()
    .replace(/^./, s => s.toUpperCase())
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function replaceOutbound(profile: Profile, index: number, ob: Outbound): Profile {
  const list = [...(profile.outbounds ?? [])]
  list[index] = ob
  return { ...profile, outbounds: list }
}

function removeOutbound(profile: Profile, index: number): Profile {
  return { ...profile, outbounds: (profile.outbounds ?? []).filter((_: Outbound, i: number) => i !== index) }
}

function outboundSearchHaystack(ob: Outbound): string {
  return [ob.tag, ob.protocol, 'sendThrough' in ob ? String(ob.sendThrough ?? '') : ''].join(' ')
}

function cloneOutbound(ob: Outbound): Outbound {
  return JSON.parse(JSON.stringify(ob)) as Outbound
}

function getOutboundStreamSettingsRecord(ob: Outbound): Record<string, unknown> | null {
  const raw = (ob as { streamSettings?: unknown }).streamSettings
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return null
  return raw as Record<string, unknown>
}

function outboundSockoptValue(ob: Outbound): Record<string, unknown> | undefined {
  const streamSettings = getOutboundStreamSettingsRecord(ob)
  const raw = streamSettings?.sockopt
  return raw && typeof raw === 'object' && !Array.isArray(raw) ? ({ ...raw } as Record<string, unknown>) : undefined
}

function patchOutboundSockopt(ob: Outbound, patchOutbound: (next: Outbound) => void, next: Record<string, unknown> | undefined) {
  const base = { ...(ob as Record<string, unknown>) }
  const streamSettings = { ...(getOutboundStreamSettingsRecord(ob) ?? {}) }
  const pruned = next === undefined ? undefined : pruneSockoptObject(next)
  if (pruned === undefined) delete streamSettings.sockopt
  else streamSettings.sockopt = pruned

  if (Object.keys(streamSettings).length === 0) delete base.streamSettings
  else base.streamSettings = streamSettings
  patchOutbound(stripEmptyStreamSettingsFromRecord(base) as Outbound)
}

function simpleOutboundStreamSettingsForProtocolSwitch(ob: Outbound): Record<string, unknown> | undefined {
  const sockopt = pruneSockoptObject(outboundSockoptValue(ob))
  return sockopt ? { sockopt } : undefined
}

/** Merge into flattened settings, then canonicalize (`vnext` / `servers`) for storage. */
function patchOutboundWithSettingsMerge(ob: Outbound, patchOutbound: (next: Outbound) => void, mut: (flat: Record<string, unknown>) => Record<string, unknown>) {
  const flat = { ...flattenOutboundSettings(ob) }
  const merged = mut(flat)
  patchOutbound({ ...(ob as object), settings: normalizeSettingsFromEditor(ob.protocol, merged) } as Outbound)
}

type OutboundRequiredIssue = { field: string; message: string }

/** Required fields before saving an outbound (tag + protocol-specific). */
function collectOutboundRequiredIssues(ob: Outbound, t: (key: string, opts?: Record<string, unknown>) => string): OutboundRequiredIssue[] {
  const issues: OutboundRequiredIssue[] = []
  if (ob.protocol === 'unmanaged') return issues

  const tag = String(ob.tag ?? '').trim()
  if (!tag) {
    issues.push({
      field: 'tag',
      message: t('coreEditor.outbound.validation.tagRequired', {
        defaultValue: 'Enter a tag for this outbound.',
      }),
    })
  }

  const p = ob.protocol
  if (PROXY_ENDPOINT_PROTOCOLS.has(p)) {
    const s = flattenOutboundSettings(ob)
    const address = String(s.address ?? '').trim()
    const portRaw = s.port
    const portNum = typeof portRaw === 'number' ? portRaw : Number(portRaw)

    if (!address) {
      issues.push({
        field: 'address',
        message: t('coreEditor.outbound.validation.addressRequired', {
          defaultValue: 'Server address is required.',
        }),
      })
    }
    if (portRaw === undefined || portRaw === '' || !Number.isFinite(portNum) || !Number.isInteger(portNum) || portNum < 1 || portNum > 65535) {
      issues.push({
        field: 'port',
        message: t('coreEditor.outbound.validation.portInvalid', {
          defaultValue: 'Enter a valid port (1–65535).',
        }),
      })
    }

    if (p === 'vless' || p === 'vmess') {
      const id = String(s.id ?? '').trim()
      if (!id) {
        issues.push({
          field: 'id',
          message: t('coreEditor.outbound.validation.uuidRequired', {
            defaultValue: 'UUID is required.',
          }),
        })
      }
    }

    if (p === 'trojan' || p === 'shadowsocks') {
      const password = String(s.password ?? '')
      if (!password.trim()) {
        issues.push({
          field: 'password',
          message: t('coreEditor.outbound.validation.passwordRequired', {
            defaultValue: 'Password is required.',
          }),
        })
      }
    }

    if (p === 'shadowsocks') {
      const method = String(s.method ?? '').trim()
      if (!method) {
        issues.push({
          field: 'method',
          message: t('coreEditor.outbound.validation.methodRequired', {
            defaultValue: 'Cipher method is required.',
          }),
        })
      }
    }
  }

  if (p === 'wireguard') {
    const s = flattenOutboundSettings(ob)
    const sk = String(s.secretKey ?? '').trim()
    if (!sk) {
      issues.push({
        field: 'secretKey',
        message: t('coreEditor.outbound.validation.wireguardSecretRequired', {
          defaultValue: 'WireGuard secret key is required.',
        }),
      })
    }
  }

  if (p === 'loopback') {
    const s = (ob as { settings?: Record<string, unknown> }).settings ?? {}
    const inboundTag = String(s.inboundTag ?? '').trim()
    if (!inboundTag) {
      issues.push({
        field: 'inboundTag',
        message: t('coreEditor.outbound.validation.inboundTagRequired', {
          defaultValue: 'Inbound tag is required for loopback.',
        }),
      })
    }
  }

  return issues
}

function applyOutboundValidationIssuesToForm(issues: OutboundRequiredIssue[], form: ReturnType<typeof useForm<Record<string, string>>>, t: (key: string, opts?: Record<string, unknown>) => string) {
  form.clearErrors(K_TAG)
  const tagIssue = issues.find(i => i.field === 'tag')
  if (tagIssue) {
    form.setError(K_TAG, { type: 'validate', message: tagIssue.message })
  }
  const rest = issues.filter(i => i.field !== 'tag')
  if (rest.length > 0) {
    toast.error(t('coreEditor.outbound.validation.requiredFieldsTitle', { defaultValue: 'Required fields missing' }), { description: rest.map(i => i.message).join('\n') })
  } else if (tagIssue) {
    /* tag-only: FormMessage on tag is enough */
  }
}

// Small helper for labels outside <FormField> (stream + endpoint sections).
function FieldRow({ label, children, wide }: { label: string; children: ReactNode; wide?: boolean }) {
  return (
    <div className={cn('flex w-full min-w-0 flex-col gap-2.5', wide && 'sm:col-span-2')}>
      <Label className="text-xs font-medium">{label}</Label>
      <div className="w-full min-w-0">{children}</div>
    </div>
  )
}

// ─── Types ────────────────────────────────────────────────────────────────────

type DialogMode = 'add' | 'edit'
type OutboundDialogTab = 'form' | 'json'

interface XrayOutboundsSectionProps {
  headerAddPulse?: SectionHeaderAddPulse
  headerAddEpoch?: number
}

// ─── Component ────────────────────────────────────────────────────────────────

export function XrayOutboundsSection({ headerAddPulse, headerAddEpoch }: XrayOutboundsSectionProps) {
  const { t } = useTranslation()
  const dir = useDirDetection()
  const profile = useCoreEditorStore(s => s.xrayProfile)
  const updateXrayProfile = useCoreEditorStore(s => s.updateXrayProfile)
  const { assertNoPersistBlockingErrors } = useXrayPersistModifyGuard()

  const [selected, setSelected] = useState(0)
  const [detailOpen, setDetailOpen] = useState(false)
  const [dialogMode, setDialogMode] = useState<DialogMode>('edit')
  const [draftOutbound, setDraftOutbound] = useState<Outbound | null>(null)
  const [editOriginalOutbound, setEditOriginalOutbound] = useState<Outbound | null>(null)
  const [discardDraftOpen, setDiscardDraftOpen] = useState(false)
  const [discardEditOpen, setDiscardEditOpen] = useState(false)
  const [blockAddWhileDraftOpen, setBlockAddWhileDraftOpen] = useState(false)
  const [outboundDialogTab, setOutboundDialogTab] = useState<OutboundDialogTab>('form')
  const [outboundJsonText, setOutboundJsonText] = useState('')
  const [uriDraft, setUriDraft] = useState('')
  /** Bumps when outbound settings shape changes without row identity changing (edit: protocol switch, URI import). */
  const [settingsFormSeed, setSettingsFormSeed] = useState(0)

  const outbounds = profile?.outbounds ?? []

  const ob = useMemo(() => {
    if (!profile) return undefined
    if (dialogMode === 'add' && draftOutbound) return draftOutbound
    return outbounds[selected]
  }, [profile, dialogMode, draftOutbound, outbounds, selected])

  const outboundCaps = useMemo(() => getOutboundFormCapabilities(), [])
  const outboundCapsRef = useRef(outboundCaps)
  outboundCapsRef.current = outboundCaps

  const visibility = useMemo(() => (ob ? getOutboundFieldVisibility(ob, outboundCaps) : null), [ob, outboundCaps])

  const showOutboundStreamSettingsAccordion = useMemo(
    () => Boolean(visibility?.streamSettings) && !!ob && ob.protocol !== 'unmanaged' && !OUTBOUND_NO_GENERIC_STREAM_UI.has(ob.protocol),
    [ob, visibility?.streamSettings],
  )

  const showStandaloneOutboundSockoptAccordion = useMemo(
    () => Boolean(visibility?.streamSettings) && !!ob && ob.protocol !== 'unmanaged' && OUTBOUND_NO_GENERIC_STREAM_UI.has(ob.protocol),
    [ob, visibility?.streamSettings],
  )

  const showOutboundStackedAccordions = useMemo(
    () => !!ob && ob.protocol !== 'unmanaged' && (showOutboundStreamSettingsAccordion || showStandaloneOutboundSockoptAccordion || 'mux' in ob || 'proxySettings' in ob),
    [ob, showOutboundStreamSettingsAccordion, showStandaloneOutboundSockoptAccordion],
  )

  const form = useForm<Record<string, string>>({})

  const profileRef = useRef(profile)
  profileRef.current = profile

  // ─── Settings field order (booleans last) ──────────────────────────────────

  const settingsOrder = useMemo(() => {
    if (!ob || ob.protocol === 'unmanaged') return []
    const flags = outboundCaps.settingsFields[ob.protocol] ?? {}
    const order = filterKitSettingsKeys(ob.protocol, outboundCaps.settingsFieldOrderByProtocol[ob.protocol] ?? []).filter(k => flags[k] !== false && !outboundHiddenSettingsKeys(ob.protocol)?.has(k))
    const defs = outboundCaps.settingsFieldDefinitions[ob.protocol]
    if (!defs) return order
    return [...order].sort((a, b) => {
      const defA = defs[a]
      const defB = defs[b]
      const isBoolA = defA ? isBooleanParityField(defA) : false
      const isBoolB = defB ? isBooleanParityField(defB) : false
      if (isBoolA && !isBoolB) return 1
      if (!isBoolA && isBoolB) return -1
      return 0
    })
  }, [ob, outboundCaps])

  const obStreamSettings = useMemo(() => (ob ? getOutboundStreamSettingsRecord(ob) : null), [ob])

  // ─── Form reset on open / row change ───────────────────────────────────────

  useEffect(() => {
    if (!detailOpen) return
    const p = profileRef.current
    if (!p) return
    const row = dialogMode === 'add' && draftOutbound ? draftOutbound : p.outbounds?.[selected]
    if (!row || row.protocol === 'unmanaged') return
    form.reset(buildOutboundDetailFormValues(row as Outbound, outboundCapsRef.current))
  }, [detailOpen, selected, dialogMode, draftOutbound, settingsFormSeed, form])

  // ─── Table columns ─────────────────────────────────────────────────────────

  const columns = useMemo<ColumnDef<Outbound, unknown>[]>(
    () => [
      {
        id: 'index',
        header: '#',
        cell: ({ row }) => row.index + 1,
      },
      {
        accessorKey: 'tag',
        header: () => t('coreEditor.col.tag', { defaultValue: 'Tag' }),
        cell: ({ row }) => <span className="text-xs">{row.original.tag}</span>,
      },
      {
        accessorKey: 'protocol',
        header: () => t('coreEditor.col.protocol', { defaultValue: 'Protocol' }),
        cell: ({ row }) => row.original.protocol,
      },
    ],
    [t],
  )

  // ─── Add / open ────────────────────────────────────────────────────────────

  const beginAddOutbound = useCallback(() => {
    if (!profile) return
    if (detailOpen && dialogMode === 'add' && draftOutbound !== null) {
      setBlockAddWhileDraftOpen(true)
      return
    }
    const created = stripSparseOutboundEnvelope(createDefaultOutbound({ protocol: 'vless', tag: '' }) as Record<string, unknown>) as Outbound
    setDraftOutbound(created)
    setDialogMode('add')
    setOutboundDialogTab('form')
    setUriDraft('')
    setOutboundJsonText('')
    setDetailOpen(true)
  }, [profile, detailOpen, dialogMode, draftOutbound])

  useSectionHeaderAddPulseEffect(headerAddPulse, headerAddEpoch, 'outbounds', beginAddOutbound)

  if (!profile) return null

  // ─── State helpers ─────────────────────────────────────────────────────────

  const finalizeDetailClose = () => {
    setOutboundDialogTab('form')
    setOutboundJsonText('')
    setUriDraft('')
    setDetailOpen(false)
    setDialogMode('edit')
    setDraftOutbound(null)
    setEditOriginalOutbound(null)
  }

  const patchOutbound = (next: Outbound) => {
    if (dialogMode === 'add' && draftOutbound !== null) {
      setDraftOutbound(next)
      return
    }
    updateXrayProfile(p => replaceOutbound(p, selected, next))
  }

  const isTagDuplicate = (candidateRaw: string): boolean => {
    return profileTagHasDuplicateUsage(profile, candidateRaw, dialogMode === 'edit' ? { owner: 'outbound', index: selected } : undefined)
  }

  const setDuplicateTagError = (tagValue: string) => {
    form.setError(K_TAG, {
      type: 'validate',
      message: profileDuplicateTagMessage(t, tagValue),
    })
  }

  // ─── JSON tab helpers ──────────────────────────────────────────────────────

  const flushOutboundJsonOrToast = (): boolean => {
    if (outboundDialogTab !== 'json') return true
    if (!ob || ob.protocol === 'unmanaged') return true
    try {
      const parsed = JSON.parse(outboundJsonText) as Record<string, unknown>
      patchOutbound(mergeEditorBodyIntoOutbound(ob, parsed))
      return true
    } catch {
      toast.error(t('coreEditor.outbound.jsonInvalid', { defaultValue: 'Fix JSON errors before leaving the JSON tab.' }))
      return false
    }
  }

  // ─── Open / close ─────────────────────────────────────────────────────────

  const handleDetailOpenChange = (open: boolean) => {
    if (open) {
      setOutboundDialogTab('form')
      setUriDraft('')
      setOutboundJsonText('')
      setDetailOpen(true)
      return
    }
    if (ob && ob.protocol !== 'unmanaged' && outboundDialogTab === 'json') {
      try {
        patchOutbound(mergeEditorBodyIntoOutbound(ob, JSON.parse(outboundJsonText) as Record<string, unknown>))
      } catch {
        /* allow close; unsaved JSON may be lost */
      }
    }
    if (dialogMode === 'add' && draftOutbound !== null) {
      setDiscardDraftOpen(true)
      return
    }
    if (dialogMode === 'edit' && ob && ob.protocol !== 'unmanaged' && editOriginalOutbound && JSON.stringify(ob) !== JSON.stringify(editOriginalOutbound)) {
      setDiscardEditOpen(true)
      return
    }
    finalizeDetailClose()
  }

  // ─── URI import ────────────────────────────────────────────────────────────

  const handleUriImport = () => {
    const raw = uriDraft.trim()
    if (!raw || !ob || ob.protocol === 'unmanaged') return
    try {
      const imported = generateXrayOutboundFromUri(raw) as Outbound
      const merged = { ...(ob as object), ...(imported as object) } as Outbound
      const normalized = stripSparseOutboundEnvelope({
        ...merged,
        settings: normalizeSettingsFromEditor(merged.protocol, flattenOutboundSettings(merged)),
      } as Record<string, unknown>) as Outbound
      patchOutbound(normalized)
      setOutboundJsonText(JSON.stringify(outboundEditorBodyFromOutbound(normalized), null, 2))
      setSettingsFormSeed(s => s + 1)
      form.reset(buildOutboundDetailFormValues(normalized, outboundCapsRef.current))
      setUriDraft('')
      toast.success(t('success', { defaultValue: 'Success' }))
    } catch (e) {
      toast.error(t('coreEditor.outbound.uriImportFailed', { defaultValue: 'Could not parse that share link.' }), {
        description: e instanceof Error ? e.message : undefined,
      })
    }
  }

  // ─── Commit add ────────────────────────────────────────────────────────────

  const commitAddOutbound = () => {
    if (!draftOutbound || draftOutbound.protocol === 'unmanaged') return
    if (!assertNoPersistBlockingErrors()) return
    const tagTrim = (form.getValues(K_TAG) ?? '').trim()

    let row: Outbound = draftOutbound
    if (outboundDialogTab === 'json') {
      try {
        row = mergeEditorBodyIntoOutbound(draftOutbound, JSON.parse(outboundJsonText) as Record<string, unknown>)
      } catch {
        toast.error(t('coreEditor.outbound.jsonInvalid', { defaultValue: 'Fix JSON errors before leaving the JSON tab.' }))
        return
      }
    }
    row = stripEmptyStreamSettingsFromRecord({
      ...row,
      tag: tagTrim,
      settings: normalizeSettingsFromEditor(row.protocol, flattenOutboundSettings(row)),
    } as Record<string, unknown>) as Outbound

    const issues = collectOutboundRequiredIssues(row, t)
    if (issues.length > 0) {
      applyOutboundValidationIssuesToForm(issues, form, t)
      return
    }
    if (isTagDuplicate(tagTrim)) {
      setDuplicateTagError(tagTrim)
      return
    }

    const insertAt = outbounds.length
    updateXrayProfile(p => ({ ...p, outbounds: [...(p.outbounds ?? []), row] }))
    setSelected(insertAt)
    finalizeDetailClose()
  }

  // ─── Commit edit ───────────────────────────────────────────────────────────

  const commitEditOutbound = () => {
    if (dialogMode !== 'edit' || !ob) return
    const tagTrim = (form.getValues(K_TAG) ?? '').trim()

    let toValidate: Outbound
    if (outboundDialogTab === 'json') {
      try {
        toValidate = stripEmptyStreamSettingsFromRecord(mergeEditorBodyIntoOutbound(ob, JSON.parse(outboundJsonText) as Record<string, unknown>) as Record<string, unknown>) as Outbound
      } catch {
        toast.error(t('coreEditor.outbound.jsonInvalid', { defaultValue: 'Fix JSON errors before leaving the JSON tab.' }))
        return
      }
    } else {
      toValidate = stripEmptyStreamSettingsFromRecord({
        ...ob,
        tag: tagTrim,
        settings: normalizeSettingsFromEditor(ob.protocol, flattenOutboundSettings(ob)),
      } as Record<string, unknown>) as Outbound
    }

    const issues = collectOutboundRequiredIssues(toValidate, t)
    if (issues.length > 0) {
      applyOutboundValidationIssuesToForm(issues, form, t)
      return
    }
    if (isTagDuplicate(tagTrim)) {
      setDuplicateTagError(tagTrim)
      return
    }

    updateXrayProfile(p => replaceOutbound(p, selected, toValidate))
    finalizeDetailClose()
  }

  // ─── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="space-y-6">
      <CoreEditorDataTable
        columns={columns}
        data={outbounds}
        getSearchableText={outboundSearchHaystack}
        getRowId={(_row: Outbound, i: number) => String(i)}
        minRowCount={1}
        minRowCountMessage={t('coreEditor.outbound.keepAtLeastOne', {
          defaultValue: 'At least one outbound is required.',
        })}
        onRowClick={(_row, rowIndex) => {
          if (detailOpen && dialogMode === 'add' && draftOutbound !== null) {
            setBlockAddWhileDraftOpen(true)
            return
          }
          setDraftOutbound(null)
          setDialogMode('edit')
          setEditOriginalOutbound(cloneOutbound(outbounds[rowIndex]))
          setSelected(rowIndex)
          setOutboundDialogTab('form')
          setUriDraft('')
          setOutboundJsonText('')
          setDetailOpen(true)
        }}
        onRemoveRow={i => {
          updateXrayProfile(p => removeOutbound(p, i))
          setSelected(0)
        }}
        onBulkRemove={indices => {
          const rm = new Set(indices)
          updateXrayProfile(p => ({
            ...p,
            outbounds: (p.outbounds ?? []).filter((_, idx) => !rm.has(idx)),
          }))
          setSelected(0)
        }}
        enableReorder
        onReorder={(from, to) => {
          updateXrayProfile(p => ({ ...p, outbounds: arrayMove(p.outbounds ?? [], from, to) }))
          setSelected(sel => remapIndexAfterArrayMove(sel, from, to))
        }}
      />

      <CoreEditorFormDialog
        isDialogOpen={detailOpen}
        onOpenChange={handleDetailOpenChange}
        leadingIcon={dialogMode === 'add' ? <Plus className="h-5 w-5 shrink-0" /> : <Pencil className="h-5 w-5 shrink-0" />}
        title={dialogMode === 'add' ? t('coreEditor.outbound.dialogTitleAdd', { defaultValue: 'Add outbound' }) : t('coreEditor.outbound.dialogTitleEdit', { defaultValue: 'Edit outbound' })}
        size="md"
        footerExtra={
          dialogMode === 'add' && draftOutbound ? (
            <Button type="button" className="sm:min-w-[88px]" onClick={commitAddOutbound}>
              {t('coreEditor.outbound.addToList', { defaultValue: 'Add to list' })}
            </Button>
          ) : ob?.protocol !== 'unmanaged' && dialogMode === 'edit' ? (
            <Button type="button" className="sm:min-w-[88px]" onClick={commitEditOutbound}>
              {t('modify')}
            </Button>
          ) : undefined
        }
      >
        {ob?.protocol === 'unmanaged' && (
          <p className="text-muted-foreground text-sm">{t('coreEditor.outbound.unmanagedHint', { defaultValue: 'This outbound is managed as raw JSON in Advanced.' })}</p>
        )}

        {ob && ob.protocol !== 'unmanaged' && (
          <Tabs
            dir={dir}
            value={outboundDialogTab}
            onValueChange={v => {
              const next = v as OutboundDialogTab
              if (next === 'form' && outboundDialogTab === 'json') {
                if (!flushOutboundJsonOrToast()) return
              }
              if (next === 'json') {
                setOutboundJsonText(JSON.stringify(outboundEditorBodyFromOutbound(ob), null, 2))
              }
              setOutboundDialogTab(next)
            }}
            className="w-full space-y-4"
          >
            {/* URI import bar */}
            <div className="space-y-1.5">
              <p className="text-muted-foreground text-xs font-medium">{t('coreEditor.outbound.linkLabel', { defaultValue: 'Import from share link' })}</p>
              <div className={cn('flex items-center gap-2', dir === 'rtl' && 'flex-row-reverse')}>
                <Input
                  value={uriDraft}
                  onChange={e => setUriDraft(e.target.value)}
                  placeholder={t('coreEditor.outbound.linkPlaceholder', {
                    defaultValue: 'vmess:// vless:// trojan:// ss:// hysteria2:// ...',
                  })}
                  className="text-xs"
                  dir="ltr"
                  onKeyDown={e => {
                    if (e.key === 'Enter') {
                      e.preventDefault()
                      handleUriImport()
                    }
                  }}
                />
                <Button
                  type="button"
                  variant="secondary"
                  size="icon"
                  className="shrink-0"
                  onClick={handleUriImport}
                  aria-label={t('coreEditor.outbound.linkImportApply', { defaultValue: 'Apply share link' })}
                >
                  <ArrowDownToLine className="h-4 w-4" />
                </Button>
              </div>
            </div>

            <TabsList className="mx-auto grid h-11 w-full max-w-xs grid-cols-2 gap-1 p-1">
              <TabsTrigger value="form" className="h-9 rounded-sm px-4 py-1 text-xs">
                {t('coreEditor.outbound.tabForm', { defaultValue: 'Form' })}
              </TabsTrigger>
              <TabsTrigger value="json" className="h-9 rounded-sm px-4 py-1 text-xs">
                {t('coreEditor.outbound.tabJson', { defaultValue: 'Advanced' })}
              </TabsTrigger>
            </TabsList>

            {/* Only mount the active panel (unlike Radix TabsContent, which keeps inactive panels in the tree). */}
            {outboundDialogTab === 'form' ? (
              <div
                key={`outbound-form-panel-${ob.protocol}-${settingsFormSeed}`}
                className="ring-offset-background focus-visible:ring-ring mt-2 pb-1 focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:outline-none"
              >
                <Form {...form}>
                  <form className="flex flex-col gap-4" onSubmit={e => e.preventDefault()}>
                    {/* ── Identity: Tag + Protocol ────────────────────────── */}
                    <div className="grid gap-4 sm:grid-cols-2">
                      <FormField
                        control={form.control}
                        name={K_TAG}
                        render={({ field, fieldState }) => (
                          <FormItem>
                            <FormLabel>{t('coreEditor.field.tag', { defaultValue: 'Tag' })}</FormLabel>
                            <FormControl>
                              <Input
                                {...field}
                                className="h-10"
                                isError={!!fieldState.error}
                                onChange={e => {
                                  const v = e.target.value
                                  field.onChange(v)
                                  if (isTagDuplicate(v)) {
                                    setDuplicateTagError(v)
                                    return
                                  }
                                  form.clearErrors(K_TAG)
                                  patchOutbound({ ...ob, tag: v } as Outbound)
                                }}
                              />
                            </FormControl>
                            <FormMessage />
                          </FormItem>
                        )}
                      />

                      <FormField
                        control={form.control}
                        name={K_PROTO}
                        render={({ field }) => (
                          <FormItem>
                            <FormLabel>{t('coreEditor.field.protocol', { defaultValue: 'Protocol' })}</FormLabel>
                            <Select
                              dir="ltr"
                              value={field.value}
                              onValueChange={v => {
                                field.onChange(v)
                                const protocol = v === 'direct' ? 'freedom' : v === 'block' ? 'blackhole' : (v as 'dns' | (typeof proxyProtocols)[number])
                                const isSimpleEnvelope = protocol === 'freedom' || protocol === 'blackhole' || protocol === 'dns'
                                const created = stripSparseOutboundEnvelope(
                                  createDefaultOutbound({
                                    protocol: protocol as 'freedom' | 'blackhole' | 'dns' | (typeof proxyProtocols)[number],
                                    tag: ob.tag,
                                    sendThrough: 'sendThrough' in ob ? ob.sendThrough : undefined,
                                    streamSettings: isSimpleEnvelope ? simpleOutboundStreamSettingsForProtocolSwitch(ob) : 'streamSettings' in ob ? ob.streamSettings : undefined,
                                    ...(!isSimpleEnvelope
                                      ? {
                                          mux: 'mux' in ob ? ob.mux : undefined,
                                          proxySettings: 'proxySettings' in ob ? ob.proxySettings : undefined,
                                        }
                                      : {}),
                                  }) as Record<string, unknown>,
                                ) as Outbound
                                patchOutbound(created)
                                setSettingsFormSeed(s => s + 1)
                                form.reset(buildOutboundDetailFormValues(created, outboundCapsRef.current))
                              }}
                            >
                              <FormControl>
                                <SelectTrigger className="h-10 w-full min-w-0" dir="ltr">
                                  <SelectValue />
                                </SelectTrigger>
                              </FormControl>
                              <SelectContent dir="ltr">
                                <SelectItem value="direct">Freedom — direct</SelectItem>
                                <SelectItem value="block">Blackhole — block</SelectItem>
                                <SelectItem value="dns">DNS</SelectItem>
                                {proxyProtocols.map(p => (
                                  <SelectItem key={p} value={p}>
                                    {p}
                                  </SelectItem>
                                ))}
                              </SelectContent>
                            </Select>
                            <FormMessage />
                          </FormItem>
                        )}
                      />

                      {'sendThrough' in ob && (
                        <FormField
                          control={form.control}
                          name={K_SEND}
                          render={({ field }) => (
                            <FormItem className="sm:col-span-2">
                              <FormLabel>{t('coreEditor.field.sendThrough', { defaultValue: 'Send Through (local IP)' })}</FormLabel>
                              <FormControl>
                                <Input
                                  {...field}
                                  dir="ltr"
                                  className="h-10"
                                  placeholder="0.0.0.0"
                                  onChange={e => {
                                    const v = e.target.value
                                    field.onChange(v)
                                    patchOutbound({ ...ob, sendThrough: v || undefined } as Outbound)
                                  }}
                                />
                              </FormControl>
                              <FormMessage />
                            </FormItem>
                          )}
                        />
                      )}
                    </div>

                    <OutboundSpecialProtocolSettings ob={ob} patchOutbound={patchOutbound} t={t} />

                    {/* ── Server / endpoint (replaces raw `vnext` / `servers` JSON) ── */}
                    {PROXY_ENDPOINT_PROTOCOLS.has(ob.protocol) && <OutboundProxyEndpointSection ob={ob} patchOutbound={patchOutbound} t={t} />}

                    {/* ── Protocol-specific settings ──────────────────────── */}
                    {visibility?.settings && ob.protocol !== 'freedom' && ob.protocol !== 'blackhole' && ob.protocol !== 'dns' && settingsOrder.length > 0 && (
                      <ProtocolSettingsGrid ob={ob} settingsOrder={settingsOrder} outboundCaps={outboundCaps} form={form} patchOutbound={patchOutbound} />
                    )}

                    {/* ── Stream + mux + chain proxy: stacked accordions (stream hidden for freedom/blackhole/dns — dedicated UIs) ── */}
                    {showOutboundStackedAccordions && (
                      <Accordion type="multiple" className="!mt-0 mb-4 flex w-full flex-col gap-y-3">
                        {showOutboundStreamSettingsAccordion && (
                          <OutboundStreamSettingsAccordion
                            ob={ob}
                            obStreamSettings={obStreamSettings}
                            form={form}
                            patchOutbound={patchOutbound}
                            t={t}
                            dialerProxyTagOptions={outbounds.map(o => o.tag).filter((tag): tag is string => typeof tag === 'string' && tag !== ob.tag)}
                          />
                        )}
                        {showStandaloneOutboundSockoptAccordion && (
                          <OutboundSockoptAccordion
                            ob={ob}
                            patchOutbound={patchOutbound}
                            t={t}
                            dialerProxyTagOptions={outbounds.map(o => o.tag).filter((tag): tag is string => typeof tag === 'string' && tag !== ob.tag)}
                          />
                        )}
                        <OutboundAdvancedAccordion ob={ob} patchOutbound={patchOutbound} t={t} />
                      </Accordion>
                    )}
                  </form>
                </Form>
              </div>
            ) : (
              <div key="outbound-json-panel" className="ring-offset-background focus-visible:ring-ring mt-2 pb-1 focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:outline-none">
                <JsonCodeEditorPanel value={outboundJsonText} onChange={setOutboundJsonText} dialogOpen={detailOpen} />
              </div>
            )}
          </Tabs>
        )}
      </CoreEditorFormDialog>

      {/* ── Discard draft ──────────────────────────────────────────────── */}
      <AlertDialog open={discardDraftOpen} onOpenChange={setDiscardDraftOpen}>
        <AlertDialogContent dir={dir}>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('coreEditor.outbound.discardDraftTitle', { defaultValue: 'Discard new outbound?' })}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('coreEditor.outbound.discardDraftDescription', {
                defaultValue: 'This outbound is not in the list yet. Closing without adding will discard your changes.',
              })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('cancel')}</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                setDiscardDraftOpen(false)
                finalizeDetailClose()
              }}
            >
              {t('coreEditor.outbound.discardDraftAction', { defaultValue: 'Discard' })}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* ── Discard unsaved edits ──────────────────────────────────────── */}
      <AlertDialog open={discardEditOpen} onOpenChange={setDiscardEditOpen}>
        <AlertDialogContent dir={dir}>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('coreEditor.outbound.discardEditTitle', { defaultValue: 'Discard changes?' })}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('coreEditor.outbound.discardEditDescription', {
                defaultValue: 'Your modifications to this outbound will be lost if you close now.',
              })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('cancel')}</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                if (dialogMode === 'edit' && editOriginalOutbound) {
                  updateXrayProfile(p => replaceOutbound(p, selected, editOriginalOutbound))
                }
                setDiscardEditOpen(false)
                finalizeDetailClose()
              }}
            >
              {t('coreEditor.outbound.discardDraftAction', { defaultValue: 'Discard' })}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* ── Block while draft open ─────────────────────────────────────── */}
      <AlertDialog open={blockAddWhileDraftOpen} onOpenChange={setBlockAddWhileDraftOpen}>
        <AlertDialogContent dir={dir}>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('coreEditor.outbound.finishCurrentTitle', { defaultValue: 'Finish the current outbound first' })}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('coreEditor.outbound.finishCurrentDescription', {
                defaultValue: 'Add it to the list, or close the dialog and discard the draft, before starting another outbound.',
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

// ─── Proxy endpoint (vnext / servers as form fields) ─────────────────────────

interface OutboundProxyEndpointSectionProps {
  ob: Outbound
  patchOutbound: (next: Outbound) => void
  t: (key: string, opts?: Record<string, unknown>) => string
}

const VLESS_FLOW_OPTIONS = ['xtls-rprx-vision', 'xtls-rprx-vision-udp443'] as const

const VMESS_SECURITY_OPTIONS = ['auto', 'aes-128-gcm', 'chacha20-poly1305', 'none', 'zero'] as const

function outboundStreamNetworkSelectLabel(net: string): string {
  switch (net) {
    case 'tcp':
      return 'TCP'
    case 'kcp':
      return 'mKCP'
    case 'ws':
      return 'WebSocket (ws)'
    case 'h2':
      return 'HTTP/2 (h2)'
    case 'grpc':
      return 'gRPC'
    case 'xhttp':
      return 'XHTTP'
    case 'splithttp':
      return 'SplitHTTP'
    default:
      return net
  }
}

/** Radix Select requires `value` to match an item; omit/blank/unknown stream `security` must map to `none`. */
function normalizeOutboundStreamSecurity(raw: unknown): 'none' | 'tls' | 'reality' {
  const s = typeof raw === 'string' ? raw.trim().toLowerCase() : ''
  if (s === 'tls' || s === 'reality' || s === 'none') return s
  return 'none'
}

function OutboundProxyEndpointSection({ ob, patchOutbound, t }: OutboundProxyEndpointSectionProps) {
  const p = ob.protocol
  if (!PROXY_ENDPOINT_PROTOCOLS.has(p)) return null

  const flat = flattenOutboundSettings(ob)
  const streamRec = getOutboundStreamSettingsRecord(ob)
  const streamSecForFlow = normalizeOutboundStreamSecurity(streamRec?.security)
  const vlessVisionFlowsOk = outboundVlessVisionFlowAllowed(streamSecForFlow)
  const flowStr = String(flat.flow ?? '').trim()

  useEffect(() => {
    if (p !== 'vless') return
    if (!vlessVisionFlowIncompatibleWithStreamSecurity(streamSecForFlow, flowStr)) return
    patchOutboundWithSettingsMerge(ob, patchOutbound, s => ({ ...s, flow: '' }))
  }, [p, ob, flowStr, streamSecForFlow, patchOutbound])
  const address = String(flat.address ?? '')
  const portStr = flat.port != null && flat.port !== '' ? String(flat.port) : ''
  const id = String(flat.id ?? '')
  const password = String(flat.password ?? '')
  const method = String(flat.method ?? 'aes-256-gcm')
  const encryption = String(flat.encryption ?? 'none')
  const flow = typeof flat.flow === 'string' ? flat.flow : ''
  const alterIdStr = flat.alterId != null && flat.alterId !== '' ? String(flat.alterId) : '0'
  const security = typeof flat.security === 'string' && flat.security ? flat.security : 'auto'

  return (
    <div className="rounded-md border p-4">
      <p className="mb-4 text-sm font-medium">{t('coreEditor.outbound.endpointSection', { defaultValue: 'Remote server' })}</p>
      <div className="grid gap-4 sm:grid-cols-2">
        <FieldRow label={t('coreEditor.field.serverAddress', { defaultValue: 'Address' })}>
          <Input
            key={`a-${address}`}
            dir="ltr"
            className="h-10 text-sm"
            placeholder="example.com"
            defaultValue={address}
            onBlur={e => {
              const v = e.target.value.trim()
              patchOutboundWithSettingsMerge(ob, patchOutbound, s => ({ ...s, address: v || undefined }))
            }}
          />
        </FieldRow>
        <FieldRow label={t('coreEditor.field.port', { defaultValue: 'Port' })}>
          <Input
            key={`p-${portStr}`}
            type="number"
            dir="ltr"
            inputMode="numeric"
            className="h-10 text-sm"
            placeholder="443"
            defaultValue={portStr}
            onBlur={e => {
              const v = e.target.value.trim()
              const n = Number(v)
              patchOutboundWithSettingsMerge(ob, patchOutbound, s => ({
                ...s,
                port: v === '' ? undefined : Number.isFinite(n) ? n : s.port,
              }))
            }}
          />
        </FieldRow>

        {p === 'vless' && (
          <>
            <FieldRow label={t('coreEditor.field.uuid', { defaultValue: 'UUID' })} wide>
              <Input
                key={`id-${id}`}
                dir="ltr"
                className="h-10 text-sm"
                placeholder="00000000-0000-0000-0000-000000000000"
                defaultValue={id}
                onBlur={e => {
                  const v = e.target.value.trim()
                  patchOutboundWithSettingsMerge(ob, patchOutbound, s => ({ ...s, id: v || undefined }))
                }}
              />
            </FieldRow>
            <FieldRow label={t('coreEditor.field.encryption', { defaultValue: 'Encryption' })} wide>
              <Input
                key={`enc-${encryption}`}
                dir="ltr"
                className="h-10 w-full min-w-0 text-xs"
                placeholder="none"
                defaultValue={encryption}
                onBlur={e => {
                  const v = e.target.value.trim() === '' ? 'none' : e.target.value
                  patchOutboundWithSettingsMerge(ob, patchOutbound, s => ({ ...s, encryption: v }))
                }}
              />
            </FieldRow>
            <FieldRow label={t('coreEditor.field.flow', { defaultValue: 'Flow' })} wide>
              <Select
                dir="ltr"
                value={vlessVisionFlowsOk || !(VLESS_FLOW_OPTIONS as readonly string[]).includes(flow) ? flow || '__none' : '__none'}
                onValueChange={v =>
                  patchOutboundWithSettingsMerge(ob, patchOutbound, s => ({
                    ...s,
                    flow: v === '__none' ? '' : v,
                  }))
                }
              >
                <SelectTrigger className="mb-2 h-10 w-full min-w-0" dir="ltr">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent dir="ltr">
                  <SelectItem value="__none">{t('coreEditor.outbound.flowDefault', { defaultValue: 'Default (none)' })}</SelectItem>
                  {vlessVisionFlowsOk
                    ? VLESS_FLOW_OPTIONS.map(f => (
                        <SelectItem key={f} value={f}>
                          {f}
                        </SelectItem>
                      ))
                    : null}
                </SelectContent>
              </Select>
              {!vlessVisionFlowsOk ? (
                <p className="text-muted-foreground text-xs">
                  {t('coreEditor.outbound.flowVisionRequiresTls', {
                    defaultValue: 'Vision flows require stream security TLS or REALITY (not “none”).',
                  })}
                </p>
              ) : null}
            </FieldRow>
          </>
        )}

        {p === 'vmess' && (
          <>
            <FieldRow label={t('coreEditor.field.uuid', { defaultValue: 'UUID' })} wide>
              <Input
                key={`vid-${id}`}
                dir="ltr"
                className="h-10 text-sm"
                placeholder="00000000-0000-0000-0000-000000000000"
                defaultValue={id}
                onBlur={e => {
                  const v = e.target.value.trim()
                  patchOutboundWithSettingsMerge(ob, patchOutbound, s => ({ ...s, id: v || undefined }))
                }}
              />
            </FieldRow>
            <FieldRow label={t('coreEditor.field.alterId', { defaultValue: 'Alter ID' })}>
              <Input
                key={`alt-${alterIdStr}`}
                type="number"
                dir="ltr"
                inputMode="numeric"
                className="h-10 text-sm"
                defaultValue={alterIdStr}
                onBlur={e => {
                  const v = e.target.value.trim()
                  const n = Number(v)
                  patchOutboundWithSettingsMerge(ob, patchOutbound, s => ({
                    ...s,
                    alterId: v === '' ? 0 : Number.isFinite(n) ? n : s.alterId,
                  }))
                }}
              />
            </FieldRow>
            <FieldRow label={t('coreEditor.field.security', { defaultValue: 'Security' })} wide>
              <Select
                dir="ltr"
                value={VMESS_SECURITY_OPTIONS.includes(security as (typeof VMESS_SECURITY_OPTIONS)[number]) ? security : 'auto'}
                onValueChange={v => patchOutboundWithSettingsMerge(ob, patchOutbound, s => ({ ...s, security: v }))}
              >
                <SelectTrigger className="h-10 w-full min-w-0" dir="ltr">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent dir="ltr">
                  {VMESS_SECURITY_OPTIONS.map(sv => (
                    <SelectItem key={sv} value={sv}>
                      {sv}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </FieldRow>
          </>
        )}

        {(p === 'trojan' || p === 'shadowsocks') && (
          <>
            {p === 'shadowsocks' && (
              <FieldRow label={t('coreEditor.field.method', { defaultValue: 'Method' })}>
                <Input
                  key={`m-${method}`}
                  dir="ltr"
                  className="h-10 text-sm"
                  placeholder="aes-256-gcm"
                  defaultValue={method}
                  onBlur={e => {
                    const v = e.target.value.trim()
                    patchOutboundWithSettingsMerge(ob, patchOutbound, s => ({ ...s, method: v || undefined }))
                  }}
                />
              </FieldRow>
            )}
            <FieldRow label={t('coreEditor.field.password', { defaultValue: 'Password' })} wide={p === 'trojan'}>
              <Input
                key={`pw-${password}`}
                dir="ltr"
                type="password"
                autoComplete="new-password"
                className="h-10 text-sm"
                defaultValue={password}
                onBlur={e => {
                  const v = e.target.value
                  patchOutboundWithSettingsMerge(ob, patchOutbound, s => ({ ...s, password: v || undefined }))
                }}
              />
            </FieldRow>
          </>
        )}
      </div>
    </div>
  )
}

// ─── Protocol Settings Grid ────────────────────────────────────────────────────
// Renders the dynamic per-protocol fields (address, port, uuid, password…)
// using the xray-config-kit caps and XrayParityFormControl.

interface ProtocolSettingsGridProps {
  ob: Outbound
  settingsOrder: readonly string[]
  outboundCaps: ReturnType<typeof getOutboundFormCapabilities>
  form: ReturnType<typeof useForm<Record<string, string>>>
  patchOutbound: (next: Outbound) => void
}

function ProtocolSettingsGrid({ ob, settingsOrder, outboundCaps, form, patchOutbound }: ProtocolSettingsGridProps) {
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      {settingsOrder.map((jsonKey: string) => {
        const def = outboundCaps.settingsFieldDefinitions[ob.protocol]?.[jsonKey] as XrayGeneratedFormField | undefined
        if (!def) return null
        const name = `${ST_PREFIX}${jsonKey}`
        const wide = inferParityFieldMode(def) !== 'scalar' || outboundScalarParityFieldPrefersFullGridWidth(def)
        const isBoolean = isBooleanParityField(def)
        return (
          <FormField
            key={jsonKey}
            control={form.control}
            name={name}
            render={({ field }) => (
              <FormItem className={cn((wide || isBoolean) && 'sm:col-span-2')}>
                {!isBoolean && <FormLabel className="text-xs font-medium">{humanizeFieldName(jsonKey)}</FormLabel>}
                <XrayParityFormControl
                  field={def}
                  value={field.value ?? ''}
                  renderBooleanAsToggleRow={isBoolean}
                  onChange={v => {
                    field.onChange(v)
                    try {
                      const parsed = parseOutboundSettingValue(def, v)
                      patchOutboundWithSettingsMerge(ob, patchOutbound, flat => ({ ...flat, [jsonKey]: parsed }))
                    } catch {
                      /* wait for valid input */
                    }
                  }}
                />
                <FormMessage />
              </FormItem>
            )}
          />
        )
      })}
    </div>
  )
}

// ─── Stream Settings Accordion ────────────────────────────────────────────────

interface OutboundStreamSettingsAccordionProps {
  ob: Outbound
  obStreamSettings: Record<string, unknown> | null
  form: ReturnType<typeof useForm<Record<string, string>>>
  patchOutbound: (next: Outbound) => void
  t: (key: string, opts?: Record<string, unknown>) => string
  dialerProxyTagOptions: readonly string[]
}

/** Same ALPN editor as inbound stream/TLS (`XrayParityFormControl` treats `alpn` specially). */
const OUTBOUND_TLS_ALPN_PARITY_FIELD = {
  go: 'alpn',
  json: 'alpn',
  type: '[]string',
} as XrayGeneratedFormField

function OutboundStreamSettingsAccordion({ ob, obStreamSettings, form, patchOutbound, t, dialerProxyTagOptions }: OutboundStreamSettingsAccordionProps) {
  const streamSecurity = normalizeOutboundStreamSecurity(obStreamSettings?.security)
  const sockoptValue =
    obStreamSettings && typeof obStreamSettings.sockopt === 'object' && obStreamSettings.sockopt !== null && !Array.isArray(obStreamSettings.sockopt)
      ? (obStreamSettings.sockopt as Record<string, unknown>)
      : undefined
  const rawNetwork = typeof obStreamSettings?.network === 'string' ? obStreamSettings.network.trim().toLowerCase() : ''

  const streamNetworkSelectValues = useMemo(() => getOutboundStreamNetworkSelectValues(streamSecurity, rawNetwork || 'tcp'), [streamSecurity, rawNetwork])

  const streamNetwork = useMemo(() => {
    if (rawNetwork && streamNetworkSelectValues.includes(rawNetwork)) return rawNetwork
    return streamNetworkSelectValues.includes('tcp') ? 'tcp' : (streamNetworkSelectValues[0] ?? 'tcp')
  }, [rawNetwork, streamNetworkSelectValues])

  const realityTransportOk = outboundStreamNetworkCompatibleWithReality(streamNetwork)

  /** Imported / hand-edited JSON can pair REALITY with ws/h2/etc.; kit rejects — coerce to TLS like inbound editor. */
  useEffect(() => {
    if (streamSecurity !== 'reality') return
    if (realityTransportOk) return
    const cur = (ob as { streamSettings?: Record<string, unknown> }).streamSettings ?? {}
    const nextSs: Record<string, unknown> = { ...cur, security: 'tls' }
    delete nextSs.realitySettings
    patchOutbound(
      stripEmptyStreamSettingsFromRecord({
        ...(ob as Record<string, unknown>),
        streamSettings: nextSs,
      }) as Outbound,
    )
  }, [ob, patchOutbound, realityTransportOk, streamSecurity])

  const tlsSettings = streamSecurity === 'tls' && obStreamSettings?.tlsSettings && typeof obStreamSettings.tlsSettings === 'object' ? (obStreamSettings.tlsSettings as Record<string, unknown>) : null

  const realitySettings =
    streamSecurity === 'reality' && obStreamSettings?.realitySettings && typeof obStreamSettings.realitySettings === 'object' ? (obStreamSettings.realitySettings as Record<string, unknown>) : null

  const patchStreamSettings = (patch: Record<string, unknown>) => {
    const cur = (ob as { streamSettings?: Record<string, unknown> }).streamSettings ?? {}
    const merged = { ...cur, ...patch }
    for (const k of Object.keys(merged)) {
      if (merged[k] === undefined) delete merged[k]
    }
    const next = stripEmptyStreamSettingsFromRecord({
      ...(ob as Record<string, unknown>),
      streamSettings: merged,
    }) as Outbound
    patchOutbound(next)
  }

  const patchTls = (patch: Record<string, unknown>) => {
    const cur = ((ob as { streamSettings?: Record<string, unknown> }).streamSettings?.tlsSettings ?? {}) as Record<string, unknown>
    patchStreamSettings({ tlsSettings: { ...cur, ...patch } })
  }

  const patchReality = (patch: Record<string, unknown>) => {
    const cur = ((ob as { streamSettings?: Record<string, unknown> }).streamSettings?.realitySettings ?? {}) as Record<string, unknown>
    patchStreamSettings({ realitySettings: { ...cur, ...patch } })
  }

  const wsSettings = obStreamSettings?.wsSettings as Record<string, unknown> | undefined
  const wsPath = typeof wsSettings?.path === 'string' ? wsSettings.path : ''
  const wsHost = typeof (wsSettings?.headers as Record<string, unknown> | undefined)?.Host === 'string' ? ((wsSettings!.headers as Record<string, unknown>).Host as string) : ''

  const grpcSettings = obStreamSettings?.grpcSettings as Record<string, unknown> | undefined
  const grpcServiceName = typeof grpcSettings?.serviceName === 'string' ? grpcSettings.serviceName : ''

  const xhttpSettingsKey = streamNetwork === 'xhttp' ? 'xhttpSettings' : 'splithttpSettings'
  const xhttpSettingsRec = obStreamSettings?.[xhttpSettingsKey] as Record<string, unknown> | undefined
  const xhttpPath = typeof xhttpSettingsRec?.path === 'string' ? xhttpSettingsRec.path : ''

  const tcpSettings = obStreamSettings?.tcpSettings as Record<string, unknown> | undefined
  const tcpHeader = tcpSettings?.header
  const isTcpObfEnabled = tcpHeader != null && typeof tcpHeader === 'object' && !Array.isArray(tcpHeader) && (tcpHeader as Record<string, unknown>).type === 'http'

  const FINGERPRINTS = ['chrome', 'firefox', 'safari', 'ios', 'android', 'edge', '360', 'qq', 'random', 'randomized']

  return (
    <AccordionItem value="stream" className="rounded-sm border px-4 [&_[data-state=closed]]:no-underline [&_[data-state=open]]:no-underline">
      <AccordionTrigger>
        <div className="flex flex-wrap items-center gap-2">
          <Cable className="text-muted-foreground h-4 w-4 shrink-0" aria-hidden />
          <span>{t('coreEditor.outbound.streamSection', { defaultValue: 'Stream & Security' })}</span>
          {(streamSecurity !== 'none' || streamNetwork !== 'tcp') && (
            <span className="bg-muted text-muted-foreground rounded px-1.5 py-0.5 text-[10px] font-medium">
              {streamNetwork}
              {streamSecurity !== 'none' ? ` · ${streamSecurity}` : ''}
            </span>
          )}
        </div>
      </AccordionTrigger>
      <AccordionContent className="px-2 pb-4">
        <div className="grid gap-4 sm:grid-cols-2">
          {/* Network type */}
          <FieldRow label={t('coreEditor.field.network', { defaultValue: 'Transport Protocol' })}>
            <Select
              dir="ltr"
              value={streamNetwork}
              onValueChange={v => {
                if (streamSecurity === 'reality' && !outboundStreamNetworkCompatibleWithReality(v)) {
                  patchStreamSettings({
                    network: v,
                    security: 'tls',
                    realitySettings: undefined,
                  })
                  return
                }
                patchStreamSettings({ network: v })
              }}
            >
              <SelectTrigger className="h-10 w-full min-w-0" dir="ltr">
                <SelectValue />
              </SelectTrigger>
              <SelectContent dir="ltr">
                {streamNetworkSelectValues.map(n => (
                  <SelectItem key={n} value={n}>
                    {outboundStreamNetworkSelectLabel(n)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </FieldRow>

          {/* Security layer */}
          <FieldRow label={t('coreEditor.field.securityType', { defaultValue: 'Security Layer' })}>
            <Select
              dir="ltr"
              value={streamSecurity}
              onValueChange={v => {
                if (v === 'none') {
                  const cur = (ob as { streamSettings?: Record<string, unknown> }).streamSettings ?? {}
                  const mergedStream: Record<string, unknown> = { ...cur, security: 'none' }
                  delete mergedStream.tlsSettings
                  delete mergedStream.realitySettings
                  let out: Outbound = stripEmptyStreamSettingsFromRecord({
                    ...(ob as Record<string, unknown>),
                    streamSettings: mergedStream,
                  }) as Outbound
                  if (ob.protocol === 'vless') {
                    const flat = flattenOutboundSettings(ob)
                    const fl = String(flat.flow ?? '')
                    if (vlessVisionFlowIncompatibleWithStreamSecurity('none', fl)) {
                      out = {
                        ...out,
                        settings: normalizeSettingsFromEditor('vless', { ...flat, flow: '' }),
                      } as Outbound
                    }
                  }
                  patchOutbound(out)
                } else if (v === 'tls') patchStreamSettings({ security: 'tls', realitySettings: undefined })
                else if (v === 'reality') {
                  if (!outboundStreamNetworkCompatibleWithReality(streamNetwork)) {
                    patchStreamSettings({
                      network: 'tcp',
                      security: 'reality',
                      tlsSettings: undefined,
                    })
                  } else {
                    patchStreamSettings({ security: 'reality', tlsSettings: undefined })
                  }
                }
              }}
            >
              <SelectTrigger className="h-10 w-full min-w-0" dir="ltr">
                <SelectValue />
              </SelectTrigger>
              <SelectContent dir="ltr">
                <SelectItem value="none">None</SelectItem>
                <SelectItem value="tls">TLS</SelectItem>
                {realityTransportOk ? (
                  <SelectItem value="reality">Reality</SelectItem>
                ) : (
                  <SelectItem value="reality" disabled>
                    {t('coreEditor.outbound.realityUnavailableTransport', {
                      defaultValue: 'Reality (not available for this transport)',
                    })}
                  </SelectItem>
                )}
              </SelectContent>
            </Select>
          </FieldRow>

          {/* ── TLS ─────────────────────────────────────────────────── */}
          {streamSecurity === 'tls' && (
            <>
              <Separator className="sm:col-span-2" />
              <div className="flex items-center gap-2 sm:col-span-2">
                <Shield className="text-muted-foreground h-3.5 w-3.5 shrink-0" aria-hidden />
                <p className="text-muted-foreground text-xs font-semibold tracking-wide uppercase">{t('coreEditor.outbound.tlsSettings', { defaultValue: 'TLS Settings' })}</p>
              </div>

              <FieldRow label={t('coreEditor.field.serverName', { defaultValue: 'Server Name (SNI)' })}>
                <Input
                  key={String(tlsSettings?.serverName ?? '')}
                  dir="ltr"
                  className="h-10 w-full min-w-0 text-xs"
                  placeholder="example.com"
                  defaultValue={typeof tlsSettings?.serverName === 'string' ? tlsSettings.serverName : ''}
                  onBlur={e => patchTls({ serverName: e.target.value || undefined })}
                />
              </FieldRow>

              <FieldRow label={t('coreEditor.field.fingerprint', { defaultValue: 'TLS Fingerprint' })}>
                <Select
                  dir="ltr"
                  value={typeof tlsSettings?.fingerprint === 'string' ? tlsSettings.fingerprint : '__none'}
                  onValueChange={v => patchTls({ fingerprint: v === '__none' ? undefined : v })}
                >
                  <SelectTrigger className="h-10 w-full min-w-0" dir="ltr">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent dir="ltr">
                    <SelectItem value="__none">Auto</SelectItem>
                    {FINGERPRINTS.map(fp => (
                      <SelectItem key={fp} value={fp}>
                        {fp}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </FieldRow>

              <FieldRow label={t('coreEditor.field.alpn', { defaultValue: 'ALPN Protocols' })} wide>
                <XrayParityFormControl
                  field={OUTBOUND_TLS_ALPN_PARITY_FIELD}
                  value={outboundSettingToString(tlsSettings?.alpn, OUTBOUND_TLS_ALPN_PARITY_FIELD)}
                  className="w-full"
                  onChange={raw => {
                    try {
                      const parsed = parseOutboundSettingValue(OUTBOUND_TLS_ALPN_PARITY_FIELD, raw)
                      patchTls({
                        alpn: Array.isArray(parsed) && parsed.length > 0 ? (parsed as string[]) : undefined,
                      })
                    } catch {
                      /* wait for valid selection */
                    }
                  }}
                />
              </FieldRow>

              <div className="flex items-center justify-between rounded-lg border px-3 py-2.5 sm:col-span-2">
                <div>
                  <p className="text-sm font-medium">{t('coreEditor.field.allowInsecure', { defaultValue: 'Allow Insecure' })}</p>
                  <p className="text-muted-foreground text-xs">{t('coreEditor.field.allowInsecureHint', { defaultValue: 'Skip certificate verification (not recommended)' })}</p>
                </div>
                <Switch checked={tlsSettings?.allowInsecure === true} onCheckedChange={checked => patchTls({ allowInsecure: checked || undefined })} />
              </div>

              {/* ECH Configuration */}
              {tlsSettings?.echSockopt && (
                <Accordion type="single" collapsible className="w-full min-w-0 sm:col-span-2">
                  <AccordionItem value="ech" className="rounded-sm border px-4 [&_[data-state=closed]]:no-underline [&_[data-state=open]]:no-underline">
                    <AccordionTrigger>
                      <div className="flex min-w-0 items-center gap-2">
                        <KeyRound className="text-muted-foreground h-4 w-4 shrink-0" aria-hidden />
                        <span className="truncate text-left">
                          {t('coreEditor.outbound.ech.sectionTitle', {
                            defaultValue: 'ECH (Encrypted Client Hello)',
                          })}
                        </span>
                      </div>
                    </AccordionTrigger>
                    <AccordionContent className="space-y-4 px-2 pb-4">
                      <p className="text-muted-foreground text-xs leading-relaxed">
                        {t('coreEditor.outbound.ech.sectionHint', {
                          defaultValue: 'Configure ECH client keys and behavior.',
                        })}
                      </p>
                      <div className="grid gap-3 sm:grid-cols-2">
                        <FormItem className="w-full min-w-0">
                          <FormLabel className="text-muted-foreground text-xs font-medium">{t('coreEditor.outbound.ech.configList', { defaultValue: 'ECH Config List' })}</FormLabel>
                          <Textarea
                            dir="ltr"
                            rows={3}
                            className="min-h-[72px] w-full min-w-0 resize-y text-xs"
                            placeholder="ECH configs (base64 or JSON)"
                            value={typeof (tlsSettings.echSockopt as any)?.configList === 'string' ? (tlsSettings.echSockopt as any).configList : ''}
                            onChange={e => {
                              const current = tlsSettings?.echSockopt as any
                              patchTls({
                                echSockopt: {
                                  ...current,
                                  configList: e.target.value || undefined,
                                },
                              })
                            }}
                          />
                        </FormItem>

                        <FormField
                          control={form.control}
                          name={`tls_ech_forceQuery`}
                          render={({ field }) => (
                            <FormItem className="w-full min-w-0">
                              <FormLabel className="text-muted-foreground text-xs font-medium">{t('coreEditor.outbound.ech.forceQuery', { defaultValue: 'ECH Force Query' })}</FormLabel>
                              <Select
                                value={field.value && String(field.value).trim() !== '' ? field.value : '__default'}
                                onValueChange={v => {
                                  field.onChange(v === '__default' ? '' : v)
                                  const current = tlsSettings?.echSockopt as any
                                  patchTls({
                                    echSockopt: {
                                      ...current,
                                      forceQuery: v === '__default' ? undefined : v,
                                    },
                                  })
                                }}
                              >
                                <SelectTrigger className="h-10 w-full min-w-0">
                                  <SelectValue />
                                </SelectTrigger>
                                <SelectContent>
                                  <SelectItem value="__default">{t('coreEditor.outbound.ech.forceQueryDefault', { defaultValue: 'Default' })}</SelectItem>
                                  <SelectItem value="none">none</SelectItem>
                                  <SelectItem value="half">half</SelectItem>
                                  <SelectItem value="full">full</SelectItem>
                                </SelectContent>
                              </Select>
                            </FormItem>
                          )}
                        />
                      </div>
                    </AccordionContent>
                  </AccordionItem>
                </Accordion>
              )}
            </>
          )}

          {/* ── Reality ──────────────────────────────────────────────── */}
          {streamSecurity === 'reality' && (
            <>
              <Separator className="sm:col-span-2" />
              <div className="flex items-center gap-2 sm:col-span-2">
                <Shield className="text-muted-foreground h-3.5 w-3.5 shrink-0" aria-hidden />
                <p className="text-muted-foreground text-xs font-semibold tracking-wide uppercase">{t('coreEditor.outbound.realitySettings', { defaultValue: 'Reality Settings' })}</p>
              </div>

              <FieldRow label={t('coreEditor.field.serverName', { defaultValue: 'Server Name (SNI)' })}>
                <Input
                  key={String(realitySettings?.serverName ?? '')}
                  dir="ltr"
                  className="h-10 w-full min-w-0 text-xs"
                  placeholder="example.com"
                  defaultValue={typeof realitySettings?.serverName === 'string' ? realitySettings.serverName : ''}
                  onBlur={e => patchReality({ serverName: e.target.value || undefined })}
                />
              </FieldRow>

              <FieldRow label={t('coreEditor.field.fingerprint', { defaultValue: 'TLS Fingerprint' })}>
                <Select
                  dir="ltr"
                  value={typeof realitySettings?.fingerprint === 'string' ? realitySettings.fingerprint : '__none'}
                  onValueChange={v => patchReality({ fingerprint: v === '__none' ? undefined : v })}
                >
                  <SelectTrigger className="h-10 w-full min-w-0" dir="ltr">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent dir="ltr">
                    <SelectItem value="__none">Auto</SelectItem>
                    {FINGERPRINTS.map(fp => (
                      <SelectItem key={fp} value={fp}>
                        {fp}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </FieldRow>

              <FieldRow label={t('coreEditor.field.publicKey', { defaultValue: 'Server Public Key' })} wide>
                <Input
                  key={String(realitySettings?.publicKey ?? '')}
                  dir="ltr"
                  className="h-10 w-full min-w-0 text-xs"
                  placeholder="Base64 encoded public key"
                  defaultValue={typeof realitySettings?.publicKey === 'string' ? realitySettings.publicKey : ''}
                  onBlur={e => patchReality({ publicKey: e.target.value || undefined })}
                />
              </FieldRow>

              <FieldRow label={t('coreEditor.field.shortId', { defaultValue: 'Short ID' })}>
                <Input
                  key={String(realitySettings?.shortId ?? '')}
                  dir="ltr"
                  className="h-10 w-full min-w-0 text-xs"
                  placeholder="Hex string (0–8 bytes)"
                  defaultValue={typeof realitySettings?.shortId === 'string' ? realitySettings.shortId : ''}
                  onBlur={e => patchReality({ shortId: e.target.value || undefined })}
                />
              </FieldRow>

              <FieldRow label={t('coreEditor.field.spiderX', { defaultValue: 'SpiderX Path' })}>
                <Input
                  key={String(realitySettings?.spiderX ?? '')}
                  dir="ltr"
                  className="h-10 w-full min-w-0 text-xs"
                  placeholder="/path?query"
                  defaultValue={typeof realitySettings?.spiderX === 'string' ? realitySettings.spiderX : ''}
                  onBlur={e => patchReality({ spiderX: e.target.value || undefined })}
                />
              </FieldRow>
            </>
          )}

          {/* ── WebSocket ─────────────────────────────────────────────── */}
          {streamNetwork === 'ws' && (
            <>
              <Separator className="sm:col-span-2" />
              <p className="text-muted-foreground text-xs font-semibold tracking-wide uppercase sm:col-span-2">{t('coreEditor.outbound.wsSettings', { defaultValue: 'WebSocket Settings' })}</p>

              <FieldRow label={t('coreEditor.field.path', { defaultValue: 'Path' })}>
                <Input
                  key={wsPath}
                  dir="ltr"
                  className="h-10 w-full min-w-0 text-xs"
                  placeholder="/ws"
                  defaultValue={wsPath}
                  onBlur={e => {
                    const ws = (obStreamSettings?.wsSettings as Record<string, unknown>) ?? {}
                    patchStreamSettings({ wsSettings: { ...ws, path: e.target.value || undefined } })
                  }}
                />
              </FieldRow>

              <FieldRow label={t('coreEditor.field.host', { defaultValue: 'Host Header' })}>
                <Input
                  key={wsHost}
                  dir="ltr"
                  className="h-10 w-full min-w-0 text-xs"
                  placeholder="example.com"
                  defaultValue={wsHost}
                  onBlur={e => {
                    const ws = (obStreamSettings?.wsSettings as Record<string, unknown>) ?? {}
                    const headers = { ...((ws.headers as Record<string, unknown>) ?? {}) }
                    if (e.target.value) headers.Host = e.target.value
                    else delete headers.Host
                    patchStreamSettings({ wsSettings: { ...ws, headers: Object.keys(headers).length ? headers : undefined } })
                  }}
                />
              </FieldRow>
            </>
          )}

          {/* ── gRPC ──────────────────────────────────────────────────── */}
          {streamNetwork === 'grpc' && (
            <>
              <Separator className="sm:col-span-2" />
              <p className="text-muted-foreground text-xs font-semibold tracking-wide uppercase sm:col-span-2">{t('coreEditor.outbound.grpcSettings', { defaultValue: 'gRPC Settings' })}</p>
              <FieldRow label={t('coreEditor.field.serviceName', { defaultValue: 'Service Name' })} wide>
                <Input
                  key={grpcServiceName}
                  dir="ltr"
                  className="h-10 w-full min-w-0 text-xs"
                  placeholder="GunService"
                  defaultValue={grpcServiceName}
                  onBlur={e => {
                    const grpc = (obStreamSettings?.grpcSettings as Record<string, unknown>) ?? {}
                    patchStreamSettings({ grpcSettings: { ...grpc, serviceName: e.target.value || undefined } })
                  }}
                />
              </FieldRow>
            </>
          )}

          {/* ── XHTTP / SplitHTTP ────────────────────────────────────── */}
          {(streamNetwork === 'xhttp' || streamNetwork === 'splithttp') && (
            <>
              <Separator className="sm:col-span-2" />
              <p className="text-muted-foreground text-xs font-semibold tracking-wide uppercase sm:col-span-2">{t('coreEditor.outbound.xhttpSettings', { defaultValue: 'XHTTP Settings' })}</p>
              <FieldRow label={t('coreEditor.field.path', { defaultValue: 'Path' })} wide>
                <Input
                  key={xhttpPath}
                  dir="ltr"
                  className="h-10 w-full min-w-0 text-xs"
                  placeholder="/"
                  defaultValue={xhttpPath}
                  onBlur={e => {
                    const cur = (obStreamSettings?.[xhttpSettingsKey] as Record<string, unknown>) ?? {}
                    patchStreamSettings({ [xhttpSettingsKey]: { ...cur, path: e.target.value || undefined } })
                  }}
                />
              </FieldRow>
            </>
          )}

          {/* ── TCP HTTP obfuscation ──────────────────────────────────── */}
          {streamNetwork === 'tcp' && (
            <>
              <Separator className="sm:col-span-2" />
              <div className="flex flex-col gap-3 sm:col-span-2">
                <div className="flex items-center justify-between rounded-lg border px-3 py-2.5">
                  <div>
                    <p className="text-sm font-medium">{t('coreEditor.inbound.tcp.httpObfuscation', { defaultValue: 'HTTP Obfuscation' })}</p>
                    <p className="text-muted-foreground text-xs">
                      {t('coreEditor.inbound.tcp.httpObfuscationHint', {
                        defaultValue: 'Disguise traffic as HTTP requests',
                      })}
                    </p>
                  </div>
                  <Switch
                    checked={isTcpObfEnabled}
                    onCheckedChange={checked => {
                      const cur = tcpSettings ?? {}
                      if (checked) {
                        patchStreamSettings({
                          tcpSettings: {
                            ...cur,
                            header: {
                              type: 'http',
                              request: { version: '1.1', method: 'GET', path: ['/'], headers: {} },
                              response: { version: '1.1', status: '200', reason: 'OK', headers: {} },
                            },
                          },
                        })
                      } else {
                        const next = { ...cur }
                        delete next.header
                        patchStreamSettings({ tcpSettings: Object.keys(next).length ? next : undefined })
                      }
                    }}
                  />
                </div>
                {isTcpObfEnabled && tcpHeader != null && typeof tcpHeader === 'object' && !Array.isArray(tcpHeader) && (
                  <TcpHeaderObfuscationForm
                    currentValue={tcpHeader as Record<string, unknown>}
                    onValueChange={next => {
                      patchStreamSettings({ tcpSettings: { ...(tcpSettings ?? {}), header: next } })
                    }}
                  />
                )}
              </div>
            </>
          )}

          <Separator className="sm:col-span-2" />
          <div className="flex flex-col gap-3 sm:col-span-2">
            <div className="text-muted-foreground flex items-center gap-2 text-xs font-semibold tracking-wide uppercase">
              <SlidersHorizontal className="h-3.5 w-3.5 shrink-0" aria-hidden />
              <span>{t('coreEditor.sockopt.section')}</span>
            </div>
            <XrayStreamSockoptFields
              variant="outbound"
              value={sockoptValue}
              onChange={next =>
                patchStreamSettings({
                  sockopt: next === undefined ? undefined : next,
                })
              }
              t={t}
              dialerProxyTags={dialerProxyTagOptions}
            />
          </div>
        </div>
      </AccordionContent>
    </AccordionItem>
  )
}

// ─── Advanced (Mux + Proxy) Accordion ────────────────────────────────────────

interface OutboundSockoptAccordionProps {
  ob: Outbound
  patchOutbound: (next: Outbound) => void
  t: (key: string, opts?: Record<string, unknown>) => string
  dialerProxyTagOptions: readonly string[]
}

function OutboundSockoptAccordion({ ob, patchOutbound, t, dialerProxyTagOptions }: OutboundSockoptAccordionProps) {
  const sockoptValue = outboundSockoptValue(ob)
  const sockoptConfigured = pruneSockoptObject(sockoptValue) != null

  return (
    <AccordionItem value="sockopt" className="rounded-sm border px-4 [&_[data-state=closed]]:no-underline [&_[data-state=open]]:no-underline">
      <AccordionTrigger>
        <div className="flex flex-wrap items-center gap-2">
          <SlidersHorizontal className="text-muted-foreground h-4 w-4 shrink-0" aria-hidden />
          <span>{t('coreEditor.sockopt.section')}</span>
          {sockoptConfigured && <span className="bg-muted text-muted-foreground rounded px-1.5 py-0.5 text-[10px] font-medium">{t('enabled', { defaultValue: 'on' })}</span>}
        </div>
      </AccordionTrigger>
      <AccordionContent className="px-2 pb-4">
        <XrayStreamSockoptFields
          variant="outbound"
          value={sockoptValue}
          onChange={next => patchOutboundSockopt(ob, patchOutbound, next)}
          t={t}
          dialerProxyTags={dialerProxyTagOptions}
        />
      </AccordionContent>
    </AccordionItem>
  )
}

interface OutboundAdvancedAccordionProps {
  ob: Outbound
  patchOutbound: (next: Outbound) => void
  t: (key: string, opts?: Record<string, unknown>) => string
}

function OutboundAdvancedAccordion({ ob, patchOutbound, t }: OutboundAdvancedAccordionProps) {
  const mux = (ob as { mux?: Record<string, unknown> }).mux ?? null
  const proxySettings = (ob as { proxySettings?: Record<string, unknown> }).proxySettings ?? null

  const patchMux = (patch: Record<string, unknown> | null) => {
    const base = { ...(ob as Record<string, unknown>) }
    if (patch == null) delete base.mux
    else base.mux = patch
    patchOutbound(stripSparseOutboundEnvelope(base) as Outbound)
  }

  const patchProxySettings = (patch: Record<string, unknown> | null) => {
    const base = { ...(ob as Record<string, unknown>) }
    if (patch == null) delete base.proxySettings
    else base.proxySettings = patch
    patchOutbound(stripSparseOutboundEnvelope(base) as Outbound)
  }

  const UDP443_OPTIONS = [
    { value: '__default', label: 'Default' },
    { value: 'allow', label: 'Allow' },
    { value: 'reject', label: 'Block' },
    { value: 'skip', label: 'Skip' },
  ]

  const muxBlock =
    'mux' in ob ? (
      <AccordionItem value="mux" className="rounded-sm border px-4 [&_[data-state=closed]]:no-underline [&_[data-state=open]]:no-underline">
        <AccordionTrigger>
          <div className="flex flex-wrap items-center gap-2">
            <RefreshCw className="text-muted-foreground h-4 w-4 shrink-0" aria-hidden />
            <span>{t('coreEditor.outbound.muxSection', { defaultValue: 'Multiplexing (Mux)' })}</span>
            {mux?.enabled === true && <span className="bg-muted text-muted-foreground rounded px-1.5 py-0.5 text-[10px] font-medium">{t('enabled', { defaultValue: 'on' })}</span>}
          </div>
        </AccordionTrigger>
        <AccordionContent className="px-2 pb-4">
          <div className="flex flex-col gap-4">
            <div className="flex items-center justify-between rounded-lg border px-3 py-2.5">
              <div>
                <p className="text-sm font-medium">{t('coreEditor.outbound.mux.enabled', { defaultValue: 'Enable Mux' })}</p>
                <p className="text-muted-foreground text-xs">{t('coreEditor.outbound.mux.enabledHint', { defaultValue: 'Multiplex multiple streams over one connection' })}</p>
              </div>
              <Switch checked={mux?.enabled === true} onCheckedChange={checked => patchMux(checked ? { ...(mux ?? {}), enabled: true } : mux ? { ...mux, enabled: false } : null)} />
            </div>

            {mux?.enabled === true && (
              <>
                <Separator />
                <div className="grid gap-4 sm:grid-cols-2">
                  <FieldRow label={t('coreEditor.outbound.mux.concurrency', { defaultValue: 'Concurrency' })}>
                    <Input
                      key={String(mux.concurrency ?? '')}
                      type="number"
                      dir="ltr"
                      inputMode="numeric"
                      className="h-10"
                      placeholder="8"
                      defaultValue={mux.concurrency !== undefined ? String(mux.concurrency) : ''}
                      onBlur={e => {
                        const v = e.target.value.trim()
                        const n = Number(v)
                        patchMux({ ...mux, concurrency: v === '' ? undefined : Number.isFinite(n) ? n : undefined })
                      }}
                    />
                  </FieldRow>

                  <FieldRow label={t('coreEditor.outbound.mux.xudpConcurrency', { defaultValue: 'XUDP Concurrency' })}>
                    <Input
                      key={String(mux.xudpConcurrency ?? '')}
                      type="number"
                      dir="ltr"
                      inputMode="numeric"
                      className="h-10"
                      placeholder="8"
                      defaultValue={mux.xudpConcurrency !== undefined ? String(mux.xudpConcurrency) : ''}
                      onBlur={e => {
                        const v = e.target.value.trim()
                        const n = Number(v)
                        patchMux({ ...mux, xudpConcurrency: v === '' ? undefined : Number.isFinite(n) ? n : undefined })
                      }}
                    />
                  </FieldRow>

                  <FieldRow label={t('coreEditor.outbound.mux.xudpProxyUDP443', { defaultValue: 'UDP Port 443 Handling' })} wide>
                    <Select
                      dir="ltr"
                      value={typeof mux.xudpProxyUDP443 === 'string' ? mux.xudpProxyUDP443 : '__default'}
                      onValueChange={v => patchMux({ ...mux, xudpProxyUDP443: v === '__default' ? undefined : v })}
                    >
                      <SelectTrigger className="h-10 w-full min-w-0" dir="ltr">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent dir="ltr">
                        {UDP443_OPTIONS.map(o => (
                          <SelectItem key={o.value} value={o.value}>
                            {o.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </FieldRow>
                </div>
              </>
            )}
          </div>
        </AccordionContent>
      </AccordionItem>
    ) : null

  const proxyBlock =
    'proxySettings' in ob ? (
      <AccordionItem value="proxy" className="rounded-sm border px-4 [&_[data-state=closed]]:no-underline [&_[data-state=open]]:no-underline">
        <AccordionTrigger>
          <div className="flex flex-wrap items-center gap-2">
            <Shield className="text-muted-foreground h-4 w-4 shrink-0" aria-hidden />
            <span>{t('coreEditor.outbound.proxySection', { defaultValue: 'Chain Proxy' })}</span>
            {typeof proxySettings?.tag === 'string' && proxySettings.tag && <span className="bg-muted text-muted-foreground rounded px-1.5 py-0.5 text-[10px]">{proxySettings.tag}</span>}
          </div>
        </AccordionTrigger>
        <AccordionContent className="px-2 pb-4">
          <div className="flex flex-col gap-4">
            <FieldRow label={t('coreEditor.outbound.proxy.tag', { defaultValue: 'Route Through Outbound Tag' })}>
              <Input
                key={String(proxySettings?.tag ?? '')}
                dir="ltr"
                className="h-10 w-full min-w-0 text-xs"
                placeholder="other-outbound-tag"
                defaultValue={typeof proxySettings?.tag === 'string' ? proxySettings.tag : ''}
                onBlur={e => {
                  const v = e.target.value.trim()
                  patchProxySettings(v ? { ...(proxySettings ?? {}), tag: v } : null)
                }}
              />
            </FieldRow>

            <div className="flex items-center justify-between rounded-lg border px-3 py-2.5">
              <div>
                <p className="text-sm font-medium">{t('coreEditor.outbound.proxy.transportLayer', { defaultValue: 'Transport Layer Proxy' })}</p>
                <p className="text-muted-foreground text-xs">
                  {t('coreEditor.outbound.proxy.transportLayerHint', {
                    defaultValue: 'Also proxy the transport layer stream',
                  })}
                </p>
              </div>
              <Switch checked={proxySettings?.transportLayer === true} onCheckedChange={checked => patchProxySettings({ ...(proxySettings ?? {}), transportLayer: checked || undefined })} />
            </div>
          </div>
        </AccordionContent>
      </AccordionItem>
    ) : null

  if (!muxBlock && !proxyBlock) return null
  // Return an array of items (not a Fragment) so Radix Accordion registers each AccordionItem on the same root.
  const items: ReactElement[] = []
  if (muxBlock) items.push(muxBlock)
  if (proxyBlock) items.push(proxyBlock)
  return items
}
