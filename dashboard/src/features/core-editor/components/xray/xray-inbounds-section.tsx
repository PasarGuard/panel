import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from '@/components/ui/alert-dialog'
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form'
import { Input } from '@/components/ui/input'
import { LoaderButton } from '@/components/ui/loader-button'
import { PasswordInput } from '@/components/ui/password-input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Separator } from '@/components/ui/separator'
import { Switch } from '@/components/ui/switch'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Textarea } from '@/components/ui/textarea'
import { StringArrayPopoverInput } from '@/components/common/string-array-popover-input'
import { CoreEditorDataTable } from '@/features/core-editor/components/shared/core-editor-data-table'
import { CoreEditorFormDialog } from '@/features/core-editor/components/shared/core-editor-form-dialog'
import { VlessAdvancedGenerationModal } from '@/features/core-editor/components/shared/vless-advanced-generation-modal'
import { isBooleanParityField, isJsonRawMessageField, transportParityFieldLabel, XrayParityFormControl } from '@/features/core-editor/components/shared/xray-parity-form-control'
import { TcpHeaderObfuscationForm } from '@/features/core-editor/components/shared/tcp-header-obfuscation-form'
import { pruneSockoptObject, XrayStreamSockoptInboundAccordion } from '@/features/core-editor/components/shared/xray-stream-sockopt-editor'
import { InboundTlsFallbacksEditor } from '@/features/core-editor/components/xray/inbound-tls-fallbacks-editor'
import { getInboundSecuritySelectOptions, getInboundTransportSelectOptions, transportCompatibleWithReality } from '@/features/core-editor/kit/inbound-form-options'
import { inferParityFieldMode, outboundSettingToString, parseOutboundSettingValue } from '@/features/core-editor/kit/xray-parity-value'
import { useSectionHeaderAddPulseEffect, type SectionHeaderAddPulse } from '@/features/core-editor/hooks/use-section-header-add-pulse'
import { useXrayPersistModifyGuard } from '@/features/core-editor/hooks/use-xray-persist-modify-guard'
import { createInboundDialogSchema, realityInboundZodTriggerFieldNames } from '@/features/core-editor/kit/inbound-dialog-schema'
import { remapIndexAfterArrayMove } from '@/features/core-editor/kit/remap-index-after-move'
import { profileDuplicateTagMessage, profileTagHasDuplicateUsage } from '@/features/core-editor/kit/profile-tag-uniqueness'
import { isPlaceholderTunnelRewriteAddress, normalizeTunnelNetworkForKit } from '@/features/core-editor/kit/sanitize-inbound'
import { useCoreEditorStore } from '@/features/core-editor/state/core-editor-store'
import { generateWireGuardKeyPair, getWireGuardPublicKey } from '@/utils/wireguard'
import {
  buildVlessGenerationOptionsFromInboundForm,
  generateShadowsocksPassword,
  generateRealityKeyPair,
  generateRealityShortId,
  generateMldsa65Keys,
  parseVlessEncryptionMethodTokenFromString,
  SHADOWSOCKS_ENCRYPTION_METHODS,
  VLESS_ENCRYPTION_METHODS,
  vlessInboundEncryptionMethodForForm,
  vlessInboundEncryptionRawForForm,
  type VlessBuilderOptions,
} from '@/lib/xray-generation'
import { createDefaultInbound, createDefaultInboundForProtocol, getInboundFieldVisibility, getInboundFormCapabilities } from '@pasarguard/xray-config-kit'
import type { Fallback, Inbound, InboundPort, Profile, Security, ShadowsocksMethod, Transport } from '@pasarguard/xray-config-kit'
import useDirDetection from '@/hooks/use-dir-detection'
import { cn } from '@/lib/utils'
import { Cable, KeyRound, Pencil, Plus, RefreshCcw, RefreshCw, Shield, Trash2 } from 'lucide-react'
import { zodResolver } from '@hookform/resolvers/zod'
import { arrayMove } from '@dnd-kit/sortable'
import type { ColumnDef } from '@tanstack/react-table'
import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useForm, type Resolver } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import type { TFunction } from 'i18next'
import { toast } from 'sonner'

function replaceInbound(profile: Profile, index: number, inbound: Inbound): Profile {
  const next = [...profile.inbounds]
  next[index] = inbound
  return { ...profile, inbounds: next }
}

function removeInbound(profile: Profile, index: number): Profile {
  return { ...profile, inbounds: profile.inbounds.filter((_: Inbound, i: number) => i !== index) }
}

function shouldPersistInboundListen(raw: string | undefined): boolean {
  if (raw === undefined) return false
  const t = raw.trim()
  if (t === '' || t === '0.0.0.0' || t === '::' || t === '[::]') return false
  return true
}

function listenAddressForForm(listen: string | undefined): string {
  return shouldPersistInboundListen(listen) ? listen!.trim() : ''
}

const SECURITY_FIELD_PREFIX = 'sec_'
const TRANSPORT_FIELD_PREFIX = 'tr_'

/** Inbound TLS booleans: shown in a 2-column grid after TLS fallbacks (see xray-config-kit `securityFieldOrderByType.tls`). */
const INBOUND_TLS_BOOLEAN_GRID_KEYS = new Set<string>(['allowInsecure', 'enableSessionResumption', 'disableSystemRoot', 'rejectUnknownSni'])

/** Matches outbound DNS-rules / TLS fallbacks sub-accordion chrome. */
const INBOUND_SECURITY_SUBACCORDION_ITEM_CLASS = 'rounded-sm border px-4 [&_[data-state=closed]]:no-underline [&_[data-state=open]]:no-underline'

function securityFieldName(jsonKey: string): string {
  return `${SECURITY_FIELD_PREFIX}${jsonKey}`
}

/** Plain English only — Xray REALITY / TLS / ECH field hints (not i18n). */
const INBOUND_SECURITY_PARITY_PLACEHOLDER: Readonly<Record<string, string>> = {
  dest: 'host:port for REALITY handshake target (e.g. www.microsoft.com:443)',
  serverName: 'TLS SNI (e.g. www.example.com)',
  serverNames: 'One allowed SNI per line',
  privateKey: 'REALITY X25519 private key (base64)',
  publicKey: 'REALITY X25519 public key (base64)',
  shortId: '8 hex chars (optional shortId)',
  shortIds: 'One 8-hex shortId per line',
  fingerprint: 'uTLS fingerprint: chrome, firefox, safari, ios, …',
  spiderX: 'First HTTP request path (often /)',
  minClientVer: 'Minimum Xray-core version string (e.g. 25.9.11)',
  maxTimeDiff: 'Max client time skew in ms (0 = do not check)',
  xver: 'REALITY xver: 0 or 1',
  mldsa65Seed: 'ML-DSA-65 seed (PQ REALITY)',
  mldsa65Verify: 'ML-DSA-65 verify public key',
  pinnedPeerCertificateChainSha256: 'SHA256 fingerprints of peer cert chain (base64, one per line)',
  verifyPeerCertInNames: 'Certificate SAN/CN substring to verify',
  echServerKeys: 'ECH server keys (PEM or base64 per Xray)',
  echConfigList: 'ECH ECHConfigList (base64)',
}

function inboundSecurityParityPlaceholder(jsonKey: string): string | undefined {
  return INBOUND_SECURITY_PARITY_PLACEHOLDER[jsonKey]
}

/** Plain English — common stream settings with VLESS + TLS/REALITY / Vision. */
const INBOUND_TRANSPORT_PARITY_PLACEHOLDER: Readonly<Record<string, string>> = {
  host: 'Host header / WS Host (e.g. cdn.example.com)',
  path: 'Path (e.g. /vless or /ws)',
  serviceName: 'gRPC serviceName',
  authority: 'HTTP/2 :authority (optional)',
  method: 'GET or POST (WS / H2)',
  seed: 'KCP seed string',
  header: 'TCP HTTP obfuscation header JSON (per Xray)',
}

function inboundTransportParityPlaceholder(jsonKey: string): string | undefined {
  return INBOUND_TRANSPORT_PARITY_PLACEHOLDER[jsonKey]
}

function transportFieldName(jsonKey: string): string {
  return `${TRANSPORT_FIELD_PREFIX}${jsonKey}`
}

function normalizeTransportMetaKey(key: string): string {
  return String(key)
    .replace(/[^a-zA-Z0-9]/g, '')
    .toLowerCase()
}

function getTransportMetaValue(transport: Record<string, unknown> | null, normalizedKey: string): unknown {
  if (!transport) return undefined
  for (const [k, v] of Object.entries(transport)) {
    if (normalizeTransportMetaKey(k) === normalizedKey) return v
  }
  return undefined
}

function getXhttpExtraRecord(transport: Record<string, unknown> | null): Record<string, unknown> | null {
  if (!transport) return null
  const extra = transport.extra
  if (extra === undefined || extra === null) return null
  if (typeof extra !== 'object' || Array.isArray(extra)) return null
  return extra as Record<string, unknown>
}

const XHTTP_EXTRA_META_KEYS = new Set<string>([
  'headers',
  'xpaddingbytes',
  'xpaddingobfsmode',
  'xpaddingkey',
  'xpaddingheader',
  'xpaddingplacement',
  'xpaddingmethod',
  'uplinkhttpmethod',
  'sessionplacement',
  'sessionkey',
  'seqplacement',
  'seqkey',
  'uplinkdataplacement',
  'uplinkdatakey',
  'uplinkchunksize',
  'scmaxeachpostbytes',
  'scminpostsintervalms',
  'scmaxbufferedposts',
  'scstreamupserversecs',
  'servermaxheaderbytes',
  'nogrpcheader',
  'nosseheader',
  'xmux',
  'downloadsettings',
])

function isXhttpExtraMetaKey(normalizedKey: string): boolean {
  return XHTTP_EXTRA_META_KEYS.has(normalizedKey)
}

function resolveTransportMetaKey(transport: Record<string, unknown> | null, normalizedKey: string, fallback: string): string {
  if (!transport) return fallback
  for (const k of Object.keys(transport)) {
    if (normalizeTransportMetaKey(k) === normalizedKey) return k
  }
  return fallback
}

/** Reality UI: show Mldsa65Verify, then Mldsa65Seed, then SpiderX (was SpiderX, Mldsa65Seed, Mldsa65Verify). */
function reorderRealitySecurityFieldOrder(order: readonly string[]): string[] {
  const spider = 'spiderX'
  const seed = 'mldsa65Seed'
  const verify = 'mldsa65Verify'
  const iSp = order.indexOf(spider)
  const iSe = order.indexOf(seed)
  const iVe = order.indexOf(verify)
  if (iSp === -1 || iSe === -1 || iVe === -1) return [...order]
  const next = order.filter(k => k !== spider && k !== seed && k !== verify)
  const insertAt = Math.min(iSp, iSe, iVe)
  next.splice(insertAt, 0, verify, seed, spider)
  return next
}

function getInboundTransportRecord(inbound: Inbound): Record<string, unknown> | null {
  if (!('transport' in inbound) || !inbound.transport) return null
  return inbound.transport as unknown as Record<string, unknown>
}

function getInboundSecurityRecord(inbound: Inbound): Record<string, unknown> | null {
  if (!('security' in inbound) || inbound.security?.type === 'none') return null
  return inbound.security as unknown as Record<string, unknown>
}

const VLESS_INBOUND_FLOW_VALUES = ['xtls-rprx-vision'] as const

/** TLS/REALITY on inbound, else form `security` (Flow sits above inbound.security in the grid until moved). */
function effectiveSecurityTypeForVlessInboundFlow(inbound: Inbound | undefined, formSecurity: unknown): string {
  if (inbound && 'security' in inbound && inbound.security && typeof inbound.security === 'object') {
    const ibType = String((inbound.security as { type?: unknown }).type ?? '')
      .trim()
      .toLowerCase()
    if (ibType === 'tls' || ibType === 'reality') return ibType
  }
  const f = typeof formSecurity === 'string' ? formSecurity.trim().toLowerCase() : ''
  if (f === 'tls' || f === 'reality' || f === 'none') return f || 'none'
  return 'none'
}

function effectiveTransportTypeForVlessInboundFlow(inbound: Inbound | undefined): string {
  if (!inbound || !('transport' in inbound) || !inbound.transport) return 'tcp'
  return String((inbound.transport as { type?: unknown }).type ?? 'tcp')
    .trim()
    .toLowerCase() || 'tcp'
}

function vlessInboundEncryptionEnabled(raw: unknown): boolean {
  if (typeof raw !== 'string') return false
  const v = raw.trim().toLowerCase()
  return v !== '' && v !== 'none'
}

function vlessInboundFlowAllowed(input: { securityType: string | undefined; transportType: string | undefined; encryption: unknown }): boolean {
  if (vlessInboundEncryptionEnabled(input.encryption)) return true
  const security = String(input.securityType ?? 'none').trim().toLowerCase()
  const transport = String(input.transportType ?? 'tcp').trim().toLowerCase() || 'tcp'
  return transport === 'tcp' && (security === 'tls' || security === 'reality')
}

function vlessInboundFlowIncompatible(input: { securityType: string | undefined; transportType: string | undefined; encryption: unknown; flow: string | undefined }): boolean {
  const flow = String(input.flow ?? '').trim()
  if (!flow) return false
  if (!(VLESS_INBOUND_FLOW_VALUES as readonly string[]).includes(flow)) return true
  return !vlessInboundFlowAllowed(input)
}

interface TlsCertificateUiItem {
  mode: 'path' | 'content'
  certificateFile: string
  keyFile: string
  certificate: string
  key: string
  ocspStapling: string
  /** PasarGuard / Xray: cert material stays on the node; control plane skips loading for SNI. */
  serveOnNode: boolean
}

const DEFAULT_ECH_SERVER_KEY = 'ACB5YddkGL+db6EvQ8s7E9Z5mb/hwVtBNeRRUHVv88yNHwBT/g0ATwAAIAAgSmNiGX1uHfFDZp8dardrjx4/XiNC3V1lQWLwQBARhGwAJAABAAEAAQACAAEAAwACAAEAAgACAAIAAwADAAEAAwACAAMAAwAAAAA='
const DEFAULT_ECH_CONFIG = 'AFP+DQBPAAAgACBKY2IZfW4d8UNmnx1qt2uPHj9eI0LdXWVBYvBAEBGEbAAkAAEAAQABAAIAAQADAAIAAQACAAIAAgADAAMAAQADAAIAAwADAAAAAA=='

function mutateBase64Seed(seed: string): string {
  try {
    const binary = atob(seed)
    const bytes = Uint8Array.from(binary, c => c.charCodeAt(0))
    if (bytes.length === 0) return seed
    const mutationCount = Math.max(1, Math.floor(bytes.length / 16))
    for (let i = 0; i < mutationCount; i += 1) {
      const idx = Math.floor(Math.random() * bytes.length)
      bytes[idx] = (bytes[idx] + 1 + Math.floor(Math.random() * 255)) % 256
    }
    let out = ''
    for (const b of bytes) out += String.fromCharCode(b)
    return btoa(out)
  } catch {
    return seed
  }
}

function tlsCertificatesForUi(value: unknown): TlsCertificateUiItem[] {
  if (!Array.isArray(value)) return []
  return value
    .map(item => (item && typeof item === 'object' ? (item as Record<string, unknown>) : null))
    .filter((item): item is Record<string, unknown> => item !== null)
    .map(item => {
      const certificateFile = typeof item.certificateFile === 'string' ? item.certificateFile : ''
      const keyFile = typeof item.keyFile === 'string' ? item.keyFile : ''
      const certificate = Array.isArray(item.certificate) ? item.certificate.map(v => String(v)).join('\n') : typeof item.certificate === 'string' ? item.certificate : ''
      const key = Array.isArray(item.key) ? item.key.map(v => String(v)).join('\n') : typeof item.key === 'string' ? item.key : ''
      const hasCertificateField = Object.prototype.hasOwnProperty.call(item, 'certificate')
      const hasKeyField = Object.prototype.hasOwnProperty.call(item, 'key')
      return {
        mode: hasCertificateField || hasKeyField || certificate || key ? ('content' as const) : ('path' as const),
        certificateFile,
        keyFile,
        certificate,
        key,
        ocspStapling: item.ocspStapling === undefined || item.ocspStapling === null ? '' : String(item.ocspStapling),
        serveOnNode: item.serveOnNode === true,
      }
    })
}

function isTcpHttpObfuscationEnabled(raw: unknown): boolean {
  if (typeof raw !== 'string' || raw.trim() === '') return false
  try {
    const parsed = JSON.parse(raw) as unknown
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return false
    const record = parsed as Record<string, unknown>
    return record.type === 'http'
  } catch {
    return false
  }
}

function kitArgsPreservingListenPort(inbound: Inbound): { tag: string; listen?: string; port?: InboundPort } {
  const args: { tag: string; listen?: string; port?: InboundPort } = { tag: inbound.tag ?? '' }
  if ('port' in inbound && inbound.port !== undefined) args.port = inbound.port
  if ('listen' in inbound && shouldPersistInboundListen(inbound.listen)) {
    args.listen = inbound.listen
  }
  return args
}

/** xray-config-kit factory defaults tunnel/dokodemo `network` to tcp; editor default is tcp,udp. */
function applyTunnelEditorCreationDefaults(ib: Inbound): Inbound {
  if (ib.protocol !== 'tunnel' && ib.protocol !== 'dokodemo-door') return ib
  return { ...ib, network: 'tcp,udp' } as Inbound
}

function isMixedLikeInboundProtocol(protocol: string): protocol is 'mixed' | 'socks' {
  return protocol === 'mixed' || protocol === 'socks'
}

function isHttpInboundProtocol(protocol: string): protocol is 'http' {
  return protocol === 'http'
}

function isWireguardInboundProtocol(protocol: string): protocol is 'wireguard' {
  return protocol === 'wireguard'
}

function hasUserPassAccountsProtocol(protocol: string): protocol is 'http' | 'mixed' | 'socks' {
  return isHttpInboundProtocol(protocol) || isMixedLikeInboundProtocol(protocol)
}

/** Mixed/SOCKS editor defaults: switches start OFF in UI. */
function applyMixedLikeEditorCreationDefaults(ib: Inbound): Inbound {
  if (!isMixedLikeInboundProtocol(ib.protocol)) return ib
  return {
    ...ib,
    auth: 'noauth',
    udp: false,
    accounts: undefined,
    ip: typeof (ib as Record<string, unknown>).ip === 'string' ? ((ib as Record<string, unknown>).ip as string) : '127.0.0.1',
  } as Inbound
}

/** HTTP editor defaults: switches start OFF in UI. */
function applyHttpEditorCreationDefaults(ib: Inbound): Inbound {
  if (!isHttpInboundProtocol(ib.protocol)) return ib
  return {
    ...ib,
    allowTransparent: false,
    accounts: undefined,
  } as Inbound
}

/** TUN editor defaults: keep name/mtu, clear optional auto-filled lists/iface. */
function applyTunEditorCreationDefaults(ib: Inbound): Inbound {
  if (ib.protocol !== 'tun') return ib
  return {
    ...ib,
    gateway: undefined,
    dns: undefined,
    autoSystemRoutingTable: undefined,
    autoOutboundsInterface: undefined,
  } as Inbound
}

/** WireGuard editor defaults: do not prefill key/peer fields. */
function applyWireguardEditorCreationDefaults(ib: Inbound): Inbound {
  if (ib.protocol !== 'wireguard') return ib
  return {
    ...ib,
    secretKey: '',
    publicKey: undefined,
    peers: [],
  } as Inbound
}

/** When user switches protocol to wireguard, generate inbound secret key immediately. */
function applyWireguardGeneratedSecretOnCreate(ib: Inbound): Inbound {
  if (ib.protocol !== 'wireguard') return ib
  const currentSecret = typeof (ib as { secretKey?: unknown }).secretKey === 'string' ? String((ib as { secretKey?: unknown }).secretKey).trim() : ''
  if (currentSecret !== '') return ib
  const keyPair = generateWireGuardKeyPair()
  return { ...ib, secretKey: keyPair.privateKey } as Inbound
}

function applyInboundEditorCreationDefaults(ib: Inbound): Inbound {
  return applyWireguardGeneratedSecretOnCreate(
    applyWireguardEditorCreationDefaults(applyTunEditorCreationDefaults(applyHttpEditorCreationDefaults(applyMixedLikeEditorCreationDefaults(applyTunnelEditorCreationDefaults(ib))))),
  )
}

function formatInboundPort(ib: Inbound): string {
  if (!('port' in ib) || ib.port === undefined) return '—'
  return typeof ib.port === 'object' ? JSON.stringify(ib.port) : String(ib.port)
}

function inboundSearchHaystack(ib: Inbound): string {
  const proto = ib.protocol === 'dokodemo-door' ? `${ib.protocol} tunnel` : ib.protocol === 'tunnel' ? `${ib.protocol} dokodemo-door` : ib.protocol
  return [ib.tag, proto, formatInboundPort(ib)].join(' ')
}

/** Tunnel inbound (formerly `dokodemo-door`). */
function isTunnelInboundProtocol(protocol: string): boolean {
  return protocol === 'tunnel' || protocol === 'dokodemo-door'
}

function userPassAccountsForUi(inbound: Inbound): Array<{ user: string; pass: string }> {
  if (!hasUserPassAccountsProtocol(inbound.protocol)) return []
  const raw = (inbound as { accounts?: unknown }).accounts
  if (!Array.isArray(raw)) return []
  return raw
    .map(item => (item && typeof item === 'object' && !Array.isArray(item) ? (item as Record<string, unknown>) : null))
    .filter((item): item is Record<string, unknown> => item !== null)
    .map(item => ({
      user: typeof item.user === 'string' ? item.user : '',
      pass: typeof item.pass === 'string' ? item.pass : '',
    }))
}

/** First peer → 10.0.0.2/32, second → 10.0.0.3/32, … (caps last octet at 254). */
function wireguardDefaultAllowedIpsForNewPeer(index: number): string[] {
  const last = Math.min(2 + index, 254)
  return [`10.0.0.${last}/32`]
}

/** Matches common xray / kit WG template: exactly IPv4 + IPv6 default routes (no extras). */
function isLikelyWireguardKitCatchAllAllowedIps(ips: string[]): boolean {
  const set = new Set(ips.map(s => String(s).trim()).filter(Boolean))
  if (set.size !== 2) return false
  const has4 = set.has('0.0.0.0/0')
  const has6 = set.has('::/0') || set.has('0::/0')
  return has4 && has6
}

function wireguardPeersForUi(inbound: Inbound): Array<{ publicKey: string; preSharedKey?: string; allowedIPs: string[] }> {
  if (!isWireguardInboundProtocol(inbound.protocol)) return []
  const raw = (inbound as { peers?: unknown }).peers
  if (!Array.isArray(raw)) return []
  return raw
    .map(item => (item && typeof item === 'object' && !Array.isArray(item) ? (item as Record<string, unknown>) : null))
    .filter((item): item is Record<string, unknown> => item !== null)
    .map(item => ({
      publicKey: typeof item.publicKey === 'string' ? item.publicKey : '',
      preSharedKey: typeof item.preSharedKey === 'string' && item.preSharedKey.trim() !== '' ? item.preSharedKey : undefined,
      allowedIPs: Array.isArray(item.allowedIPs) ? item.allowedIPs.map(v => String(v).trim()).filter(Boolean) : [],
    }))
}

function generateMixedAccountUsername(length: number = 10): string {
  const charset = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
  let out = ''
  for (let i = 0; i < length; i += 1) {
    out += charset[getRandomInt(charset.length)]
  }
  return out
}

function generateMixedAccountCredentials(): { user: string; pass: string } {
  return {
    user: generateMixedAccountUsername(10),
    pass: generatePassword(10),
  }
}

const INBOUND_PROTOCOL_PREFERRED_ORDER: readonly string[] = ['vless', 'vmess', 'trojan', 'shadowsocks', 'hysteria', 'mixed', 'tunnel', 'socks', 'http', 'tun']

function sortInboundProtocolsForUi(protocols: readonly string[]): string[] {
  const preferredSet = new Set(INBOUND_PROTOCOL_PREFERRED_ORDER)
  const preferred = INBOUND_PROTOCOL_PREFERRED_ORDER.filter(p => protocols.includes(p))
  const others = protocols.filter(p => !preferredSet.has(p))
  return [...preferred, ...others]
}

function stringListFromUnknown(value: unknown): string[] {
  if (!Array.isArray(value)) return []
  return value.map(item => String(item).trim()).filter(Boolean)
}

function formatInboundProtocolForUi(protocol: string, tt: TFunction): string {
  if (protocol === 'dokodemo-door') return tt('coreEditor.inbound.protocolDokodemoDoor', { defaultValue: 'dokodemo-door (legacy)' })
  return protocol
}

function tunnelLegacySettingsRecord(inbound: Inbound): Record<string, unknown> {
  const s = (inbound as Record<string, unknown>).settings
  return s !== null && typeof s === 'object' && !Array.isArray(s) ? (s as Record<string, unknown>) : {}
}

/** Kit canonical field `address` (Xray imports `settings.address`). */
function tunnelAddressForForm(inbound: Inbound): string {
  const r = inbound as Record<string, unknown>
  if (typeof r.address === 'string') {
    const t = r.address.trim()
    return t !== '' && !isPlaceholderTunnelRewriteAddress(t) ? t : ''
  }
  const s = tunnelLegacySettingsRecord(inbound)
  const v = s.rewriteAddress ?? s.address
  if (typeof v === 'string') {
    const t = v.trim()
    return t !== '' && !isPlaceholderTunnelRewriteAddress(t) ? v : ''
  }
  return v != null ? String(v) : ''
}

/** Kit canonical field `targetPort` (Xray imports `settings.port`). */
function tunnelTargetPortForForm(inbound: Inbound): string {
  const r = inbound as Record<string, unknown>
  const tp = r.targetPort
  if (tp !== undefined && tp !== null && tp !== '') return String(tp)
  const s = tunnelLegacySettingsRecord(inbound)
  const v = s.rewritePort ?? s.port
  if (v === undefined || v === null || v === '') return ''
  return String(v)
}

/** Kit canonical field `network` (tcp | udp | tcp,udp). */
function tunnelNetworkSelectValue(inbound: Inbound): string {
  const r = inbound as Record<string, unknown>
  const top = r.network
  if (typeof top === 'string') return normalizeTunnelNetworkForKit(top)
  const s = tunnelLegacySettingsRecord(inbound)
  const fromLegacy = s.network ?? s.allowedNetwork
  if (typeof fromLegacy === 'string') return normalizeTunnelNetworkForKit(fromLegacy)
  return normalizeTunnelNetworkForKit(undefined)
}

function tunnelFollowRedirectForForm(inbound: Inbound): string {
  const r = inbound as Record<string, unknown>
  if (typeof r.followRedirect === 'boolean') return r.followRedirect ? 'true' : 'false'
  const s = tunnelLegacySettingsRecord(inbound)
  return s.followRedirect === true || s.followRedirect === 'true' ? 'true' : 'false'
}

/** Reads kit `portMap` first; falls back to legacy raw patch or `settings.portMap` until sanitize runs. */
function tunnelPortMapFromInbound(inbound: Inbound): Record<string, string> | null {
  const r = inbound as Record<string, unknown>
  const top = r.portMap
  if (top && typeof top === 'object' && !Array.isArray(top)) {
    const out: Record<string, string> = {}
    for (const [k, v] of Object.entries(top as Record<string, unknown>)) out[k] = v != null ? String(v) : ''
    return Object.keys(out).length ? out : null
  }
  const raw = Array.isArray(r.raw) ? r.raw : []
  for (const p of raw) {
    if (p && typeof p === 'object' && !Array.isArray(p) && (p as { path?: string }).path === '/settings/portMap') {
      const value = (p as { value?: unknown }).value
      if (value && typeof value === 'object' && !Array.isArray(value)) {
        const out: Record<string, string> = {}
        for (const [k, v] of Object.entries(value as Record<string, unknown>)) out[k] = v != null ? String(v) : ''
        return out
      }
    }
  }
  const legacy = tunnelLegacySettingsRecord(inbound).portMap
  if (legacy && typeof legacy === 'object' && !Array.isArray(legacy)) {
    const out: Record<string, string> = {}
    for (const [k, v] of Object.entries(legacy as Record<string, unknown>)) out[k] = v != null ? String(v) : ''
    return Object.keys(out).length ? out : null
  }
  return null
}

function readTunnelPortMapRowsFromInbound(inbound: Inbound): { listenPort: string; target: string }[] {
  const pm = tunnelPortMapFromInbound(inbound)
  if (!pm) return []
  return Object.entries(pm)
    .sort((a, b) => {
      const na = Number.parseInt(a[0], 10)
      const nb = Number.parseInt(b[0], 10)
      if (Number.isFinite(na) && Number.isFinite(nb)) return na - nb
      return a[0].localeCompare(b[0])
    })
    .map(([listenPort, target]) => ({ listenPort, target: target != null ? String(target) : '' }))
}

function cloneInbound(inbound: Inbound): Inbound {
  return JSON.parse(JSON.stringify(inbound)) as Inbound
}

function getRandomInt(max: number): number {
  const array = new Uint32Array(1)
  window.crypto.getRandomValues(array)
  return array[0] % max
}

function generatePassword(length: number = 24): string {
  const letters = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ'
  const numbers = '0123456789'
  const special = '_'
  let password = special

  for (let i = 1; i < length; i++) {
    const charSet = getRandomInt(10) < 7 ? letters : numbers
    const randomIndex = getRandomInt(charSet.length)
    password += charSet[randomIndex]
  }

  const arr = password.split('')
  for (let i = arr.length - 1; i > 0; i--) {
    const j = getRandomInt(i + 1)
    ;[arr[i], arr[j]] = [arr[j], arr[i]]
  }
  return arr.join('')
}

function vlessInboundFlowForForm(row: Inbound): string {
  if (row.protocol !== 'vless') return ''
  const r = row as Record<string, unknown>
  const top = r.flow
  if (typeof top === 'string') return top.trim()
  const s = r.settings
  if (s && typeof s === 'object' && !Array.isArray(s)) {
    const f = (s as Record<string, unknown>).flow
    if (typeof f === 'string') return f.trim()
  }
  return ''
}

function syncVlessFieldsFromInboundForm(form: { setValue: (n: string, v: string) => void }, row: Inbound) {
  if (row.protocol !== 'vless') return
  form.setValue('encryption', vlessInboundEncryptionRawForForm(row as { protocol: string; encryption?: string }) || 'none')
  form.setValue('vlessEncryptionMethod', vlessInboundEncryptionMethodForForm(row as { protocol: string; encryption?: string }))
  form.setValue('decryption', 'decryption' in row ? (row.decryption ?? '') : '')
  form.setValue('vlessFlow', vlessInboundFlowForForm(row))
}

function inboundSupportsTlsFallbacksModel(next: Inbound): boolean {
  return 'transport' in next && next.transport?.type === 'tcp' && 'security' in next && next.security?.type === 'tls'
}

function mergeVlessInboundStreamFields(prev: Inbound, next: Inbound): Inbound {
  if (prev.protocol !== 'vless' || next.protocol !== 'vless') return next
  const p = prev as { encryption?: string; decryption?: string; flow?: string; fallbacks?: Fallback[] }
  const merged = { ...next } as { encryption?: string; decryption?: string; flow?: string; fallbacks?: Fallback[] }
  if (p.encryption !== undefined) merged.encryption = p.encryption
  if (p.decryption !== undefined) merged.decryption = p.decryption
  if (p.flow !== undefined) merged.flow = p.flow
  if (p.fallbacks !== undefined && p.fallbacks.length > 0 && inboundSupportsTlsFallbacksModel(next)) {
    merged.fallbacks = p.fallbacks
  }
  return merged as Inbound
}

function mergeTrojanInboundStreamFields(prev: Inbound, next: Inbound): Inbound {
  if (prev.protocol !== 'trojan' || next.protocol !== 'trojan') return next
  const p = prev as { fallbacks?: Fallback[] }
  const merged = { ...next } as { fallbacks?: Fallback[] }
  if (p.fallbacks !== undefined && p.fallbacks.length > 0 && inboundSupportsTlsFallbacksModel(next)) {
    merged.fallbacks = p.fallbacks
  }
  return merged as Inbound
}

function shadowsocksMethodFormValue(row: Inbound): string {
  if (row.protocol !== 'shadowsocks') return SHADOWSOCKS_ENCRYPTION_METHODS[0].value
  const m = 'method' in row ? row.method : undefined
  if (m === undefined || String(m).trim() === '') return SHADOWSOCKS_ENCRYPTION_METHODS[0].value
  return String(m)
}

function shadowsocksPasswordFormValue(row: Inbound): string {
  if (row.protocol !== 'shadowsocks') return ''
  const p = 'password' in row ? row.password : undefined
  return p === undefined || p === null ? '' : String(p)
}

/** Kit / Xray parity: top-level `network` (tcp | udp | tcp,udp), same normalization as tunnel. */
function shadowsocksNetworkFormValue(row: Inbound): 'tcp' | 'udp' | 'tcp,udp' {
  if (row.protocol !== 'shadowsocks') return 'tcp,udp'
  const r = row as Record<string, unknown>
  const nw = r.network
  if (Array.isArray(nw)) {
    const parts = nw.map(v => String(v).trim().toLowerCase()).filter(Boolean)
    if (parts.includes('tcp') && parts.includes('udp')) return 'tcp,udp'
    if (parts.includes('udp') && !parts.includes('tcp')) return 'udp'
    if (parts.includes('tcp')) return 'tcp'
    return 'tcp,udp'
  }
  return normalizeTunnelNetworkForKit(nw)
}

function mergeShadowsocksInboundStreamFields(prev: Inbound, next: Inbound): Inbound {
  if (prev.protocol !== 'shadowsocks' || next.protocol !== 'shadowsocks') return next
  const p = prev as { method?: string; password?: string; network?: string | string[] }
  const merged = { ...next } as { method?: string; password?: string; network?: string | string[] }
  if (p.method !== undefined) merged.method = p.method
  if (p.password !== undefined) merged.password = p.password
  if (p.network !== undefined) merged.network = p.network
  return merged as Inbound
}

function mergeSecurityAcrossRebuild(prev: Inbound, next: Inbound): Inbound {
  if (!('security' in prev) || !prev.security || !('security' in next) || !next.security) return next
  if (prev.security.type !== next.security.type) return next
  return { ...next, security: prev.security } as Inbound
}

function mergeTransportAcrossRebuild(prev: Inbound, next: Inbound): Inbound {
  if (!('transport' in prev) || !prev.transport || !('transport' in next) || !next.transport) return next
  if (prev.transport.type !== next.transport.type) return next
  return { ...next, transport: prev.transport } as Inbound
}

function mergeStreamAdvancedAcrossRebuild(prev: Inbound, next: Inbound): Inbound {
  if (next.protocol === 'unmanaged' || next.protocol === 'tun') return next
  const streamAdvanced = (prev as { streamAdvanced?: unknown }).streamAdvanced
  if (!streamAdvanced || typeof streamAdvanced !== 'object' || Array.isArray(streamAdvanced)) return next
  return { ...next, streamAdvanced } as Inbound
}

const SNIFFING_DEST_OVERRIDE_OPTIONS = ['http', 'tls', 'quic', 'fakedns'] as const

/** Grid for tunnel `portMap` editor rows (index, local port, remote target, actions). */
const TUNNEL_PORT_MAP_ROW_GRID = 'sm:grid sm:grid-cols-[2.5rem_minmax(6rem,8.5rem)_minmax(0,1fr)_2.5rem] sm:items-center sm:gap-x-2'

function parseSniffingDestOverride(value: unknown): string[] {
  if (Array.isArray(value)) return value.map(v => String(v).toLowerCase())
  if (typeof value !== 'string' || value.trim() === '') return []
  try {
    const parsed = JSON.parse(value) as unknown
    return Array.isArray(parsed) ? parsed.map(v => String(v).toLowerCase()) : []
  } catch {
    return []
  }
}

type DialogMode = 'add' | 'edit'
type InboundDialogFormValues = Record<string, string>

interface XrayInboundsSectionProps {
  headerAddPulse?: SectionHeaderAddPulse
  headerAddEpoch?: number
}

export function XrayInboundsSection({ headerAddPulse, headerAddEpoch }: XrayInboundsSectionProps) {
  const { t } = useTranslation()
  const dir = useDirDetection()
  const profile = useCoreEditorStore(s => s.xrayProfile)
  const updateXrayProfile = useCoreEditorStore(s => s.updateXrayProfile)
  const { assertNoPersistBlockingErrors } = useXrayPersistModifyGuard()
  const [selected, setSelected] = useState(0)
  const [detailOpen, setDetailOpen] = useState(false)
  const [dialogMode, setDialogMode] = useState<DialogMode>('edit')
  const [isGeneratingRealityKeyPair, setIsGeneratingRealityKeyPair] = useState(false)
  const [isGeneratingRealityShortId, setIsGeneratingRealityShortId] = useState(false)
  const [isGeneratingMldsa65, setIsGeneratingMldsa65] = useState(false)
  const [echUsageOption, setEchUsageOption] = useState<'default' | 'required' | 'preferred'>('default')
  const [draftInbound, setDraftInbound] = useState<Inbound | null>(null)
  const [editOriginalInbound, setEditOriginalInbound] = useState<Inbound | null>(null)
  const [discardDraftOpen, setDiscardDraftOpen] = useState(false)
  const [discardEditOpen, setDiscardEditOpen] = useState(false)
  const [blockAddWhileDraftOpen, setBlockAddWhileDraftOpen] = useState(false)
  const [isGeneratingShadowsocksPassword, setIsGeneratingShadowsocksPassword] = useState(false)
  const [shadowsocksPasswordJustGenerated, setShadowsocksPasswordJustGenerated] = useState(false)
  const [vlessDecryptionJustGenerated, setVlessDecryptionJustGenerated] = useState(false)
  const [vlessAdvancedOpen, setVlessAdvancedOpen] = useState(false)
  const [vlessAdvancedSeed, setVlessAdvancedSeed] = useState<VlessBuilderOptions | undefined>(undefined)
  const [tunnelBlankPortMapRows, setTunnelBlankPortMapRows] = useState<{ listenPort: string; target: string }[]>([])
  const [wireguardPeerPrivateKeys, setWireguardPeerPrivateKeys] = useState<Record<number, string>>({})
  const tunnelBlankPortMapRowsRef = useRef(tunnelBlankPortMapRows)
  tunnelBlankPortMapRowsRef.current = tunnelBlankPortMapRows

  const patchInboundRef = useRef<((patch: Partial<Inbound>) => void) | undefined>(undefined)
  const wireguardKitAllowedMigrateKeyRef = useRef<string | null>(null)

  const inbound = useMemo(() => {
    if (!profile) return undefined
    if (dialogMode === 'add' && draftInbound) return draftInbound
    return profile.inbounds[selected]
  }, [profile, dialogMode, draftInbound, selected])

  const visibility = useMemo(() => (inbound ? getInboundFieldVisibility(inbound) : null), [inbound])
  const caps = useMemo(() => getInboundFormCapabilities(), [])
  const protocolSelectOptions = useMemo(() => {
    const visibleProtocols = caps.protocolOrder.filter(p => caps.protocols[p] && p !== 'dokodemo-door')
    // Keep legacy value selectable when editing an existing legacy inbound.
    if (inbound?.protocol === 'dokodemo-door' && !visibleProtocols.includes('dokodemo-door')) {
      visibleProtocols.push('dokodemo-door')
    }
    return sortInboundProtocolsForUi(visibleProtocols)
  }, [caps, inbound?.protocol])
  const tunnelCommittedPortMapRows = useMemo(() => {
    if (!inbound || !isTunnelInboundProtocol(inbound.protocol)) return []
    return readTunnelPortMapRowsFromInbound(inbound)
  }, [inbound])

  const transportSelectOptions = useMemo(() => {
    if (!inbound || inbound.protocol === 'unmanaged') return []
    if (!('transport' in inbound) || !inbound.transport) return []
    const securityType = 'security' in inbound ? inbound.security?.type : undefined
    return getInboundTransportSelectOptions(caps, {
      protocol: inbound.protocol,
      securityType,
      currentTransportType: inbound.transport.type,
    })
  }, [caps, inbound])

  const securitySelectOptions = useMemo(() => {
    if (!inbound || inbound.protocol === 'unmanaged') return []
    return getInboundSecuritySelectOptions(caps, inbound.protocol)
  }, [caps, inbound])

  const inboundDialogSchema = useMemo(() => createInboundDialogSchema(caps, t), [caps, t])

  const form = useForm<InboundDialogFormValues>({
    resolver: zodResolver(inboundDialogSchema) as unknown as Resolver<InboundDialogFormValues>,
    defaultValues: {
      protocol: 'vless',
      tag: '',
      listen: '',
      port: '',
      vlessEncryptionMethod: 'none',
      encryption: 'none',
      decryption: '',
      vlessFlow: '',
      shadowsocksMethod: SHADOWSOCKS_ENCRYPTION_METHODS[0].value,
      shadowsocksPassword: '',
      shadowsocksNetwork: 'tcp,udp',
      transport: 'tcp',
      security: 'none',
      tunnelRewriteAddress: '',
      tunnelRewritePort: '',
      tunnelAllowedNetwork: 'tcp,udp',
      tunnelFollowRedirect: 'true',
      tunName: '',
      tunMtu: '',
      wgSecretKey: '',
      wgMtu: '',
    },
    // `onSubmit`: REALITY rules use `superRefine` on the whole form — with `onTouched`, focusing
    // e.g. Security runs the resolver once and surfaces every REALITY field error at once. With
    // `onSubmit`, errors appear when saving; then `reValidateMode: 'onChange'` clears them as values are fixed.
    mode: 'onSubmit',
    reValidateMode: 'onChange',
  })

  const syncOpts = { shouldValidate: false, shouldDirty: false } as const

  /** `reValidateMode: 'onChange'` only runs after `isSubmitted`; we use `trigger()` on save, not `handleSubmit`, so re-run REALITY checks when those fields change. */
  const revalidateRealityInboundForm = useCallback(() => {
    if (form.getValues('security') !== 'reality') return
    void form.trigger(realityInboundZodTriggerFieldNames())
  }, [form])

  const syncTunnelFormFieldsFromInbound = useCallback(
    (nextIb: Inbound) => {
      if (!isTunnelInboundProtocol(nextIb.protocol)) {
        form.setValue('tunnelRewriteAddress', '', syncOpts)
        form.setValue('tunnelRewritePort', '', syncOpts)
        form.setValue('tunnelAllowedNetwork', 'tcp,udp', syncOpts)
        form.setValue('tunnelFollowRedirect', 'true', syncOpts)
        return
      }
      form.setValue('tunnelRewriteAddress', tunnelAddressForForm(nextIb), syncOpts)
      form.setValue('tunnelRewritePort', tunnelTargetPortForForm(nextIb), syncOpts)
      form.setValue('tunnelAllowedNetwork', tunnelNetworkSelectValue(nextIb), syncOpts)
      form.setValue('tunnelFollowRedirect', tunnelFollowRedirectForForm(nextIb), syncOpts)
    },
    [form],
  )

  const syncTunFormFieldsFromInbound = useCallback(
    (nextIb: Inbound) => {
      if (nextIb.protocol !== 'tun') {
        form.setValue('tunName', '', syncOpts)
        form.setValue('tunMtu', '', syncOpts)
        return
      }
      form.setValue('tunName', typeof (nextIb as { name?: unknown }).name === 'string' ? String((nextIb as { name?: unknown }).name) : '', syncOpts)
      form.setValue('tunMtu', typeof (nextIb as { mtu?: unknown }).mtu === 'number' ? String((nextIb as { mtu?: number }).mtu) : '', syncOpts)
    },
    [form],
  )

  const syncWireguardFormFieldsFromInbound = useCallback(
    (nextIb: Inbound) => {
      if (nextIb.protocol !== 'wireguard') {
        form.setValue('wgSecretKey', '', syncOpts)
        form.setValue('wgMtu', '', syncOpts)
        return
      }
      form.setValue('wgSecretKey', typeof (nextIb as { secretKey?: unknown }).secretKey === 'string' ? String((nextIb as { secretKey?: unknown }).secretKey) : '', syncOpts)
      form.setValue('wgMtu', typeof (nextIb as { mtu?: unknown }).mtu === 'number' ? String((nextIb as { mtu?: number }).mtu) : '', syncOpts)
    },
    [form],
  )

  const profileRef = useRef(profile)
  profileRef.current = profile

  useEffect(() => {
    if (!detailOpen) return
    const p = profileRef.current
    if (!p) return
    const row = dialogMode === 'add' && draftInbound ? draftInbound : p.inbounds[selected]
    if (!row || row.protocol === 'unmanaged') return

    const security = getInboundSecurityRecord(row)
    const sniffing = 'sniffing' in row && row.sniffing && typeof row.sniffing === 'object' && !Array.isArray(row.sniffing) ? (row.sniffing as Record<string, unknown>) : null
    const securityType = security?.type
    const securityOrder = typeof securityType === 'string' ? (caps.securityFieldOrderByType[securityType] ?? []) : []

    const next: InboundDialogFormValues = {
      protocol: row.protocol,
      tag: row.tag,
      listen: listenAddressForForm(row.listen),
      port: 'port' in row && row.port !== undefined ? String(row.port) : '',
      vlessEncryptionMethod: vlessInboundEncryptionMethodForForm(row),
      encryption: vlessInboundEncryptionRawForForm(row) || 'none',
      decryption: 'decryption' in row ? (row.decryption ?? '') : '',
      vlessFlow: vlessInboundFlowForForm(row),
      shadowsocksMethod: shadowsocksMethodFormValue(row),
      shadowsocksPassword: shadowsocksPasswordFormValue(row),
      shadowsocksNetwork: shadowsocksNetworkFormValue(row),
      hysteriaAuth:
        row.protocol === 'hysteria'
          ? (row.clients.find(client => client.protocol === 'hysteria')?.auth ?? (row.transport.type === 'hysteria' && typeof row.transport.auth === 'string' ? row.transport.auth : ''))
          : '',
      hysteriaUdpIdleTimeout: row.protocol === 'hysteria' && row.transport.type === 'hysteria' && row.transport.udpIdleTimeout !== undefined ? String(row.transport.udpIdleTimeout) : '',
      hysteriaMasqueradeType: row.protocol === 'hysteria' && row.transport.type === 'hysteria' && row.transport.masquerade?.type ? String(row.transport.masquerade.type) : '__none',
      hysteriaMasqueradeDir: row.protocol === 'hysteria' && row.transport.type === 'hysteria' && typeof row.transport.masquerade?.dir === 'string' ? row.transport.masquerade.dir : '',
      hysteriaMasqueradeUrl: row.protocol === 'hysteria' && row.transport.type === 'hysteria' && typeof row.transport.masquerade?.url === 'string' ? row.transport.masquerade.url : '',
      hysteriaMasqueradeRewriteHost: row.protocol === 'hysteria' && row.transport.type === 'hysteria' && row.transport.masquerade?.rewriteHost ? 'true' : 'false',
      hysteriaMasqueradeInsecure: row.protocol === 'hysteria' && row.transport.type === 'hysteria' && row.transport.masquerade?.insecure ? 'true' : 'false',
      hysteriaMasqueradeContent: row.protocol === 'hysteria' && row.transport.type === 'hysteria' && typeof row.transport.masquerade?.content === 'string' ? row.transport.masquerade.content : '',
      hysteriaMasqueradeHeaders:
        row.protocol === 'hysteria' && row.transport.type === 'hysteria' && row.transport.masquerade?.headers && typeof row.transport.masquerade.headers === 'object'
          ? JSON.stringify(row.transport.masquerade.headers, null, 2)
          : '',
      hysteriaMasqueradeStatusCode:
        row.protocol === 'hysteria' && row.transport.type === 'hysteria' && typeof row.transport.masquerade?.statusCode === 'number' ? String(row.transport.masquerade.statusCode) : '',
      sniffingEnabled: sniffing?.enabled ? 'true' : 'false',
      sniffingDestOverride: JSON.stringify(parseSniffingDestOverride(sniffing?.destOverride)),
      sniffingMetadataOnly: sniffing?.metadataOnly ? 'true' : 'false',
      sniffingRouteOnly: sniffing?.routeOnly ? 'true' : 'false',
      transport: 'transport' in row && row.transport ? row.transport.type : 'tcp',
      security: 'security' in row && row.security ? row.security.type : 'none',
      tunName: row.protocol === 'tun' && typeof (row as { name?: unknown }).name === 'string' ? String((row as { name?: unknown }).name) : '',
      tunMtu: row.protocol === 'tun' && typeof (row as { mtu?: unknown }).mtu === 'number' ? String((row as { mtu?: number }).mtu) : '',
      wgSecretKey: row.protocol === 'wireguard' && typeof (row as { secretKey?: unknown }).secretKey === 'string' ? String((row as { secretKey?: unknown }).secretKey) : '',
      wgMtu: row.protocol === 'wireguard' && typeof (row as { mtu?: unknown }).mtu === 'number' ? String((row as { mtu?: number }).mtu) : '',
      ...(isTunnelInboundProtocol(row.protocol)
        ? {
            tunnelRewriteAddress: tunnelAddressForForm(row),
            tunnelRewritePort: tunnelTargetPortForForm(row),
            tunnelAllowedNetwork: tunnelNetworkSelectValue(row),
            tunnelFollowRedirect: tunnelFollowRedirectForForm(row),
          }
        : {
            tunnelRewriteAddress: '',
            tunnelRewritePort: '',
            tunnelAllowedNetwork: 'tcp,udp',
            tunnelFollowRedirect: 'true',
          }),
    }

    for (const key of securityOrder) {
      const def = caps.securityFieldDefinitions[String(securityType)]?.[key]
      if (def) next[securityFieldName(key)] = outboundSettingToString(security?.[key], def)
    }

    if (securityType === 'tls' && security?.echSockopt) {
      const ech = security.echSockopt as Record<string, unknown>
      if (typeof ech.serverKeys === 'string') next[securityFieldName('echServerKeys')] = ech.serverKeys
      if (typeof ech.configList === 'string') next[securityFieldName('echConfigList')] = ech.configList
      if (typeof ech.forceQuery === 'string') next[securityFieldName('echForceQuery')] = ech.forceQuery
    }

    const tr = 'transport' in row && row.transport ? row.transport : null
    const transportType = tr?.type
    if (transportType) {
      const transportOrder = caps.transportSettingsFieldOrderByType[transportType] ?? []
      const trRec = getInboundTransportRecord(row)
      const trExtra = transportType === 'xhttp' ? getXhttpExtraRecord(trRec) : null
      for (const key of transportOrder) {
        const def = caps.transportSettingsFieldDefinitions[transportType]?.[key]
        const normalizedKey = normalizeTransportMetaKey(key)
        const transportValue = transportType === 'xhttp' && isXhttpExtraMetaKey(normalizedKey) ? getTransportMetaValue(trExtra, normalizedKey) : trRec?.[key]
        if (def) {
          if (isJsonRawMessageField(def)) {
            if (dialogMode === 'add') {
              // In add mode, preserve user's input if they've set a value, otherwise default to empty
              const fieldName = transportFieldName(key)
              const currentValue = form.getValues(fieldName)
              if (currentValue && typeof currentValue === 'string' && currentValue.trim() !== '') {
                // User has explicitly set a value, preserve it
                next[fieldName] = currentValue
              } else {
                // No explicit value set, default to empty (OFF for switches)
                next[fieldName] = ''
              }
            } else {
              next[transportFieldName(key)] = outboundSettingToString(transportValue, def)
            }
          } else {
            next[transportFieldName(key)] = outboundSettingToString(transportValue, def)
          }
        }
      }
    }

    form.reset(next, { keepErrors: false, keepTouched: false, keepDirty: false })
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `form.reset` is stable; listing `form` re-runs sync every render.
  }, [caps, detailOpen, selected, dialogMode, draftInbound])

  useEffect(() => {
    if (!detailOpen) return
    const p = profileRef.current
    if (!p) return
    const row = dialogMode === 'add' && draftInbound ? draftInbound : p.inbounds[selected]
    if (row && isTunnelInboundProtocol(row.protocol)) setTunnelBlankPortMapRows([])
  }, [detailOpen, selected, dialogMode, draftInbound])

  useEffect(() => {
    if (inbound?.protocol !== 'wireguard') {
      setWireguardPeerPrivateKeys({})
    }
  }, [inbound?.protocol])

  const columns = useMemo<ColumnDef<Inbound, unknown>[]>(
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
        cell: ({ row }) => formatInboundProtocolForUi(row.original.protocol, t),
      },
      {
        id: 'port',
        header: () => t('coreEditor.col.port', { defaultValue: 'Port' }),
        cell: ({ row }) => formatInboundPort(row.original),
      },
    ],
    [t],
  )

  const beginAddInbound = useCallback(() => {
    if (!profile) return
    if (detailOpen && dialogMode === 'add' && draftInbound !== null) {
      setBlockAddWhileDraftOpen(true)
      return
    }
    const created = createDefaultInbound({
      protocol: 'vless',
      transport: 'tcp',
      security: 'none',
      clientDefaults: 'empty',
    })
    setDraftInbound(created)
    setDialogMode('add')
    setDetailOpen(true)
  }, [profile, detailOpen, dialogMode, draftInbound])

  useSectionHeaderAddPulseEffect(headerAddPulse, headerAddEpoch, 'inbounds', beginAddInbound)

  const inboundSecurity = useMemo(() => (inbound ? getInboundSecurityRecord(inbound) : null), [inbound])
  const inboundSecurityType = useMemo(() => (typeof inboundSecurity?.type === 'string' ? inboundSecurity.type : undefined), [inboundSecurity])
  const vlessStoredFlow = useMemo(() => (inbound && inbound.protocol === 'vless' ? vlessInboundFlowForForm(inbound) : ''), [inbound])
  const watchedInboundSecurity = form.watch('security')
  const watchedVlessEncryption = form.watch('encryption')
  const securityForVlessInboundFlow = useMemo(() => effectiveSecurityTypeForVlessInboundFlow(inbound, watchedInboundSecurity), [inbound, watchedInboundSecurity])
  const transportForVlessInboundFlow = useMemo(() => effectiveTransportTypeForVlessInboundFlow(inbound), [inbound])
  const vlessInboundFlowsOk = useMemo(
    () =>
      vlessInboundFlowAllowed({
        securityType: securityForVlessInboundFlow,
        transportType: transportForVlessInboundFlow,
        encryption: watchedVlessEncryption,
      }),
    [securityForVlessInboundFlow, transportForVlessInboundFlow, watchedVlessEncryption],
  )
  const tlsCertificates = useMemo(
    () => (inboundSecurityType === 'tls' ? tlsCertificatesForUi((inboundSecurity as Record<string, unknown> | null)?.certificates) : []),
    [inboundSecurityType, inboundSecurity],
  )
  const securityFieldOrder = useMemo(() => {
    if (!inboundSecurityType) return []
    const order = caps.securityFieldOrderByType[inboundSecurityType] ?? []
    const defs = caps.securityFieldDefinitions[inboundSecurityType]
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
  }, [inboundSecurityType, caps])
  const displaySecurityFieldOrder = useMemo(
    () => (inboundSecurityType === 'reality' ? reorderRealitySecurityFieldOrder(securityFieldOrder) : securityFieldOrder),
    [inboundSecurityType, securityFieldOrder],
  )
  const displaySecurityFieldOrderMain = useMemo(
    () => (inboundSecurityType === 'tls' ? displaySecurityFieldOrder.filter(k => !INBOUND_TLS_BOOLEAN_GRID_KEYS.has(k)) : displaySecurityFieldOrder),
    [inboundSecurityType, displaySecurityFieldOrder],
  )
  const inboundTlsBooleanGridFieldOrder = useMemo(
    () => (inboundSecurityType === 'tls' ? displaySecurityFieldOrder.filter(k => INBOUND_TLS_BOOLEAN_GRID_KEYS.has(k)) : []),
    [inboundSecurityType, displaySecurityFieldOrder],
  )
  const inboundTransport = useMemo(() => (inbound ? getInboundTransportRecord(inbound) : null), [inbound])
  const inboundTransportType = useMemo(() => (typeof inboundTransport?.type === 'string' ? inboundTransport.type : undefined), [inboundTransport])
  const xhttpExtra = useMemo(() => getXhttpExtraRecord(inboundTransport), [inboundTransport])
  const xPaddingBytesKey = useMemo(() => resolveTransportMetaKey(xhttpExtra, 'xpaddingbytes', 'xPaddingBytes'), [xhttpExtra])
  const xPaddingObfsEnabled = useMemo(() => {
    if (inboundTransportType !== 'xhttp') return false
    const raw = getTransportMetaValue(xhttpExtra, 'xpaddingobfsmode')
    return raw === true || raw === 'true' || raw === 1 || raw === '1'
  }, [inboundTransportType, xhttpExtra])
  const transportSettingsFieldOrder = useMemo(() => {
    if (!inboundTransportType) return []
    const order = caps.transportSettingsFieldOrderByType[inboundTransportType] ?? []
    const defs = caps.transportSettingsFieldDefinitions[inboundTransportType]
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
  }, [inboundTransportType, caps])
  const showTransportTypeSelect = useMemo(() => inbound && inbound.protocol !== 'hysteria' && transportSelectOptions.length > 0, [inbound, transportSelectOptions])
  const showTransportSettings = useMemo(
    () => Boolean(inbound?.protocol !== 'hysteria' && visibility?.stream && inboundTransportType && transportSettingsFieldOrder.length > 0),
    [inbound, visibility, inboundTransportType, transportSettingsFieldOrder],
  )
  const showTransportSection = useMemo(() => Boolean(showTransportTypeSelect || showTransportSettings || inbound?.protocol === 'hysteria'), [showTransportTypeSelect, showTransportSettings, inbound])

  const showTlsFallbacksEditor = useMemo(() => {
    if (!inbound) return false
    if (inbound.protocol !== 'vless' && inbound.protocol !== 'trojan') return false
    if (inboundTransportType !== 'tcp') return false
    if (inboundSecurityType !== 'tls') return false
    return true
  }, [inbound, inboundTransportType, inboundSecurityType])

  const inboundTlsFallbacks = useMemo((): Fallback[] | undefined => {
    if (!inbound) return undefined
    if (inbound.protocol === 'vless' || inbound.protocol === 'trojan') return inbound.fallbacks
    return undefined
  }, [inbound])

  const patchTransport = useCallback(
    (patch: Record<string, unknown>) => {
      if (!inbound || !('transport' in inbound) || !inbound.transport) return
      const cur = { ...(inbound.transport as unknown as Record<string, unknown>) }
      const t = inbound.transport.type
      const isXhttp = t === 'xhttp'
      const patchHasExplicitExtra = Object.prototype.hasOwnProperty.call(patch, 'extra')
      const rawExplicitExtra = patchHasExplicitExtra ? patch.extra : undefined
      const nextExtra = isXhttp
        ? patchHasExplicitExtra
          ? rawExplicitExtra && typeof rawExplicitExtra === 'object' && !Array.isArray(rawExplicitExtra)
            ? { ...(rawExplicitExtra as Record<string, unknown>) }
            : {}
          : (getXhttpExtraRecord(cur) ?? {})
        : null
      for (const [k, v] of Object.entries(patch)) {
        if (isXhttp && k === 'extra') continue
        const normalized = normalizeTransportMetaKey(k)
        if (isXhttp && isXhttpExtraMetaKey(normalized) && nextExtra) {
          // When patch carries explicit `extra`, undefined meta keys are root-cleanup only.
          // This avoids deleting freshly written values from `extra` in the same cycle.
          if (!(patchHasExplicitExtra && v === undefined)) {
            const extraKey = resolveTransportMetaKey(nextExtra, normalized, k)
            if (v === undefined || (typeof v === 'string' && v.trim() === '')) delete nextExtra[extraKey]
            else nextExtra[extraKey] = v
          }
          // Prevent strict-schema errors from root-level xhttp meta fields.
          delete cur[k]
          continue
        }
        if (v === undefined) delete cur[k]
        else cur[k] = v
      }
      if (isXhttp && nextExtra) {
        if (Object.keys(nextExtra).length === 0) delete cur.extra
        else cur.extra = nextExtra
      }
      cur.type = t
      patchInbound({ transport: cur as Transport } as Partial<Inbound>)
    },
    [inbound],
  )

  const updateXhttpMeta = useCallback(
    (normalizedKey: string, value: unknown) => {
      if (inboundTransportType !== 'xhttp') return
      const fallbackByKey: Record<string, string> = {
        xpaddingobfsmode: 'xPaddingObfsMode',
        xpaddingbytes: 'xPaddingBytes',
        xpaddingkey: 'xPaddingKey',
        xpaddingheader: 'xPaddingHeader',
        xpaddingplacement: 'xPaddingPlacement',
        xpaddingmethod: 'xPaddingMethod',
      }
      const nextExtra = { ...(xhttpExtra ?? {}) }
      const fallback = fallbackByKey[normalizedKey] ?? normalizedKey
      const resolved = resolveTransportMetaKey(xhttpExtra, normalizedKey, fallback)
      if (value === undefined || String(value).trim() === '') delete nextExtra[resolved]
      else nextExtra[resolved] = value

      const patch: Record<string, unknown> = {}
      patch.extra = Object.keys(nextExtra).length > 0 ? nextExtra : undefined

      // Clean up any legacy root-level xPadding keys that fail strict schema.
      for (const [legacyNormalized, legacyFallback] of Object.entries(fallbackByKey)) {
        const legacyRootKey = resolveTransportMetaKey(inboundTransport, legacyNormalized, legacyFallback)
        patch[legacyRootKey] = undefined
      }

      patchTransport(patch)
    },
    [inboundTransportType, xhttpExtra, inboundTransport, patchTransport],
  )

  const updateXhttpMetaBatch = useCallback(
    (updates: Record<string, unknown>) => {
      if (inboundTransportType !== 'xhttp') return
      const fallbackByKey: Record<string, string> = {
        xpaddingobfsmode: 'xPaddingObfsMode',
        xpaddingbytes: 'xPaddingBytes',
        xpaddingkey: 'xPaddingKey',
        xpaddingheader: 'xPaddingHeader',
        xpaddingplacement: 'xPaddingPlacement',
        xpaddingmethod: 'xPaddingMethod',
      }
      const nextExtra = { ...(xhttpExtra ?? {}) }
      for (const [normalizedKey, value] of Object.entries(updates)) {
        const fallback = fallbackByKey[normalizedKey] ?? normalizedKey
        const resolved = resolveTransportMetaKey(xhttpExtra, normalizedKey, fallback)
        if (value === undefined || String(value).trim() === '') delete nextExtra[resolved]
        else nextExtra[resolved] = value
      }
      const patch: Record<string, unknown> = {}
      patch.extra = Object.keys(nextExtra).length > 0 ? nextExtra : undefined
      for (const [legacyNormalized, legacyFallback] of Object.entries(fallbackByKey)) {
        const legacyRootKey = resolveTransportMetaKey(inboundTransport, legacyNormalized, legacyFallback)
        patch[legacyRootKey] = undefined
      }
      patchTransport(patch)
    },
    [inboundTransportType, xhttpExtra, inboundTransport, patchTransport],
  )

  useEffect(() => {
    if (inboundTransportType !== 'xhttp' || !xPaddingObfsEnabled) return
    const paddingBytesCurrent = getTransportMetaValue(xhttpExtra, 'xpaddingbytes')
    const hasPaddingBytes = paddingBytesCurrent !== undefined && String(paddingBytesCurrent).trim() !== '' && String(paddingBytesCurrent).trim() !== '0-0'
    if (hasPaddingBytes) return
    updateXhttpMeta('xpaddingbytes', '100-1000')
  }, [inboundTransportType, xPaddingObfsEnabled, xhttpExtra, xPaddingBytesKey, updateXhttpMeta])

  useEffect(() => {
    if (inboundTransportType !== 'xhttp' || !inboundTransport) return
    const xhttpMetaFallbacks: Record<string, string> = {
      headers: 'headers',
      xpaddingobfsmode: 'xPaddingObfsMode',
      xpaddingbytes: 'xPaddingBytes',
      xpaddingkey: 'xPaddingKey',
      xpaddingheader: 'xPaddingHeader',
      xpaddingplacement: 'xPaddingPlacement',
      xpaddingmethod: 'xPaddingMethod',
      uplinkhttpmethod: 'uplinkHTTPMethod',
      sessionplacement: 'sessionPlacement',
      sessionkey: 'sessionKey',
      seqplacement: 'seqPlacement',
      seqkey: 'seqKey',
      uplinkdataplacement: 'uplinkDataPlacement',
      uplinkdatakey: 'uplinkDataKey',
      uplinkchunksize: 'uplinkChunkSize',
      scmaxeachpostbytes: 'scMaxEachPostBytes',
      scminpostsintervalms: 'scMinPostsIntervalMs',
      scmaxbufferedposts: 'scMaxBufferedPosts',
      scstreamupserversecs: 'scStreamUpServerSecs',
      servermaxheaderbytes: 'serverMaxHeaderBytes',
      nogrpcheader: 'noGRPCHeader',
      nosseheader: 'noSSEHeader',
      xmux: 'xmux',
      downloadsettings: 'downloadSettings',
    }
    const nextExtra = { ...(xhttpExtra ?? {}) }
    let changed = false

    for (const [normalizedKey, fallbackKey] of Object.entries(xhttpMetaFallbacks)) {
      const rootKey = resolveTransportMetaKey(inboundTransport, normalizedKey, fallbackKey)
      const hasRootKey = Object.prototype.hasOwnProperty.call(inboundTransport, rootKey)
      if (!hasRootKey || rootKey === 'extra') continue

      const rootValue = (inboundTransport as Record<string, unknown>)[rootKey]
      const existingExtraValue = getTransportMetaValue(xhttpExtra, normalizedKey)
      if (existingExtraValue === undefined && rootValue !== undefined) {
        const extraKey = resolveTransportMetaKey(xhttpExtra, normalizedKey, fallbackKey)
        nextExtra[extraKey] = rootValue
      }
      changed = true
    }

    if (!changed) return

    const patch: Record<string, unknown> = {}
    patch.extra = Object.keys(nextExtra).length > 0 ? nextExtra : undefined
    for (const [normalizedKey, fallbackKey] of Object.entries(xhttpMetaFallbacks)) {
      const rootKey = resolveTransportMetaKey(inboundTransport, normalizedKey, fallbackKey)
      if (Object.prototype.hasOwnProperty.call(inboundTransport, rootKey) && rootKey !== 'extra') {
        patch[rootKey] = undefined
      }
    }
    patchTransport(patch)
  }, [inboundTransportType, inboundTransport, xhttpExtra, patchTransport])

  const finalizeDetailClose = () => {
    setDetailOpen(false)
    setDialogMode('edit')
    setDraftInbound(null)
    setEditOriginalInbound(null)
  }

  const isTagDuplicate = useCallback(
    (candidateRaw: string): boolean => {
      if (!profile) return false
      return profileTagHasDuplicateUsage(profile, candidateRaw, dialogMode === 'edit' ? { owner: 'inbound', index: selected } : undefined)
    },
    [profile, dialogMode, selected],
  )

  const setDuplicateTagError = useCallback(
    (tagValue: string) => {
      form.setError('tag', {
        type: 'validate',
        message: profileDuplicateTagMessage(t, tagValue),
      })
    },
    [form, t],
  )

  const validateWireguardInboundForCommit = useCallback(
    (wgInbound: Inbound): boolean => {
      if (!isWireguardInboundProtocol(wgInbound.protocol)) return true
      const secretKey = String((wgInbound as { secretKey?: unknown }).secretKey ?? '').trim()
      if (secretKey === '') {
        form.setError('wgSecretKey', {
          type: 'validate',
          message: t('validation.required', {
            field: t('coreEditor.inbound.wireguard.secretKey', { defaultValue: 'Secret Key' }),
            defaultValue: 'Secret Key is required',
          }),
        })
        return false
      }
      const peers = wireguardPeersForUi(wgInbound)
      if (peers.length === 0) {
        toast.error(
          t('coreEditor.inbound.wireguard.validation.peerRequired', {
            defaultValue: 'At least one peer is required.',
          }),
        )
        return false
      }
      if (peers.some(peer => peer.publicKey.trim() === '')) {
        toast.error(
          t('coreEditor.inbound.wireguard.validation.peerPublicKeyRequired', {
            defaultValue: 'Each peer must have a public key.',
          }),
        )
        return false
      }
      return true
    },
    [form, t],
  )

  const handleDetailOpenChange = (open: boolean) => {
    if (open) {
      setDetailOpen(true)
      return
    }
    if (dialogMode === 'add' && draftInbound !== null) {
      setDiscardDraftOpen(true)
      return
    }
    if (dialogMode === 'edit' && inbound && inbound.protocol !== 'unmanaged' && editOriginalInbound && JSON.stringify(inbound) !== JSON.stringify(editOriginalInbound)) {
      setDiscardEditOpen(true)
      return
    }
    finalizeDetailClose()
  }

  const commitAddInbound = async () => {
    if (!profile) return
    if (!draftInbound || draftInbound.protocol === 'unmanaged') return
    if (!assertNoPersistBlockingErrors()) return
    const tagValue = form.getValues('tag') ?? ''
    if (isTagDuplicate(tagValue)) {
      setDuplicateTagError(tagValue)
      return
    }
    const triggerFields =
      draftInbound.protocol === 'tun'
        ? (['protocol', 'tag', 'tunName', 'tunMtu'] as const)
        : draftInbound.protocol === 'wireguard'
          ? (['protocol', 'tag', 'port', 'wgSecretKey'] as const)
          : (['protocol', 'tag', 'port'] as const)
    const fields = [
      ...triggerFields,
      ...(form.getValues('security') === 'reality' ? realityInboundZodTriggerFieldNames() : []),
      ...(isTunnelInboundProtocol(draftInbound.protocol) ? (['tunnelRewriteAddress', 'tunnelRewritePort'] as const) : []),
    ]
    const ok = await form.trigger(fields, { shouldFocus: true })
    if (!ok) return
    if (!validateWireguardInboundForCommit(draftInbound)) return
    const insertAt = profile.inbounds.length
    updateXrayProfile(p => ({ ...p, inbounds: [...p.inbounds, draftInbound] }))
    setSelected(insertAt)
    finalizeDetailClose()
  }

  const commitEditInbound = async () => {
    if (dialogMode !== 'edit' || !inbound) return
    const tagValue = form.getValues('tag') ?? ''
    if (isTagDuplicate(tagValue)) {
      setDuplicateTagError(tagValue)
      return
    }
    if (inbound.protocol !== 'unmanaged' && 'transport' in inbound && 'security' in inbound) {
      const fields = ['protocol', 'tag', 'port', ...(form.getValues('security') === 'reality' ? realityInboundZodTriggerFieldNames() : [])]
      const ok = await form.trigger(fields, { shouldFocus: true })
      if (!ok) return
    } else if (inbound.protocol !== 'unmanaged' && isTunnelInboundProtocol(inbound.protocol)) {
      const ok = await form.trigger(['protocol', 'tag', 'port', 'tunnelRewriteAddress', 'tunnelRewritePort'], { shouldFocus: true })
      if (!ok) return
    } else if (inbound.protocol === 'tun') {
      const ok = await form.trigger(['protocol', 'tag', 'tunName', 'tunMtu'], { shouldFocus: true })
      if (!ok) return
    } else if (inbound.protocol === 'wireguard') {
      const ok = await form.trigger(['protocol', 'tag', 'port', 'wgSecretKey'], { shouldFocus: true })
      if (!ok) return
    }
    if (!validateWireguardInboundForCommit(inbound)) return
    let nextInbound: Inbound = inbound

    if ('security' in nextInbound && nextInbound.security && form.getValues('security') === 'none') {
      // When switching from TLS/Reality to none, force-drop advanced security keys.
      nextInbound = { ...nextInbound, security: { type: 'none' } } as unknown as Inbound
      if (nextInbound.protocol === 'vless' || nextInbound.protocol === 'trojan') {
        const copy = { ...nextInbound } as Record<string, unknown>
        delete copy.fallbacks
        nextInbound = copy as Inbound
      }
    }

    const selectedTransport = form.getValues('transport') as Transport['type'] | undefined
    if ('transport' in nextInbound && nextInbound.transport && selectedTransport && selectedTransport !== nextInbound.transport.type) {
      const baseArgs = kitArgsPreservingListenPort(nextInbound)
      let rebuilt: Inbound | null = null
      switch (nextInbound.protocol) {
        case 'vmess': {
          const st = nextInbound.security.type
          const security = st === 'tls' ? ('tls' as const) : ('none' as const)
          rebuilt = createDefaultInbound({
            protocol: 'vmess',
            ...baseArgs,
            transport: selectedTransport,
            security,
            clientDefaults: 'empty',
          })
          break
        }
        case 'vless': {
          const st = nextInbound.security.type
          const security = st === 'reality' ? ('reality' as const) : st === 'tls' ? ('tls' as const) : ('none' as const)
          rebuilt = createDefaultInbound({
            protocol: 'vless',
            ...baseArgs,
            transport: selectedTransport,
            security,
            clientDefaults: 'empty',
          })
          break
        }
        case 'trojan': {
          const st = nextInbound.security.type
          const security = st === 'reality' ? ('reality' as const) : st === 'tls' ? ('tls' as const) : ('none' as const)
          rebuilt = createDefaultInbound({
            protocol: 'trojan',
            ...baseArgs,
            transport: selectedTransport,
            security,
            clientDefaults: 'empty',
          })
          break
        }
        case 'shadowsocks': {
          const st = nextInbound.security?.type
          const security = st === 'tls' ? ('tls' as const) : ('none' as const)
          rebuilt = createDefaultInbound({
            protocol: 'shadowsocks',
            ...baseArgs,
            transport: selectedTransport,
            security,
            clientDefaults: 'empty',
          })
          break
        }
      }
      if (rebuilt) {
        if (nextInbound.protocol === 'vless' && rebuilt.protocol === 'vless') {
          rebuilt = mergeVlessInboundStreamFields(nextInbound, rebuilt)
        }
        if (nextInbound.protocol === 'trojan' && rebuilt.protocol === 'trojan') {
          rebuilt = mergeTrojanInboundStreamFields(nextInbound, rebuilt)
        }
        if (nextInbound.protocol === 'shadowsocks' && rebuilt.protocol === 'shadowsocks') {
          rebuilt = mergeShadowsocksInboundStreamFields(nextInbound, rebuilt)
        }
        rebuilt = mergeSecurityAcrossRebuild(nextInbound, rebuilt)
        rebuilt = mergeStreamAdvancedAcrossRebuild(nextInbound, rebuilt)
        nextInbound = rebuilt
      }
    }

    if (nextInbound.protocol === 'vless') {
      const rawEncryption = form.getValues('encryption') ?? ''
      const rawDecryption = form.getValues('decryption') ?? ''
      const rawFlow = form.getValues('vlessFlow') ?? ''
      const encryption = rawEncryption.trim() === '' ? 'none' : rawEncryption
      const decryption = rawDecryption.trim()
      const flow = rawFlow.trim()
      const vlessNext = { ...nextInbound } as { encryption?: string; decryption?: string; flow?: string }
      vlessNext.encryption = encryption
      if (decryption === '') delete vlessNext.decryption
      else vlessNext.decryption = rawDecryption
      if (flow === '') delete vlessNext.flow
      else vlessNext.flow = flow
      nextInbound = vlessNext as Inbound
    }

    replaceEffectiveInbound(nextInbound)
    if ('security' in nextInbound && nextInbound.security) form.setValue('security', nextInbound.security.type)
    if ('transport' in nextInbound && nextInbound.transport) form.setValue('transport', nextInbound.transport.type)
    if (nextInbound.protocol === 'vless') {
      syncVlessFieldsFromInboundForm(form, nextInbound)
    }
    syncSecurityFormFields(nextInbound)
    syncTransportFormFields(nextInbound)
    finalizeDetailClose()
  }

  const replaceEffectiveInbound = (next: Inbound) => {
    if (dialogMode === 'add' && draftInbound !== null) setDraftInbound(next)
    else updateXrayProfile(p => replaceInbound(p, selected, next))
  }

  function patchInboundSockopt(next: Record<string, unknown> | undefined) {
    if (!inbound || inbound.protocol === 'unmanaged' || inbound.protocol === 'tun') return
    const baseRec = { ...(inbound as Record<string, unknown>) }
    const prevSa = (baseRec.streamAdvanced as Record<string, unknown> | undefined) ?? {}
    const sa = { ...prevSa }
    const pruned = next === undefined ? undefined : pruneSockoptObject(next)
    if (pruned === undefined) delete sa.sockopt
    else sa.sockopt = pruned
    if (Object.keys(sa).length === 0) delete baseRec.streamAdvanced
    else baseRec.streamAdvanced = sa
    replaceEffectiveInbound(baseRec as Inbound)
  }

  function renderInboundSockopt() {
    if (!inbound || inbound.protocol === 'unmanaged' || inbound.protocol === 'tun') return null
    const raw = (inbound as { streamAdvanced?: { sockopt?: Record<string, unknown> } }).streamAdvanced?.sockopt
    const sockValue = raw && typeof raw === 'object' && !Array.isArray(raw) ? ({ ...raw } as Record<string, unknown>) : undefined
    return <XrayStreamSockoptInboundAccordion accordionItemClassName={INBOUND_SECURITY_SUBACCORDION_ITEM_CLASS} value={sockValue} onChange={patchInboundSockopt} t={t} />
  }

  const patchInbound = (patch: Partial<Inbound>) => {
    if (!inbound || inbound.protocol === 'unmanaged') return
    const base = { ...inbound } as Record<string, unknown>
    if (inbound.protocol === 'tunnel' || inbound.protocol === 'dokodemo-door') {
      delete base.settings
    }
    for (const [key, val] of Object.entries(patch)) {
      if (key === 'encryption' || key === 'decryption') continue
      if (key === 'flow') continue
      if (key === 'fallbacks') continue
      if (val !== undefined) base[key] = val
    }
    if ('encryption' in patch) {
      const v = patch.encryption
      if (typeof v === 'string' && v.trim() === '') delete base.encryption
      else if (v !== undefined) base.encryption = v
    }
    if ('decryption' in patch) {
      const v = patch.decryption
      if (typeof v === 'string' && v.trim() === '') delete base.decryption
      else if (v !== undefined) base.decryption = v
    }
    if ('flow' in (patch as Record<string, unknown>)) {
      const v = (patch as Record<string, unknown>).flow
      if (typeof v === 'string' && v.trim() === '') delete base.flow
      else if (v !== undefined) base.flow = v
    }
    if ('listen' in patch) {
      if (!shouldPersistInboundListen(patch.listen as string | undefined)) delete base.listen
    }
    if ('sniffing' in patch && patch.sniffing === undefined) delete base.sniffing
    if ('port' in patch && patch.port === undefined) delete base.port
    if ('address' in patch && patch.address === undefined) delete base.address
    if ('targetPort' in patch && patch.targetPort === undefined) delete base.targetPort
    if ('network' in patch && patch.network === undefined) delete base.network
    if ('raw' in patch && patch.raw === undefined) delete base.raw
    if ('portMap' in patch && patch.portMap === undefined) delete base.portMap
    if ('fallbacks' in patch) {
      const fb = patch.fallbacks as Fallback[] | undefined
      if (fb === undefined || (Array.isArray(fb) && fb.length === 0)) delete base.fallbacks
      else base.fallbacks = fb
    }
    if (base.protocol === 'tunnel' || base.protocol === 'dokodemo-door') {
      base.network = normalizeTunnelNetworkForKit(base.network)
    }
    if (base.protocol === 'shadowsocks' && base.network !== undefined) {
      base.network = normalizeTunnelNetworkForKit(base.network)
    }
    const merged = base as Inbound
    if (dialogMode === 'add' && draftInbound !== null) setDraftInbound(merged)
    else updateXrayProfile(p => replaceInbound(p, selected, merged))
  }

  patchInboundRef.current = patchInbound

  useEffect(() => {
    if (!detailOpen || inbound?.protocol !== 'vless') return
    if (
      !vlessInboundFlowIncompatible({
        securityType: effectiveSecurityTypeForVlessInboundFlow(inbound, form.getValues('security')),
        transportType: effectiveTransportTypeForVlessInboundFlow(inbound),
        encryption: form.getValues('encryption'),
        flow: vlessStoredFlow,
      })
    ) {
      return
    }
    form.setValue('vlessFlow', '')
    patchInboundRef.current?.({ flow: '' } as Partial<Inbound>)
  }, [detailOpen, inbound, vlessStoredFlow, form])

  useEffect(() => {
    if (!detailOpen) {
      wireguardKitAllowedMigrateKeyRef.current = null
      return
    }
    if (!inbound || inbound.protocol !== 'wireguard') return

    const stableKey = `${dialogMode}:${selected}:${inbound.tag}`
    if (wireguardKitAllowedMigrateKeyRef.current === stableKey) return

    const peers = wireguardPeersForUi(inbound)
    const nextPeers = peers.map((p, i) => ({
      ...p,
      ...(isLikelyWireguardKitCatchAllAllowedIps(p.allowedIPs) ? { allowedIPs: wireguardDefaultAllowedIpsForNewPeer(i) } : {}),
    }))
    const changed = peers.some((p, i) => JSON.stringify(p.allowedIPs) !== JSON.stringify(nextPeers[i]?.allowedIPs))

    if (changed) {
      patchInboundRef.current?.({ peers: nextPeers.length > 0 ? nextPeers : undefined } as Partial<Inbound>)
    }
    wireguardKitAllowedMigrateKeyRef.current = stableKey
  }, [detailOpen, dialogMode, selected, inbound])

  const patchTunnelInboundFields = useCallback(
    (
      updates: Partial<{
        rewriteAddress: string
        rewritePort: string
        allowedNetwork: string
        followRedirect: boolean
      }>,
    ) => {
      if (!inbound || !isTunnelInboundProtocol(inbound.protocol)) return
      const proto = inbound.protocol === 'dokodemo-door' ? ({ protocol: 'tunnel' } as Partial<Inbound>) : ({} as Partial<Inbound>)
      const next: Record<string, unknown> = { ...proto }

      if (updates.rewriteAddress !== undefined) {
        const v = updates.rewriteAddress.trim()
        next.address = v === '' ? undefined : v
      }
      if (updates.rewritePort !== undefined) {
        const t = updates.rewritePort.trim()
        next.targetPort = t === '' ? undefined : Number.isFinite(Number(t)) ? Math.trunc(Number(t)) : undefined
      }
      if (updates.allowedNetwork !== undefined) {
        next.network = normalizeTunnelNetworkForKit(updates.allowedNetwork)
      }
      if (updates.followRedirect !== undefined) {
        next.followRedirect = updates.followRedirect
      }

      patchInbound(next as Partial<Inbound>)
    },
    [inbound],
  )

  const persistTunnelPortMapRows = useCallback(
    (rows: { listenPort: string; target: string }[]) => {
      if (!inbound || !isTunnelInboundProtocol(inbound.protocol)) return
      const portMap: Record<string, string> = {}
      for (const r of rows) {
        const lp = r.listenPort.trim()
        const tg = r.target.trim()
        if (!lp || !tg) continue
        portMap[lp] = tg
      }
      const protoPatch = inbound.protocol === 'dokodemo-door' ? ({ protocol: 'tunnel' as const } as Partial<Inbound>) : {}
      patchInbound({
        ...protoPatch,
        portMap: Object.keys(portMap).length > 0 ? portMap : undefined,
      } as Partial<Inbound>)
    },
    [inbound],
  )

  const commitTunnelBlankPortMapSlot = useCallback(
    (slotIndex: number) => {
      if (!inbound || !isTunnelInboundProtocol(inbound.protocol)) return
      const r = tunnelBlankPortMapRowsRef.current[slotIndex]
      if (!r) return
      const lp = r.listenPort.trim()
      const tg = r.target.trim()
      if (!lp || !tg) return
      const curPm = readTunnelPortMapRowsFromInbound(inbound)
      persistTunnelPortMapRows([...curPm, { listenPort: lp, target: tg }])
      setTunnelBlankPortMapRows(prev => {
        const next = prev.filter((_, k) => k !== slotIndex)
        return next
      })
    },
    [inbound, persistTunnelPortMapRows],
  )

  const patchHysteriaServerSettings = useCallback(
    (patch: { auth?: string; udpIdleTimeout?: number | undefined; masquerade?: Record<string, unknown> | undefined }) => {
      if (!inbound || inbound.protocol !== 'hysteria' || inbound.transport.type !== 'hysteria') return
      // Peer auth belongs on hysteria transport (hysteriaSettings); keep settings.clients empty in exported Xray JSON.
      const nextClients = inbound.clients.filter(client => client.protocol !== 'hysteria')
      const nextTransport = { ...inbound.transport }
      if ('auth' in patch) {
        const auth = (patch.auth ?? '').trim()
        if (auth === '') delete nextTransport.auth
        else nextTransport.auth = auth
      }
      if ('udpIdleTimeout' in patch) {
        const timeout = patch.udpIdleTimeout
        if (timeout === undefined || Number.isNaN(timeout)) delete nextTransport.udpIdleTimeout
        else nextTransport.udpIdleTimeout = timeout
      }
      if ('masquerade' in patch) {
        if (!patch.masquerade || Object.keys(patch.masquerade).length === 0) {
          delete nextTransport.masquerade
        } else {
          const mergedMasquerade = { ...(nextTransport.masquerade ?? {}), ...patch.masquerade } as Record<string, unknown>
          for (const [k, v] of Object.entries(mergedMasquerade)) {
            if (v === undefined || (typeof v === 'string' && v.trim() === '')) delete mergedMasquerade[k]
          }
          if (Object.keys(mergedMasquerade).length === 0) delete nextTransport.masquerade
          else nextTransport.masquerade = mergedMasquerade as NonNullable<typeof nextTransport.masquerade>
        }
      }
      patchInbound({
        clients: nextClients,
        transport: nextTransport as Transport,
      } as Partial<Inbound>)
    },
    [inbound],
  )
  const generateHysteriaAuth = useCallback(() => {
    const generated = generatePassword()
    form.setValue('hysteriaAuth', generated)
    patchHysteriaServerSettings({ auth: generated })
  }, [form, patchHysteriaServerSettings])
  const hysteriaMasqueradeType = form.watch('hysteriaMasqueradeType')
  const sniffingEnabledValue = form.watch('sniffingEnabled')
  const isSniffingEnabled = sniffingEnabledValue === 'true'
  const currentSniffing = inbound && inbound.protocol !== 'unmanaged' && 'sniffing' in inbound ? inbound.sniffing : undefined
  const renderSniffingAccordion = () => (
    <Accordion type="single" collapsible className="mt-0! sm:col-span-2">
      <AccordionItem value="sniffing" className={INBOUND_SECURITY_SUBACCORDION_ITEM_CLASS}>
        <AccordionTrigger>
          <div className="flex items-center gap-2">
            <Shield className="text-muted-foreground h-3.5 w-3.5 shrink-0" aria-hidden />
            <span>{t('coreEditor.inbound.sniffing.section', { defaultValue: 'Sniffing' })}</span>
          </div>
        </AccordionTrigger>
        <AccordionContent className="pt-0 pb-3">
          <div className="flex flex-col gap-3">
            <FormField
              control={form.control}
              name="sniffingEnabled"
              render={({ field }) => (
                <FormItem className="flex flex-row items-center justify-between gap-3 space-y-0 py-1">
                  <FormLabel className="cursor-pointer text-sm font-medium">{t('coreEditor.inbound.sniffing.enabled', { defaultValue: 'Enabled' })}</FormLabel>
                  <FormControl>
                    <Switch
                      checked={!!field.value && field.value !== 'false'}
                      onCheckedChange={(checked: boolean) => {
                        field.onChange(checked ? 'true' : 'false')
                        if (checked) {
                          const nextDestOverride = [...SNIFFING_DEST_OVERRIDE_OPTIONS]
                          form.setValue('sniffingDestOverride', JSON.stringify(nextDestOverride))
                          patchInbound({
                            sniffing: {
                              ...(currentSniffing as any),
                              enabled: true,
                              destOverride: nextDestOverride,
                              metadataOnly: form.getValues('sniffingMetadataOnly') === 'true',
                              routeOnly: form.getValues('sniffingRouteOnly') === 'true',
                            },
                          } as Partial<Inbound>)
                        } else {
                          form.setValue('sniffingDestOverride', JSON.stringify([]))
                          form.setValue('sniffingMetadataOnly', 'false')
                          form.setValue('sniffingRouteOnly', 'false')
                          patchInbound({ sniffing: undefined } as Partial<Inbound>)
                        }
                      }}
                    />
                  </FormControl>
                </FormItem>
              )}
            />
            {isSniffingEnabled ? (
              <div className="border-border/60 space-y-3 border-t pt-3">
                <FormField
                  control={form.control}
                  name="sniffingDestOverride"
                  render={({ field }) => {
                    const selectedProtocols = parseSniffingDestOverride(field.value)
                    return (
                      <FormItem className="space-y-2 py-0">
                        <FormLabel className="text-muted-foreground text-xs font-medium">{t('coreEditor.inbound.sniffing.destOverride', { defaultValue: 'Dest override' })}</FormLabel>
                        <FormControl>
                          <div className="flex flex-wrap gap-x-5 gap-y-2.5 sm:gap-x-6">
                            {SNIFFING_DEST_OVERRIDE_OPTIONS.map(protocol => (
                              <label key={protocol} className="text-foreground flex cursor-pointer items-center gap-2.5 text-xs font-medium tracking-wide uppercase select-none">
                                <Checkbox
                                  checked={selectedProtocols.includes(protocol)}
                                  onCheckedChange={checked => {
                                    const isChecked = checked === true
                                    const updated = isChecked ? [...new Set([...selectedProtocols, protocol])] : selectedProtocols.filter(p => p !== protocol)
                                    field.onChange(JSON.stringify(updated))
                                    patchInbound({
                                      sniffing: {
                                        ...(currentSniffing as any),
                                        destOverride: updated,
                                      },
                                    } as Partial<Inbound>)
                                  }}
                                />
                                <span>{protocol}</span>
                              </label>
                            ))}
                          </div>
                        </FormControl>
                      </FormItem>
                    )
                  }}
                />
                <FormField
                  control={form.control}
                  name="sniffingMetadataOnly"
                  render={({ field }) => (
                    <FormItem className="flex flex-row items-center justify-between gap-3 space-y-0 py-0">
                      <FormLabel className="cursor-pointer text-xs font-medium">{t('coreEditor.inbound.sniffing.metadataOnly', { defaultValue: 'Metadata only' })}</FormLabel>
                      <FormControl>
                        <Switch
                          checked={!!field.value && field.value !== 'false'}
                          onCheckedChange={(checked: boolean) => {
                            field.onChange(checked ? 'true' : 'false')
                            patchInbound({
                              sniffing: {
                                ...(currentSniffing as any),
                                metadataOnly: checked,
                              },
                            } as Partial<Inbound>)
                          }}
                        />
                      </FormControl>
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name="sniffingRouteOnly"
                  render={({ field }) => (
                    <FormItem className="flex flex-row items-center justify-between gap-3 space-y-0 py-0">
                      <FormLabel className="cursor-pointer text-xs font-medium">{t('coreEditor.inbound.sniffing.routeOnly', { defaultValue: 'Route only' })}</FormLabel>
                      <FormControl>
                        <Switch
                          checked={!!field.value && field.value !== 'false'}
                          onCheckedChange={(checked: boolean) => {
                            field.onChange(checked ? 'true' : 'false')
                            patchInbound({
                              sniffing: {
                                ...(currentSniffing as any),
                                routeOnly: checked,
                              },
                            } as Partial<Inbound>)
                          }}
                        />
                      </FormControl>
                    </FormItem>
                  )}
                />
              </div>
            ) : null}
          </div>
        </AccordionContent>
      </AccordionItem>
    </Accordion>
  )

  const generateInboundShadowsocksPassword = () => {
    const methodValue = form.getValues('shadowsocksMethod')
    setIsGeneratingShadowsocksPassword(true)
    try {
      const result = generateShadowsocksPassword(methodValue)
      if (!result) {
        toast.error(t('coreConfigModal.shadowsocksPasswordGenerationFailed'))
        return
      }
      form.setValue('shadowsocksPassword', result.password)
      patchInbound({
        password: result.password,
        method: methodValue as ShadowsocksMethod,
      } as Partial<Inbound>)
      setShadowsocksPasswordJustGenerated(true)
      toast.success(t('coreConfigModal.shadowsocksPasswordGenerated'))
    } catch {
      toast.error(t('coreConfigModal.shadowsocksPasswordGenerationFailed'))
    } finally {
      setIsGeneratingShadowsocksPassword(false)
    }
  }

  const openInboundVlessGenerator = () => {
    const method = vlessInboundEncryptionMethodForForm({
      protocol: 'vless',
      encryption: form.getValues('encryption') ?? '',
    })
    setVlessAdvancedSeed(buildVlessGenerationOptionsFromInboundForm(method))
    setVlessAdvancedOpen(true)
  }

  const generateRealityKeys = async () => {
    try {
      setIsGeneratingRealityKeyPair(true)
      const keyPair = generateRealityKeyPair()
      form.setValue(securityFieldName('publicKey'), keyPair.publicKey)
      form.setValue(securityFieldName('privateKey'), keyPair.privateKey)
      patchSecurity({
        publicKey: keyPair.publicKey,
        privateKey: keyPair.privateKey,
      })
      revalidateRealityInboundForm()
      toast.success(t('coreConfigModal.keyPairGenerated'))
    } catch (error) {
      toast.error(t('coreConfigModal.keyPairGenerationFailed'))
    } finally {
      setIsGeneratingRealityKeyPair(false)
    }
  }

  const generateShortId = async () => {
    try {
      setIsGeneratingRealityShortId(true)
      const newId = generateRealityShortId()
      const realityOrder = caps.securityFieldOrderByType.reality ?? []
      const jsonKey = realityOrder.includes('shortIds') ? 'shortIds' : 'shortId'
      const def = caps.securityFieldDefinitions.reality?.[jsonKey]
      const fieldName = securityFieldName(jsonKey)
      const currentRaw = String(form.getValues(fieldName) ?? '')

      const splitLinesAndCommas = (raw: string) =>
        raw
          .split(/[\n,]+/)
          .map(s => s.trim())
          .filter(Boolean)

      let parts = splitLinesAndCommas(currentRaw)
      if (def && inferParityFieldMode(def) === 'stringList') {
        const parsed = parseOutboundSettingValue(def, currentRaw)
        if (Array.isArray(parsed) && parsed.length > 0) {
          parts = parsed.map(String).filter(Boolean)
        }
      }
      if (!parts.includes(newId)) parts.push(newId)

      if (def && inferParityFieldMode(def) === 'stringList') {
        const formStr = outboundSettingToString(parts, def)
        form.setValue(fieldName, formStr)
        patchSecurity({ [jsonKey]: parts })
      } else if (def) {
        const formStr = parts.join('\n')
        form.setValue(fieldName, formStr)
        patchSecurity({ [jsonKey]: parseOutboundSettingValue(def, formStr) })
      } else {
        const formStr = parts.join('\n')
        form.setValue(fieldName, formStr)
        patchSecurity({
          [jsonKey]: jsonKey === 'shortIds' ? parts : parts.length === 1 ? (parts[0] ?? newId) : parts,
        })
      }
      revalidateRealityInboundForm()
      toast.success(t('coreConfigModal.shortIdGenerated'))
    } catch (error) {
      toast.error(t('coreConfigModal.shortIdGenerationFailed'))
    } finally {
      setIsGeneratingRealityShortId(false)
    }
  }

  const handleGenerateMldsa65 = async () => {
    try {
      setIsGeneratingMldsa65(true)
      const result = await generateMldsa65Keys()
      form.setValue(securityFieldName('mldsa65Seed'), result.seed)
      form.setValue(securityFieldName('mldsa65Verify'), result.verify)
      patchSecurity({
        mldsa65Seed: result.seed,
        mldsa65Verify: result.verify,
      })
      revalidateRealityInboundForm()
      toast.success(t('coreConfigModal.mldsa65Generated'))
    } catch (error) {
      const message = error instanceof Error ? error.message : t('coreConfigModal.mldsa65GenerationFailed', { defaultValue: 'Failed to generate ML-DSA-65 keys' })
      toast.error(message)
    } finally {
      setIsGeneratingMldsa65(false)
    }
  }

  const syncSecurityFormFields = (next: Inbound) => {
    const security = getInboundSecurityRecord(next)
    const securityType = security?.type
    if (typeof securityType !== 'string') return
    for (const key of caps.securityFieldOrderByType[securityType] ?? []) {
      const def = caps.securityFieldDefinitions[securityType]?.[key]
      if (def) form.setValue(securityFieldName(key), outboundSettingToString(security?.[key], def), syncOpts)
    }
  }

  const syncTransportFormFields = (next: Inbound) => {
    const tr = getInboundTransportRecord(next)
    const transportType = tr?.type
    if (typeof transportType !== 'string') return
    const trExtra = transportType === 'xhttp' ? getXhttpExtraRecord(tr) : null
    for (const key of caps.transportSettingsFieldOrderByType[transportType] ?? []) {
      const def = caps.transportSettingsFieldDefinitions[transportType]?.[key]
      const normalizedKey = normalizeTransportMetaKey(key)
      const transportValue = transportType === 'xhttp' && isXhttpExtraMetaKey(normalizedKey) ? getTransportMetaValue(trExtra, normalizedKey) : tr?.[key]
      if (def) {
        if (isJsonRawMessageField(def)) {
          if (dialogMode === 'add') {
            const fieldName = transportFieldName(key)
            const currentValue = form.getValues(fieldName)
            // In add flow, keep user's in-progress value only when explicitly set.
            if (!currentValue || typeof currentValue !== 'string' || currentValue.trim() === '') {
              form.setValue(fieldName, '', syncOpts)
            }
          } else {
            form.setValue(transportFieldName(key), outboundSettingToString(transportValue, def), syncOpts)
          }
        } else {
          form.setValue(transportFieldName(key), outboundSettingToString(transportValue, def), syncOpts)
        }
      }
    }
  }

  const patchSecurity = (patch: Record<string, unknown>) => {
    const security = inbound ? getInboundSecurityRecord(inbound) : null
    if (!security) return
    const merged = { ...security, ...patch } as Security
    patchInbound({ security: merged } as Partial<Inbound>)
  }

  const setTlsCertificates = (next: TlsCertificateUiItem[]) => {
    if (!inboundSecurity || inboundSecurityType !== 'tls') return
    const merged = { ...(inboundSecurity as Record<string, unknown>) }
    const normalized = next.map(item => {
      const certFile = item.certificateFile.trim()
      const keyFile = item.keyFile.trim()
      const certContent = item.certificate.trim()
      const keyContent = item.key.trim()
      const ocspRaw = item.ocspStapling.trim()
      const ocspNum = ocspRaw === '' ? undefined : Number(ocspRaw)
      const base = {
        ...(ocspNum !== undefined && Number.isFinite(ocspNum) ? { ocspStapling: ocspNum } : {}),
        ...(item.serveOnNode ? { serveOnNode: true } : {}),
      }
      if (item.mode === 'content') {
        const certificateLines = certContent
          .split(/\r?\n/)
          .map(line => line.trim())
          .filter(Boolean)
        const keyLines = keyContent
          .split(/\r?\n/)
          .map(line => line.trim())
          .filter(Boolean)
        return {
          ...base,
          certificate: certificateLines,
          key: keyLines,
        }
      }
      return {
        ...base,
        certificateFile: certFile,
        keyFile,
      }
    })

    if (next.length === 0) {
      delete merged.certificates
    } else {
      merged.certificates = normalized
    }

    patchInbound({ security: merged as Security } as Partial<Inbound>)
  }

  const applyTlsEchPatch = (patch: { echServerKeys?: string; echConfigList?: string; echForceQuery?: string }) => {
    if (inboundSecurityType !== 'tls') return
    const security = (inboundSecurity ?? {}) as Record<string, unknown>
    const echSockopt = (security.echSockopt ?? {}) as Record<string, unknown>
    const mergedEch = { ...echSockopt }

    if ('echServerKeys' in patch) {
      if (patch.echServerKeys === undefined || patch.echServerKeys.trim() === '') delete mergedEch.serverKeys
      else mergedEch.serverKeys = patch.echServerKeys
    }
    if ('echConfigList' in patch) {
      if (patch.echConfigList === undefined || patch.echConfigList.trim() === '') delete mergedEch.configList
      else mergedEch.configList = patch.echConfigList
    }
    if ('echForceQuery' in patch) {
      if (patch.echForceQuery === undefined || patch.echForceQuery.trim() === '') delete mergedEch.forceQuery
      else mergedEch.forceQuery = patch.echForceQuery
    }

    const mergedSecurity = { ...security }
    if (Object.keys(mergedEch).length === 0) {
      delete mergedSecurity.echSockopt
    } else {
      mergedSecurity.echSockopt = mergedEch
    }

    // Ensure we don't have legacy top-level fields
    delete mergedSecurity.echServerKeys
    delete mergedSecurity.echConfigList
    delete mergedSecurity.echForceQuery

    patchInbound({ security: mergedSecurity as Security } as Partial<Inbound>)
  }

  const handleGenerateEchCertificate = () => {
    const generatedEchServerKey = mutateBase64Seed(DEFAULT_ECH_SERVER_KEY)
    const generatedEchConfig = mutateBase64Seed(DEFAULT_ECH_CONFIG)
    form.setValue(securityFieldName('echServerKeys'), generatedEchServerKey)
    form.setValue(securityFieldName('echConfigList'), generatedEchConfig)
    if (echUsageOption === 'required') {
      form.setValue(securityFieldName('echForceQuery'), 'full')
      applyTlsEchPatch({
        echServerKeys: generatedEchServerKey,
        echConfigList: generatedEchConfig,
        echForceQuery: 'full',
      })
    } else if (echUsageOption === 'preferred') {
      form.setValue(securityFieldName('echForceQuery'), 'half')
      applyTlsEchPatch({
        echServerKeys: generatedEchServerKey,
        echConfigList: generatedEchConfig,
        echForceQuery: 'half',
      })
    } else {
      form.setValue(securityFieldName('echForceQuery'), '')
      applyTlsEchPatch({
        echServerKeys: generatedEchServerKey,
        echConfigList: generatedEchConfig,
        echForceQuery: '',
      })
    }
  }

  if (!profile) return null

  return (
    <div className="space-y-6">
      <CoreEditorDataTable
        columns={columns}
        data={profile.inbounds}
        getSearchableText={inboundSearchHaystack}
        getRowId={(_row: Inbound, i: number) => String(i)}
        minRowCount={1}
        minRowCountMessage={t('coreEditor.inbound.keepAtLeastOne', {
          defaultValue: 'At least one inbound is required.',
        })}
        onRowClick={(_row, rowIndex) => {
          if (detailOpen && dialogMode === 'add' && draftInbound !== null) {
            setBlockAddWhileDraftOpen(true)
            return
          }
          setDraftInbound(null)
          setDialogMode('edit')
          setEditOriginalInbound(cloneInbound(profile.inbounds[rowIndex]))
          setSelected(rowIndex)
          setDetailOpen(true)
        }}
        onRemoveRow={i => {
          updateXrayProfile(p => removeInbound(p, i))
          setSelected(0)
        }}
        onBulkRemove={indices => {
          const rm = new Set(indices)
          updateXrayProfile(p => ({ ...p, inbounds: p.inbounds.filter((_, idx) => !rm.has(idx)) }))
          setSelected(0)
        }}
        enableReorder
        onReorder={(from, to) => {
          updateXrayProfile(p => ({ ...p, inbounds: arrayMove(p.inbounds, from, to) }))
          setSelected(sel => remapIndexAfterArrayMove(sel, from, to))
        }}
      />

      <CoreEditorFormDialog
        isDialogOpen={detailOpen}
        onOpenChange={handleDetailOpenChange}
        inlinePersistValidation={!(detailOpen && dialogMode === 'add')}
        persistValidationPathPrefix={detailOpen && dialogMode === 'edit' ? `/inbounds/${selected + 1}` : undefined}
        leadingIcon={dialogMode === 'add' ? <Plus className="h-5 w-5 shrink-0" /> : <Pencil className="h-5 w-5 shrink-0" />}
        title={dialogMode === 'add' ? t('coreEditor.inbound.dialogTitleAdd', { defaultValue: 'Add inbound' }) : t('coreEditor.inbound.dialogTitleEdit', { defaultValue: 'Edit inbound' })}
        size="md"
        footerExtra={
          dialogMode === 'add' && draftInbound ? (
            <Button type="button" className="sm:min-w-[88px]" onClick={commitAddInbound}>
              {t('coreEditor.inbound.addToList', { defaultValue: 'Add to list' })}
            </Button>
          ) : dialogMode === 'edit' ? (
            <Button type="button" className="sm:min-w-[88px]" onClick={commitEditInbound}>
              {t('modify')}
            </Button>
          ) : undefined
        }
      >
        {inbound?.protocol === 'unmanaged' && (
          <p className="text-muted-foreground text-sm">{t('coreEditor.inbound.unmanagedHint', { defaultValue: 'This inbound is managed as raw JSON in Advanced.' })}</p>
        )}

        {inbound && inbound.protocol !== 'unmanaged' && 'transport' in inbound && 'security' in inbound && (
          <Form {...form}>
            <form className="flex flex-col gap-4 pb-6" onSubmit={e => e.preventDefault()}>
              <div className="grid gap-4 sm:grid-cols-2">
                <FormField
                  control={form.control}
                  name="tag"
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
                            form.clearErrors('tag')
                            patchInbound({ tag: v })
                          }}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="protocol"
                  render={({ field, fieldState }) => (
                    <FormItem>
                      <FormLabel>{t('coreEditor.field.protocol', { defaultValue: 'Protocol' })}</FormLabel>
                      <Select
                        dir="ltr"
                        value={field.value}
                        onValueChange={v => {
                          const protocol = v as Parameters<typeof createDefaultInboundForProtocol>[0]['protocol']
                          field.onChange(protocol)
                          const next = applyInboundEditorCreationDefaults(
                            createDefaultInboundForProtocol({
                              protocol,
                              ...kitArgsPreservingListenPort(inbound),
                              clientDefaults: 'empty',
                            }),
                          )
                          replaceEffectiveInbound(next)
                          form.setValue('protocol', next.protocol)
                          form.setValue('tag', next.tag ?? '')
                          form.setValue('listen', 'listen' in next ? listenAddressForForm(next.listen) : '')
                          form.setValue('port', 'port' in next && next.port !== undefined ? String(next.port) : '')
                          syncVlessFieldsFromInboundForm(form, next)
                          form.setValue('shadowsocksMethod', shadowsocksMethodFormValue(next))
                          form.setValue('shadowsocksPassword', shadowsocksPasswordFormValue(next))
                          form.setValue('shadowsocksNetwork', shadowsocksNetworkFormValue(next))
                          setShadowsocksPasswordJustGenerated(false)
                          setVlessDecryptionJustGenerated(false)
                          form.setValue('transport', 'transport' in next && next.transport ? next.transport.type : 'tcp')
                          form.setValue('security', 'security' in next && next.security ? next.security.type : 'none')
                          syncSecurityFormFields(next)
                          syncTransportFormFields(next)
                          syncTunnelFormFieldsFromInbound(next)
                          syncTunFormFieldsFromInbound(next)
                          syncWireguardFormFieldsFromInbound(next)
                        }}
                      >
                        <FormControl className={cn(!!fieldState.error && 'border-destructive')}>
                          <SelectTrigger className="h-10 py-2" dir="ltr">
                            <SelectValue />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent dir="ltr">
                          {protocolSelectOptions.map(p => (
                            <SelectItem key={p} value={p}>
                              {formatInboundProtocolForUi(p, t)}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="listen"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>{t('coreEditor.field.listen', { defaultValue: 'Listen' })}</FormLabel>
                      <FormControl>
                        <Input
                          {...field}
                          className="h-10"
                          dir="ltr"
                          placeholder="0.0.0.0"
                          onChange={e => {
                            const v = e.target.value
                            field.onChange(v)
                            if (!shouldPersistInboundListen(v)) patchInbound({ listen: undefined } as Partial<Inbound>)
                            else patchInbound({ listen: v.trim() })
                          }}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="port"
                  render={({ field, fieldState }) => (
                    <FormItem>
                      <FormLabel>{t('coreEditor.field.port', { defaultValue: 'Port' })}</FormLabel>
                      <FormControl>
                        <Input
                          {...field}
                          className="h-10"
                          dir="ltr"
                          isError={!!fieldState.error}
                          placeholder="443 or 1000-2000,444"
                          onChange={e => {
                            const v = e.target.value
                            field.onChange(v)
                            if (v.trim() === '') patchInbound({ port: undefined } as Partial<Inbound>)
                            else {
                              const n = Number(v)
                              patchInbound({ port: Number.isFinite(n) ? n : v } as Partial<Inbound>)
                            }
                          }}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                {inbound.protocol === 'vless' && (
                  <FormField
                    control={form.control}
                    name="encryption"
                    render={({ field, fieldState }) => (
                      <FormItem className="sm:col-span-2">
                        <FormLabel className="text-muted-foreground text-xs font-semibold tracking-wide">{t('coreConfigModal.encryption', { defaultValue: 'Encryption' })}</FormLabel>
                        <FormControl>
                          <Input
                            {...field}
                            dir="ltr"
                            className="h-10 text-xs"
                            isError={!!fieldState.error}
                            placeholder="none (VLESS inbound; use TLS/REALITY for transport security)"
                            onChange={e => {
                              const v = e.target.value.trim() === '' ? 'none' : e.target.value
                              field.onChange(v)
                              setVlessDecryptionJustGenerated(false)
                              const parsed = parseVlessEncryptionMethodTokenFromString(v)
                              if (parsed !== null) form.setValue('vlessEncryptionMethod', parsed)
                              patchInbound({ encryption: v })
                            }}
                          />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                )}

                {inbound.protocol === 'vless' && (
                  <FormField
                    control={form.control}
                    name="decryption"
                    render={({ field }) => (
                      <FormItem className="sm:col-span-2">
                        <FormLabel className="text-muted-foreground text-xs font-semibold tracking-wide">{t('coreEditor.field.decryption', { defaultValue: 'Decryption' })}</FormLabel>
                        <FormControl>
                          <Input
                            {...field}
                            dir="ltr"
                            className="h-10 text-xs"
                            placeholder="Optional decryption / flow token (see Xray VLESS inbound docs)"
                            onChange={e => {
                              const v = e.target.value
                              field.onChange(v)
                              setVlessDecryptionJustGenerated(false)
                              patchInbound({ decryption: v })
                            }}
                          />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                )}

                {inbound.protocol === 'vless' && (
                  <div className="sm:col-span-2">
                    <LoaderButton type="button" onClick={openInboundVlessGenerator} className="h-10 w-full text-sm font-medium transition-all hover:shadow-md sm:h-11" isLoading={false}>
                      <span className="flex items-center gap-2 truncate">
                        {vlessDecryptionJustGenerated && <span className="h-2.5 w-2.5 shrink-0 rounded-full bg-green-500 ring-2 ring-green-500/20" />}
                        {t('coreConfigModal.generateVLESSEncryption')}
                      </span>
                    </LoaderButton>
                  </div>
                )}

                {inbound.protocol === 'shadowsocks' && (
                  <>
                    <FormField
                      control={form.control}
                      name="shadowsocksMethod"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel className="text-muted-foreground text-xs font-semibold tracking-wide">
                            {t('coreConfigModal.shadowsocksEncryptionMethod', { defaultValue: 'Encryption Method' })}
                          </FormLabel>
                          <Select
                            dir="ltr"
                            value={field.value}
                            onValueChange={v => {
                              field.onChange(v)
                              setShadowsocksPasswordJustGenerated(false)
                              patchInbound({ method: v as ShadowsocksMethod } as Partial<Inbound>)
                            }}
                          >
                            <FormControl>
                              <SelectTrigger className="h-10 py-2">
                                <SelectValue />
                              </SelectTrigger>
                            </FormControl>
                            <SelectContent dir="ltr">
                              {!SHADOWSOCKS_ENCRYPTION_METHODS.some(m => m.value === field.value) ? <SelectItem value={field.value}>{field.value}</SelectItem> : null}
                              {SHADOWSOCKS_ENCRYPTION_METHODS.map(method => (
                                <SelectItem key={method.value} value={method.value}>
                                  {method.label}
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                          <FormMessage />
                        </FormItem>
                      )}
                    />

                    <FormField
                      control={form.control}
                      name="shadowsocksNetwork"
                      render={({ field }) => (
                        <FormItem className="min-w-0">
                          <FormLabel className="text-muted-foreground text-xs font-semibold tracking-wide">{t('coreEditor.inbound.shadowsocks.network')}</FormLabel>
                          <Select
                            dir="ltr"
                            value={normalizeTunnelNetworkForKit(field.value)}
                            onValueChange={v => {
                              const nw = normalizeTunnelNetworkForKit(v)
                              field.onChange(nw)
                              patchInbound({ network: nw } as Partial<Inbound>)
                            }}
                          >
                            <FormControl>
                              <SelectTrigger className="h-10 w-full min-w-0 py-2">
                                <SelectValue />
                              </SelectTrigger>
                            </FormControl>
                            <SelectContent dir="ltr">
                              <SelectItem value="tcp">TCP</SelectItem>
                              <SelectItem value="udp">UDP</SelectItem>
                              <SelectItem value="tcp,udp">TCP,UDP</SelectItem>
                            </SelectContent>
                          </Select>
                          <FormMessage />
                        </FormItem>
                      )}
                    />

                    <FormField
                      control={form.control}
                      name="shadowsocksPassword"
                      render={({ field }) => (
                        <FormItem className="w-full min-w-0 sm:col-span-2">
                          <FormLabel className="text-muted-foreground text-xs font-semibold tracking-wide">{t('coreConfigModal.shadowsocksPassword')}</FormLabel>
                          <FormControl>
                            <PasswordInput
                              dir="ltr"
                              autoComplete="new-password"
                              className="h-10 w-full"
                              value={field.value}
                              onChange={e => {
                                const v = e.target.value
                                field.onChange(v)
                                setShadowsocksPasswordJustGenerated(false)
                                patchInbound({ password: v } as Partial<Inbound>)
                              }}
                            />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />

                    <div className="sm:col-span-2">
                      <LoaderButton
                        type="button"
                        onClick={generateInboundShadowsocksPassword}
                        className="h-10 w-full text-sm font-medium transition-all hover:shadow-md sm:h-11"
                        isLoading={isGeneratingShadowsocksPassword}
                        loadingText={t('coreConfigModal.generatingShadowsocksPassword')}
                      >
                        <span className="flex items-center gap-2 truncate">
                          {shadowsocksPasswordJustGenerated && <span className="h-2.5 w-2.5 shrink-0 rounded-full bg-green-500 ring-2 ring-green-500/20" />}
                          {t('coreConfigModal.generateShadowsocksPassword')}
                        </span>
                      </LoaderButton>
                    </div>
                  </>
                )}

                {showTransportSection ? <Separator className="my-2 sm:col-span-2" /> : null}

                {showTransportSection ? (
                  <div className="mb-1 flex items-center gap-2 sm:col-span-2">
                    <Cable className="text-muted-foreground h-3.5 w-3.5 shrink-0" aria-hidden />
                    <h3 className="text-sm font-semibold">{t('coreEditor.inbound.transportSection', { defaultValue: 'Transport' })}</h3>
                  </div>
                ) : null}

                {showTransportTypeSelect && (
                  <FormField
                    control={form.control}
                    name="transport"
                    render={({ field }) => (
                      <FormItem className="w-full min-w-0 sm:col-span-2">
                        <FormLabel>{t('coreEditor.field.transport', { defaultValue: 'Transport' })}</FormLabel>
                        <Select
                          value={transportSelectOptions.includes(field.value as Transport['type']) ? field.value : (transportSelectOptions[0] ?? 'tcp')}
                          onValueChange={v => {
                            field.onChange(v)
                            const baseArgs = kitArgsPreservingListenPort(inbound)
                            const transport = v as Transport['type']
                            let next: Inbound
                            switch (inbound.protocol) {
                              case 'vmess': {
                                const st = inbound.security.type
                                const security = st === 'tls' ? ('tls' as const) : ('none' as const)
                                next = createDefaultInbound({
                                  protocol: 'vmess',
                                  ...baseArgs,
                                  transport,
                                  security,
                                  clientDefaults: 'empty',
                                })
                                break
                              }
                              case 'vless': {
                                const st = inbound.security.type
                                const security = st === 'reality' ? ('reality' as const) : st === 'tls' ? ('tls' as const) : ('none' as const)
                                next = createDefaultInbound({
                                  protocol: 'vless',
                                  ...baseArgs,
                                  transport,
                                  security,
                                  clientDefaults: 'empty',
                                })
                                break
                              }
                              case 'trojan': {
                                const st = inbound.security.type
                                const security = st === 'reality' ? ('reality' as const) : st === 'tls' ? ('tls' as const) : ('none' as const)
                                next = createDefaultInbound({
                                  protocol: 'trojan',
                                  ...baseArgs,
                                  transport,
                                  security,
                                  clientDefaults: 'empty',
                                })
                                break
                              }
                              case 'shadowsocks': {
                                const st = inbound.security?.type
                                const security = st === 'tls' ? ('tls' as const) : ('none' as const)
                                next = createDefaultInbound({
                                  protocol: 'shadowsocks',
                                  ...baseArgs,
                                  transport,
                                  security,
                                  clientDefaults: 'empty',
                                })
                                break
                              }
                              default:
                                return
                            }
                            if (inbound.protocol === 'vless' && next.protocol === 'vless') {
                              next = mergeVlessInboundStreamFields(inbound, next)
                            }
                            if (inbound.protocol === 'trojan' && next.protocol === 'trojan') {
                              next = mergeTrojanInboundStreamFields(inbound, next)
                            }
                            if (inbound.protocol === 'shadowsocks' && next.protocol === 'shadowsocks') {
                              next = mergeShadowsocksInboundStreamFields(inbound, next)
                            }
                            next = mergeSecurityAcrossRebuild(inbound, next)
                            next = mergeStreamAdvancedAcrossRebuild(inbound, next)
                            replaceEffectiveInbound(next)
                            if ('transport' in next && next.transport) form.setValue('transport', next.transport.type)
                            if ('security' in next && next.security) form.setValue('security', next.security.type)
                            if (next.protocol === 'vless') {
                              syncVlessFieldsFromInboundForm(form, next)
                            }
                            if (next.protocol === 'shadowsocks') {
                              form.setValue('shadowsocksMethod', shadowsocksMethodFormValue(next))
                              form.setValue('shadowsocksPassword', shadowsocksPasswordFormValue(next))
                              form.setValue('shadowsocksNetwork', shadowsocksNetworkFormValue(next))
                            }
                            syncSecurityFormFields(next)
                            syncTransportFormFields(next)
                            syncTunnelFormFieldsFromInbound(next)
                            syncTunFormFieldsFromInbound(next)
                            syncWireguardFormFieldsFromInbound(next)
                          }}
                        >
                          <FormControl>
                            <SelectTrigger className="h-10 w-full py-2">
                              <SelectValue />
                            </SelectTrigger>
                          </FormControl>
                          <SelectContent>
                            {transportSelectOptions.map(transportName => (
                              <SelectItem key={transportName} value={transportName}>
                                {transportName}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                )}

                {inbound.protocol === 'hysteria' && (
                  <>
                    <FormField
                      control={form.control}
                      name="hysteriaAuth"
                      render={({ field }) => (
                        <FormItem className="sm:col-span-2">
                          <FormLabel className="text-muted-foreground text-xs font-semibold tracking-wide">{t('coreEditor.inbound.hysteria.auth', { defaultValue: 'Auth' })}</FormLabel>
                          <FormControl>
                            <div className={cn('flex w-full min-w-0 items-center gap-2', dir === 'rtl' && 'flex-row-reverse')}>
                              <div className="min-w-0 flex-1">
                                <PasswordInput
                                  dir="ltr"
                                  autoComplete="new-password"
                                  className="h-10 w-full"
                                  value={field.value ?? ''}
                                  onChange={e => {
                                    const v = e.target.value
                                    field.onChange(v)
                                    patchHysteriaServerSettings({ auth: v })
                                  }}
                                />
                              </div>
                              <Button
                                type="button"
                                variant="ghost"
                                size="icon"
                                onClick={generateHysteriaAuth}
                                className="shrink-0"
                                title={t('coreEditor.inbound.hysteria.generateAuth', { defaultValue: 'Generate auth key' })}
                              >
                                <RefreshCw className="h-3 w-3" aria-hidden />
                              </Button>
                            </div>
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                    <FormField
                      control={form.control}
                      name="hysteriaUdpIdleTimeout"
                      render={({ field, fieldState }) => (
                        <FormItem>
                          <FormLabel className="text-muted-foreground text-xs font-semibold tracking-wide">
                            {t('coreEditor.inbound.hysteria.udpIdleTimeout', { defaultValue: 'UDP Idle Timeout (seconds)' })}
                          </FormLabel>
                          <FormControl>
                            <Input
                              dir="ltr"
                              className="h-10"
                              isError={!!fieldState.error}
                              value={field.value ?? ''}
                              onChange={e => {
                                const v = e.target.value
                                field.onChange(v)
                                const trimmed = v.trim()
                                if (trimmed === '') {
                                  patchHysteriaServerSettings({ udpIdleTimeout: undefined })
                                  return
                                }
                                const parsed = Number(trimmed)
                                if (Number.isFinite(parsed)) patchHysteriaServerSettings({ udpIdleTimeout: parsed })
                              }}
                            />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                    <FormField
                      control={form.control}
                      name="hysteriaMasqueradeType"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel className="text-muted-foreground text-xs font-semibold tracking-wide">
                            {t('coreEditor.inbound.hysteria.masqueradeType', { defaultValue: 'Masquerade Type' })}
                          </FormLabel>
                          <Select
                            value={field.value || '__none'}
                            onValueChange={v => {
                              field.onChange(v)
                              if (v === '__none') patchHysteriaServerSettings({ masquerade: undefined })
                              else {
                                patchHysteriaServerSettings({
                                  masquerade: {
                                    type: v,
                                    dir: undefined,
                                    url: undefined,
                                    content: undefined,
                                  },
                                })
                              }
                            }}
                          >
                            <FormControl>
                              <SelectTrigger className="h-10">
                                <SelectValue />
                              </SelectTrigger>
                            </FormControl>
                            <SelectContent>
                              <SelectItem value="__none">{t('coreEditor.inbound.hysteria.masqueradeNone', { defaultValue: 'None' })}</SelectItem>
                              <SelectItem value="file">{t('coreEditor.inbound.hysteria.masqueradeFile', { defaultValue: 'file' })}</SelectItem>
                              <SelectItem value="proxy">{t('coreEditor.inbound.hysteria.masqueradeProxy', { defaultValue: 'proxy' })}</SelectItem>
                              <SelectItem value="string">{t('coreEditor.inbound.hysteria.masqueradeString', { defaultValue: 'string' })}</SelectItem>
                            </SelectContent>
                          </Select>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                    {hysteriaMasqueradeType === 'file' && (
                      <FormField
                        control={form.control}
                        name="hysteriaMasqueradeDir"
                        render={({ field }) => (
                          <FormItem className="sm:col-span-2">
                            <FormLabel className="text-muted-foreground text-xs font-semibold tracking-wide">{t('coreEditor.inbound.hysteria.masqueradeDir', { defaultValue: 'Directory' })}</FormLabel>
                            <FormControl>
                              <Input
                                dir="ltr"
                                className="h-10"
                                value={field.value ?? ''}
                                onChange={e => {
                                  const v = e.target.value
                                  field.onChange(v)
                                  patchHysteriaServerSettings({ masquerade: { type: 'file', dir: v } })
                                }}
                              />
                            </FormControl>
                            <FormMessage />
                          </FormItem>
                        )}
                      />
                    )}
                    {hysteriaMasqueradeType === 'proxy' && (
                      <FormField
                        control={form.control}
                        name="hysteriaMasqueradeUrl"
                        render={({ field }) => (
                          <FormItem className="sm:col-span-2">
                            <FormLabel className="text-muted-foreground text-xs font-semibold tracking-wide">{t('coreEditor.inbound.hysteria.masqueradeUrl', { defaultValue: 'URL' })}</FormLabel>
                            <FormControl>
                              <Input
                                dir="ltr"
                                className="h-10"
                                value={field.value ?? ''}
                                onChange={e => {
                                  const v = e.target.value
                                  field.onChange(v)
                                  patchHysteriaServerSettings({ masquerade: { type: 'proxy', url: v } })
                                }}
                              />
                            </FormControl>
                            <FormMessage />
                          </FormItem>
                        )}
                      />
                    )}
                    {hysteriaMasqueradeType === 'string' && (
                      <FormField
                        control={form.control}
                        name="hysteriaMasqueradeContent"
                        render={({ field }) => (
                          <FormItem className="sm:col-span-2">
                            <FormLabel className="text-muted-foreground text-xs font-semibold tracking-wide">
                              {t('coreEditor.inbound.hysteria.masqueradeContent', { defaultValue: 'Content' })}
                            </FormLabel>
                            <FormControl>
                              <Textarea
                                dir="ltr"
                                rows={4}
                                className="text-xs"
                                value={field.value ?? ''}
                                onChange={e => {
                                  const v = e.target.value
                                  field.onChange(v)
                                  patchHysteriaServerSettings({ masquerade: { type: 'string', content: v } })
                                }}
                              />
                            </FormControl>
                            <FormMessage />
                          </FormItem>
                        )}
                      />
                    )}
                  </>
                )}

                {showTransportSettings && inboundTransportType && transportSettingsFieldOrder.length > 0 && (
                  <>
                    <Separator className="my-2 sm:col-span-2" />
                    <div className="sm:col-span-2">
                      <h4 className="text-muted-foreground mb-3 text-xs font-semibold tracking-wide uppercase">
                        {t('coreEditor.inbound.transportAdvanced.title', { defaultValue: 'Transport settings' })}
                      </h4>
                      <div className="grid gap-3 sm:grid-cols-2">
                        {inboundTransportType === 'xhttp' && (
                          <div className="space-y-3 rounded-lg border px-3 py-2 sm:col-span-2">
                            <div className="flex items-center justify-between">
                              <FormLabel className="text-xs font-medium">{t('hostsDialog.xhttp.xPaddingObfsMode', { defaultValue: 'X-Padding Obfs Mode' })}</FormLabel>
                              <Switch
                                checked={xPaddingObfsEnabled}
                                onCheckedChange={checked => {
                                  const updates: Record<string, unknown> = { xpaddingobfsmode: checked }
                                  if (checked) {
                                    const paddingBytesCurrent = getTransportMetaValue(xhttpExtra, 'xpaddingbytes')
                                    const hasPaddingBytes = paddingBytesCurrent !== undefined && String(paddingBytesCurrent).trim() !== '' && String(paddingBytesCurrent).trim() !== '0-0'
                                    if (!hasPaddingBytes) updates.xpaddingbytes = '100-1000'
                                  }
                                  updateXhttpMetaBatch(updates)
                                }}
                              />
                            </div>

                            {xPaddingObfsEnabled && (
                              <div className="grid gap-3 sm:grid-cols-2">
                                <FormItem>
                                  <FormLabel className="text-xs font-medium">{t('hostsDialog.xhttp.xPaddingKey', { defaultValue: 'X-Padding Key' })}</FormLabel>
                                  <FormControl>
                                    <Input
                                      dir="ltr"
                                      className="h-10 text-xs"
                                      value={String(getTransportMetaValue(xhttpExtra, 'xpaddingkey') ?? '')}
                                      onChange={e => updateXhttpMeta('xpaddingkey', e.target.value)}
                                    />
                                  </FormControl>
                                </FormItem>

                                <FormItem>
                                  <FormLabel className="text-xs font-medium">{t('hostsDialog.xhttp.xPaddingHeader', { defaultValue: 'X-Padding Header' })}</FormLabel>
                                  <FormControl>
                                    <Input
                                      dir="ltr"
                                      className="h-10 text-xs"
                                      value={String(getTransportMetaValue(xhttpExtra, 'xpaddingheader') ?? '')}
                                      onChange={e => updateXhttpMeta('xpaddingheader', e.target.value)}
                                    />
                                  </FormControl>
                                </FormItem>

                                <FormItem>
                                  <FormLabel className="text-xs font-medium">{t('hostsDialog.xhttp.xPaddingPlacement', { defaultValue: 'X-Padding Placement' })}</FormLabel>
                                  <Select
                                    value={String(getTransportMetaValue(xhttpExtra, 'xpaddingplacement') ?? '__default')}
                                    onValueChange={v => updateXhttpMeta('xpaddingplacement', v === '__default' ? '' : v)}
                                  >
                                    <FormControl>
                                      <SelectTrigger className="h-10">
                                        <SelectValue />
                                      </SelectTrigger>
                                    </FormControl>
                                    <SelectContent>
                                      <SelectItem value="__default">{t('coreEditor.parityUi.selectDefault', { defaultValue: 'Default' })}</SelectItem>
                                      <SelectItem value="queryInHeader">queryInHeader</SelectItem>
                                      <SelectItem value="query">query</SelectItem>
                                      <SelectItem value="header">header</SelectItem>
                                      <SelectItem value="cookie">cookie</SelectItem>
                                    </SelectContent>
                                  </Select>
                                </FormItem>

                                <FormItem>
                                  <FormLabel className="text-xs font-medium">{t('hostsDialog.xhttp.xPaddingMethod', { defaultValue: 'X-Padding Method' })}</FormLabel>
                                  <Select
                                    value={String(getTransportMetaValue(xhttpExtra, 'xpaddingmethod') ?? '__default')}
                                    onValueChange={v => updateXhttpMeta('xpaddingmethod', v === '__default' ? '' : v)}
                                  >
                                    <FormControl>
                                      <SelectTrigger className="h-10">
                                        <SelectValue />
                                      </SelectTrigger>
                                    </FormControl>
                                    <SelectContent>
                                      <SelectItem value="__default">{t('coreEditor.parityUi.selectDefault', { defaultValue: 'Default' })}</SelectItem>
                                      <SelectItem value="repeat-x">repeat-x</SelectItem>
                                      <SelectItem value="tokenish">tokenish</SelectItem>
                                    </SelectContent>
                                  </Select>
                                </FormItem>
                              </div>
                            )}
                          </div>
                        )}

                        {transportSettingsFieldOrder.map((jsonKey: string) => {
                          const def = caps.transportSettingsFieldDefinitions[inboundTransportType]?.[jsonKey]
                          if (!def) return null
                          const normalizedTransportKey = normalizeTransportMetaKey(jsonKey)
                          const isXhttpClientOnlyField =
                            normalizedTransportKey === 'nogrpcheader' ||
                            normalizedTransportKey === 'scminpostsintervalms' ||
                            normalizedTransportKey === 'xmux' ||
                            normalizedTransportKey === 'downloadsettings'
                          if (inboundTransportType === 'xhttp' && isXhttpClientOnlyField) return null
                          const isXhttpCustomManagedField =
                            normalizedTransportKey === 'xpaddingobfsmode' ||
                            normalizedTransportKey === 'xpaddingbytes' ||
                            normalizedTransportKey === 'xpaddingkey' ||
                            normalizedTransportKey === 'xpaddingheader' ||
                            normalizedTransportKey === 'xpaddingplacement' ||
                            normalizedTransportKey === 'xpaddingmethod' ||
                            normalizedTransportKey === 'extra'
                          if (inboundTransportType === 'xhttp' && isXhttpCustomManagedField) return null
                          const isXPaddingAdvancedField =
                            normalizedTransportKey === 'xpaddingkey' ||
                            normalizedTransportKey === 'xpaddingheader' ||
                            normalizedTransportKey === 'xpaddingplacement' ||
                            normalizedTransportKey === 'xpaddingmethod'
                          if (inboundTransportType === 'xhttp' && isXPaddingAdvancedField && !xPaddingObfsEnabled) return null
                          const name = transportFieldName(jsonKey)
                          const wide = inferParityFieldMode(def) !== 'scalar'
                          const isBoolean = isBooleanParityField(def)
                          const transportFieldSpansTwo = wide || isBoolean || normalizedTransportKey === 'heartbeatperiod'
                          return (
                            <FormField
                              key={jsonKey}
                              control={form.control}
                              name={name}
                              render={({ field }) => (
                                <FormItem className={cn('w-full min-w-0', transportFieldSpansTwo && 'sm:col-span-2')}>
                                  {!isBooleanParityField(def) && !isJsonRawMessageField(def) && <FormLabel className="text-xs font-medium">{transportParityFieldLabel(def, t)}</FormLabel>}
                                  {isJsonRawMessageField(def) && inboundTransportType === 'tcp' ? (
                                    <>
                                      <div className="flex items-center justify-between rounded-lg border px-3 py-2">
                                        <FormLabel className="font-medium">{t('coreEditor.inbound.tcp.httpObfuscation', { defaultValue: 'HTTP Obfuscation' })}</FormLabel>
                                        <FormControl>
                                          <Switch
                                            checked={isTcpHttpObfuscationEnabled(field.value)}
                                            onCheckedChange={(checked: boolean) => {
                                              const defaultValue = JSON.stringify(
                                                {
                                                  type: 'http',
                                                  request: { version: '1.1', method: 'GET', path: ['/'], headers: {} },
                                                  response: { version: '1.1', status: '200', reason: 'OK', headers: {} },
                                                },
                                                null,
                                                2,
                                              )
                                              const newFieldValue = checked ? defaultValue : ''
                                              field.onChange(newFieldValue)

                                              if (!inbound || !('transport' in inbound) || !inbound.transport) {
                                                return
                                              }

                                              const cur = { ...(inbound.transport as unknown as Record<string, unknown>) }
                                              const transportType = inbound.transport.type
                                              cur.type = transportType

                                              if (checked) {
                                                try {
                                                  const parsed = parseOutboundSettingValue(def, defaultValue)
                                                  cur[jsonKey] = parsed
                                                } catch (e) {
                                                  console.error('Failed to parse HTTP obfuscation value:', e)
                                                  return
                                                }
                                              } else {
                                                delete cur[jsonKey]
                                              }

                                              patchInbound({ transport: cur as Transport } as Partial<Inbound>)
                                            }}
                                          />
                                        </FormControl>
                                      </div>
                                      {isTcpHttpObfuscationEnabled(field.value) && (
                                        <FormControl className="sm:col-span-2">
                                          <TcpHeaderObfuscationForm
                                            currentValue={(() => {
                                              try {
                                                return JSON.parse(field.value as string)
                                              } catch {
                                                return null
                                              }
                                            })()}
                                            onValueChange={next => {
                                              const stringified = JSON.stringify(next, null, 2)
                                              field.onChange(stringified)
                                              try {
                                                patchTransport({ [jsonKey]: parseOutboundSettingValue(def, stringified) })
                                              } catch {
                                                /* invalid JSON fragment — wait for valid input */
                                              }
                                            }}
                                          />
                                        </FormControl>
                                      )}
                                    </>
                                  ) : (
                                    <>
                                      <XrayParityFormControl
                                        field={def}
                                        value={field.value ?? ''}
                                        placeholder={inboundTransportParityPlaceholder(jsonKey)}
                                        renderBooleanAsToggleRow={isBooleanParityField(def)}
                                        onChange={v => {
                                          field.onChange(v)
                                          try {
                                            const parsed = parseOutboundSettingValue(def, v)
                                            if (
                                              inboundTransportType === 'xhttp' &&
                                              normalizedTransportKey === 'xpaddingobfsmode' &&
                                              (parsed === true || parsed === 'true' || parsed === 1 || parsed === '1')
                                            ) {
                                              const paddingBytesCurrent = getTransportMetaValue(inboundTransport, 'xpaddingbytes')
                                              const hasPaddingBytes = paddingBytesCurrent !== undefined && String(paddingBytesCurrent).trim() !== '' && String(paddingBytesCurrent).trim() !== '0-0'
                                              if (!hasPaddingBytes) {
                                                patchTransport({ [jsonKey]: parsed, [xPaddingBytesKey]: '100-1000' })
                                                return
                                              }
                                            }
                                            patchTransport({ [jsonKey]: parsed })
                                          } catch {
                                            /* invalid JSON fragment — wait for valid input */
                                          }
                                        }}
                                      />
                                      <FormMessage />
                                    </>
                                  )}
                                </FormItem>
                              )}
                            />
                          )
                        })}
                      </div>
                    </div>
                  </>
                )}

                {showTransportSection ? <Separator className="my-2 sm:col-span-2" /> : null}

                <div className="mb-1 flex items-center gap-2 sm:col-span-2">
                  <Shield className="text-muted-foreground h-3.5 w-3.5 shrink-0" aria-hidden />
                  <h3 className="text-sm font-semibold">{t('coreEditor.inbound.securitySection', { defaultValue: 'Security' })}</h3>
                </div>

                <FormField
                  control={form.control}
                  name="security"
                  render={({ field }) => (
                    <FormItem className="w-full min-w-0 sm:col-span-2">
                      <FormLabel>{t('coreEditor.field.securityType', { defaultValue: 'Security type' })}</FormLabel>
                      <Select
                        value={field.value}
                        onValueChange={v => {
                          field.onChange(v)
                          const baseArgs = kitArgsPreservingListenPort(inbound)
                          const security = v as 'none' | 'tls' | 'reality'
                          let next: Inbound
                          switch (inbound.protocol) {
                            case 'hysteria':
                              next = createDefaultInbound({
                                protocol: 'hysteria',
                                ...baseArgs,
                                security: security === 'reality' ? 'tls' : security,
                                clientDefaults: 'empty',
                              })
                              break
                            case 'vmess':
                              next = createDefaultInbound({
                                protocol: 'vmess',
                                ...baseArgs,
                                transport: inbound.transport?.type ?? 'tcp',
                                security: security === 'reality' ? 'tls' : security,
                                clientDefaults: 'empty',
                              })
                              break
                            case 'vless': {
                              let tr = inbound.transport?.type ?? 'tcp'
                              if (security === 'reality' && !transportCompatibleWithReality(tr)) tr = 'tcp'
                              next = createDefaultInbound({
                                protocol: 'vless',
                                ...baseArgs,
                                transport: tr,
                                security,
                                clientDefaults: 'empty',
                              })
                              break
                            }
                            case 'trojan': {
                              let tr = inbound.transport?.type ?? 'tcp'
                              if (security === 'reality' && !transportCompatibleWithReality(tr)) tr = 'tcp'
                              next = createDefaultInbound({
                                protocol: 'trojan',
                                ...baseArgs,
                                transport: tr,
                                security,
                                clientDefaults: 'empty',
                              })
                              break
                            }
                            case 'shadowsocks':
                              next = createDefaultInbound({
                                protocol: 'shadowsocks',
                                ...baseArgs,
                                transport: inbound.transport?.type ?? 'tcp',
                                security: security === 'reality' ? 'tls' : security,
                                clientDefaults: 'empty',
                              })
                              break
                            default:
                              return
                          }
                          if (inbound.protocol === 'vless' && next.protocol === 'vless') {
                            next = mergeVlessInboundStreamFields(inbound, next)
                          }
                          if (inbound.protocol === 'trojan' && next.protocol === 'trojan') {
                            next = mergeTrojanInboundStreamFields(inbound, next)
                          }
                          if (inbound.protocol === 'shadowsocks' && next.protocol === 'shadowsocks') {
                            next = mergeShadowsocksInboundStreamFields(inbound, next)
                          }
                          next = mergeTransportAcrossRebuild(inbound, next)
                          next = mergeStreamAdvancedAcrossRebuild(inbound, next)

                          // Clear REALITY security defaults to avoid auto-population
                          if (security === 'reality' && 'security' in next && next.security?.type === 'reality') {
                            const clearedSecurity = { ...next.security }
                            for (const key of Object.keys(clearedSecurity)) {
                              if (key !== 'type' && !['fingerprint'].includes(key)) {
                                delete (clearedSecurity as Record<string, unknown>)[key]
                              }
                            }
                            next = { ...next, security: clearedSecurity } as Inbound
                          }

                          replaceEffectiveInbound(next)
                          if ('security' in next && next.security) form.setValue('security', next.security.type)
                          if ('transport' in next && next.transport) form.setValue('transport', next.transport.type)
                          if (next.protocol === 'vless') {
                            syncVlessFieldsFromInboundForm(form, next)
                          }
                          if (next.protocol === 'shadowsocks') {
                            form.setValue('shadowsocksMethod', shadowsocksMethodFormValue(next))
                            form.setValue('shadowsocksPassword', shadowsocksPasswordFormValue(next))
                            form.setValue('shadowsocksNetwork', shadowsocksNetworkFormValue(next))
                          }
                          syncSecurityFormFields(next)
                          syncTransportFormFields(next)
                          syncTunnelFormFieldsFromInbound(next)
                          syncTunFormFieldsFromInbound(next)
                          syncWireguardFormFieldsFromInbound(next)
                        }}
                      >
                        <FormControl>
                          <SelectTrigger className="h-10 w-full py-2">
                            <SelectValue />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          {securitySelectOptions.map(securityName => (
                            <SelectItem key={securityName} value={securityName}>
                              {securityName}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                {inbound.protocol === 'vless' && (
                  <FormField
                    control={form.control}
                    name="vlessFlow"
                    render={({ field }) => {
                      const flow = field.value ?? ''
                      return (
                        <FormItem className="sm:col-span-2">
                          <FormLabel className="text-muted-foreground text-xs font-semibold tracking-wide">{t('coreEditor.field.flow', { defaultValue: 'Flow' })}</FormLabel>
                          <Select
                            dir="ltr"
                            value={vlessInboundFlowsOk && (VLESS_INBOUND_FLOW_VALUES as readonly string[]).includes(flow) ? flow : '__none'}
                            onValueChange={v => {
                              const next = v === '__none' ? '' : v
                              field.onChange(next)
                              if (next.trim() === '') patchInbound({ flow: '' } as Partial<Inbound>)
                              else patchInbound({ flow: next } as Partial<Inbound>)
                            }}
                          >
                            <FormControl>
                              <SelectTrigger className="h-10 w-full min-w-0 py-2">
                                <SelectValue />
                              </SelectTrigger>
                            </FormControl>
                            <SelectContent>
                              <SelectItem value="__none">{t('coreEditor.inbound.vlessFlowDefault', { defaultValue: 'Default (standard TLS proxy)' })}</SelectItem>
                              {vlessInboundFlowsOk
                                ? VLESS_INBOUND_FLOW_VALUES.map(f => (
                                    <SelectItem key={f} value={f}>
                                      {f}
                                    </SelectItem>
                                  ))
                                : null}
                            </SelectContent>
                          </Select>
                          {!vlessInboundFlowsOk ? (
                            <p className="text-muted-foreground text-xs">
                              {t('coreEditor.inbound.vlessFlowVisionRequiresTls', {
                                defaultValue: 'XTLS Vision requires TCP with TLS/REALITY, or VLESS Encryption.',
                              })}
                            </p>
                          ) : null}
                          <FormMessage />
                        </FormItem>
                      )
                    }}
                  />
                )}

                {inboundSecurityType && securityFieldOrder.length > 0 && (
                  <>
                    <Separator className="my-2 sm:col-span-2" />
                    <div className="sm:col-span-2">
                      <h4 className="text-muted-foreground mb-3 text-xs font-semibold tracking-wide uppercase">
                        {t('coreEditor.inbound.securityAdvanced.title', { defaultValue: 'Security settings' })}
                      </h4>
                      <div className="grid gap-3 sm:grid-cols-2">
                        {inboundSecurityType === 'tls' && (
                          <div className="space-y-2 sm:col-span-2">
                            <div className="flex items-center justify-between">
                              <FormLabel className="text-xs font-medium">{t('coreEditor.inbound.tlsCertificates.sectionLabel', { defaultValue: 'Certificates' })}</FormLabel>
                              <Button
                                type="button"
                                variant="outline"
                                size="icon"
                                className="size-7"
                                onClick={() =>
                                  setTlsCertificates([
                                    ...tlsCertificates,
                                    {
                                      mode: 'path',
                                      certificateFile: '',
                                      keyFile: '',
                                      certificate: '',
                                      key: '',
                                      ocspStapling: '',
                                      serveOnNode: false,
                                    },
                                  ])
                                }
                              >
                                <Plus className="size-4" />
                              </Button>
                            </div>
                            {tlsCertificates.length === 0 ? (
                              <div className="text-muted-foreground rounded-md border border-dashed px-3 py-2 text-xs">
                                {t('coreEditor.inbound.tlsCertificates.emptyHint', {
                                  defaultValue: 'No certificates yet. Click + to add one.',
                                })}
                              </div>
                            ) : (
                              <div className="space-y-2">
                                {tlsCertificates.map((cert, index) => (
                                  <div key={`tls-cert-${index}`} className="space-y-2 rounded-md border p-2">
                                    <div className="flex items-center justify-between gap-2">
                                      <span className="text-muted-foreground text-xs font-medium">
                                        {t('coreEditor.inbound.tlsCertificates.certIndex', {
                                          index: index + 1,
                                          defaultValue: `Certificate #${index + 1}`,
                                        })}
                                      </span>
                                      <Button
                                        type="button"
                                        variant="ghost"
                                        size="icon"
                                        className="size-9 shrink-0 border-red-500/20 transition-colors hover:border-red-500 hover:bg-red-50 dark:hover:bg-red-950/20"
                                        onClick={() => {
                                          const next = tlsCertificates.filter((_, i) => i !== index)
                                          setTlsCertificates(next)
                                        }}
                                      >
                                        <Trash2 className="text-red-500" />
                                      </Button>
                                    </div>
                                    <Tabs
                                      value={cert.mode}
                                      onValueChange={v => {
                                        const mode = v === 'content' ? 'content' : 'path'
                                        if (mode === cert.mode) return
                                        const next = [...tlsCertificates]
                                        next[index] = { ...next[index], mode }
                                        setTlsCertificates(next)
                                      }}
                                    >
                                      <TabsList className="grid w-full grid-cols-2">
                                        <TabsTrigger value="path">{t('coreEditor.inbound.tlsCertificates.filePathTab', { defaultValue: 'File path' })}</TabsTrigger>
                                        <TabsTrigger value="content">{t('coreEditor.inbound.tlsCertificates.fileContentTab', { defaultValue: 'File content' })}</TabsTrigger>
                                      </TabsList>
                                    </Tabs>
                                    <div className="flex items-start gap-2 rounded-md border border-dashed px-2 py-2">
                                      <Checkbox
                                        id={`inbound-tls-cert-serve-on-node-${index}`}
                                        checked={cert.serveOnNode}
                                        onCheckedChange={checked => {
                                          const next = [...tlsCertificates]
                                          next[index] = { ...next[index], serveOnNode: checked === true }
                                          setTlsCertificates(next)
                                        }}
                                      />
                                      <div className="grid gap-0.5 leading-tight">
                                        <label htmlFor={`inbound-tls-cert-serve-on-node-${index}`} className="cursor-pointer text-xs font-medium">
                                          {t('coreEditor.inbound.tlsCertificateServeOnNode', { defaultValue: 'Serve on node' })}
                                        </label>
                                        <p className="text-muted-foreground text-[11px]">
                                          {t('coreEditor.inbound.tlsCertificateServeOnNodeHint', {
                                            defaultValue: 'Certificate files are only used on the node; the server will not read them for SNI.',
                                          })}
                                        </p>
                                      </div>
                                    </div>
                                    <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                                      {cert.mode === 'path' ? (
                                        <>
                                          <div className="space-y-1">
                                            <FormLabel className="text-muted-foreground text-[11px] font-medium">
                                              {t('coreEditor.inbound.tlsCertificates.certificateFile', { defaultValue: 'Certificate file' })}
                                            </FormLabel>
                                            <Input
                                              dir="ltr"
                                              className="text-xs"
                                              placeholder="/path/fullchain.pem"
                                              defaultValue={cert.certificateFile}
                                              onBlur={e => {
                                                if (e.target.value === cert.certificateFile) return
                                                const next = [...tlsCertificates]
                                                next[index] = { ...next[index], certificateFile: e.target.value }
                                                setTlsCertificates(next)
                                              }}
                                            />
                                          </div>
                                          <div className="space-y-1">
                                            <FormLabel className="text-muted-foreground text-[11px] font-medium">
                                              {t('coreEditor.inbound.tlsCertificates.keyFile', { defaultValue: 'Key file' })}
                                            </FormLabel>
                                            <Input
                                              dir="ltr"
                                              className="text-xs"
                                              placeholder="/path/key.pem"
                                              defaultValue={cert.keyFile}
                                              onBlur={e => {
                                                if (e.target.value === cert.keyFile) return
                                                const next = [...tlsCertificates]
                                                next[index] = { ...next[index], keyFile: e.target.value }
                                                setTlsCertificates(next)
                                              }}
                                            />
                                          </div>
                                        </>
                                      ) : (
                                        <>
                                          <div className="space-y-1">
                                            <FormLabel className="text-muted-foreground text-[11px] font-medium">
                                              {t('coreEditor.inbound.tlsCertificates.certificateContent', { defaultValue: 'Certificate content' })}
                                            </FormLabel>
                                            <Textarea
                                              dir="ltr"
                                              rows={5}
                                              className="text-xs"
                                              placeholder="-----BEGIN CERTIFICATE-----"
                                              defaultValue={cert.certificate}
                                              onBlur={e => {
                                                if (e.target.value === cert.certificate) return
                                                const next = [...tlsCertificates]
                                                next[index] = { ...next[index], certificate: e.target.value }
                                                setTlsCertificates(next)
                                              }}
                                            />
                                          </div>
                                          <div className="space-y-1">
                                            <FormLabel className="text-muted-foreground text-[11px] font-medium">
                                              {t('coreEditor.inbound.tlsCertificates.keyContent', { defaultValue: 'Key content' })}
                                            </FormLabel>
                                            <Textarea
                                              dir="ltr"
                                              rows={5}
                                              className="text-xs"
                                              placeholder="-----BEGIN PRIVATE KEY-----"
                                              defaultValue={cert.key}
                                              onBlur={e => {
                                                if (e.target.value === cert.key) return
                                                const next = [...tlsCertificates]
                                                next[index] = { ...next[index], key: e.target.value }
                                                setTlsCertificates(next)
                                              }}
                                            />
                                          </div>
                                        </>
                                      )}
                                      <div className="space-y-1 sm:col-span-2">
                                        <FormLabel className="text-muted-foreground text-[11px] font-medium">
                                          {t('coreEditor.inbound.tlsCertificates.ocspStapling', { defaultValue: 'OCSP stapling' })}
                                        </FormLabel>
                                        <Input
                                          dir="ltr"
                                          className="h-9 w-full text-xs"
                                          type="number"
                                          inputMode="numeric"
                                          placeholder="3600"
                                          defaultValue={cert.ocspStapling}
                                          onBlur={e => {
                                            if (e.target.value === cert.ocspStapling) return
                                            const next = [...tlsCertificates]
                                            next[index] = { ...next[index], ocspStapling: e.target.value }
                                            setTlsCertificates(next)
                                          }}
                                        />
                                      </div>
                                    </div>
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        )}

                        {displaySecurityFieldOrderMain.map(jsonKey => {
                          if (inbound.protocol === 'hysteria' && inboundSecurityType === 'tls' && (jsonKey === 'minVersion' || jsonKey === 'maxVersion')) {
                            return null
                          }
                          if (inboundSecurityType === 'tls' && (jsonKey === 'echServerKeys' || jsonKey === 'echConfigList' || jsonKey === 'echForceQuery')) {
                            return null
                          }
                          const def = caps.securityFieldDefinitions[inboundSecurityType]?.[jsonKey]
                          if (!def) return null
                          const name = securityFieldName(jsonKey)
                          const wide = inferParityFieldMode(def) !== 'scalar'
                          const isBoolean = isBooleanParityField(def)
                          const isReality = inboundSecurityType === 'reality'
                          const securityFieldFullWidth = wide || isBoolean || jsonKey === 'serverName' || jsonKey === 'serverNames'

                          return (
                            <Fragment key={jsonKey}>
                              {jsonKey !== 'echSockopt' && (
                                <FormField
                                  control={form.control}
                                  name={name}
                                  render={({ field }) => (
                                    <FormItem className={cn('w-full min-w-0', securityFieldFullWidth && 'sm:col-span-2')}>
                                      {!isBoolean && <FormLabel className="text-xs font-medium">{transportParityFieldLabel(def, t)}</FormLabel>}
                                      <XrayParityFormControl
                                        field={def}
                                        value={field.value ?? ''}
                                        placeholder={inboundSecurityParityPlaceholder(jsonKey)}
                                        renderBooleanAsToggleRow={isBoolean}
                                        disabled={isReality && jsonKey === 'publicKey'}
                                        onChange={v => {
                                          field.onChange(v)
                                          try {
                                            patchSecurity({ [jsonKey]: parseOutboundSettingValue(def, v) })
                                          } catch {
                                            /* invalid JSON fragment — wait for valid input */
                                          }
                                          revalidateRealityInboundForm()
                                        }}
                                      />
                                      <FormMessage />
                                    </FormItem>
                                  )}
                                />
                              )}
                              {inboundSecurityType === 'tls' && jsonKey === 'echSockopt' && (
                                <Accordion type="single" collapsible className="w-full min-w-0 sm:col-span-2">
                                  <AccordionItem value="ech" className={INBOUND_SECURITY_SUBACCORDION_ITEM_CLASS}>
                                    <AccordionTrigger>
                                      <div className="flex min-w-0 items-center gap-2">
                                        <KeyRound className="text-muted-foreground h-4 w-4 shrink-0" aria-hidden />
                                        <span className="truncate text-left">
                                          {t('coreEditor.inbound.ech.sectionTitle', {
                                            defaultValue: 'ECH (Encrypted Client Hello)',
                                          })}
                                        </span>
                                      </div>
                                    </AccordionTrigger>
                                    <AccordionContent className="space-y-4 px-2 pb-4">
                                      <p className="text-muted-foreground text-xs leading-relaxed">
                                        {t('coreEditor.inbound.ech.sectionHint', {
                                          defaultValue: 'Configure ECH server keys, config list, and force-query behavior. Generate fills key material according to the usage option.',
                                        })}
                                      </p>
                                      <div className="grid gap-3 sm:grid-cols-2">
                                        <FormItem className="w-full min-w-0">
                                          <FormLabel className="text-muted-foreground text-xs font-medium">{t('coreEditor.inbound.ech.usageOption', { defaultValue: 'Usage option' })}</FormLabel>
                                          <Select value={echUsageOption} onValueChange={v => setEchUsageOption(v as 'default' | 'required' | 'preferred')}>
                                            <FormControl>
                                              <SelectTrigger className="h-10 w-full min-w-0">
                                                <SelectValue />
                                              </SelectTrigger>
                                            </FormControl>
                                            <SelectContent>
                                              <SelectItem value="default">{t('coreEditor.inbound.ech.usageDefault', { defaultValue: 'Default' })}</SelectItem>
                                              <SelectItem value="preferred">{t('coreEditor.inbound.ech.usagePreferred', { defaultValue: 'Preferred' })}</SelectItem>
                                              <SelectItem value="required">{t('coreEditor.inbound.ech.usageRequired', { defaultValue: 'Required' })}</SelectItem>
                                            </SelectContent>
                                          </Select>
                                        </FormItem>

                                        <FormField
                                          control={form.control}
                                          name={securityFieldName('echForceQuery')}
                                          render={({ field }) => (
                                            <FormItem className="w-full min-w-0">
                                              <FormLabel className="text-muted-foreground text-xs font-medium">{t('coreEditor.inbound.ech.forceQuery', { defaultValue: 'ECH force query' })}</FormLabel>
                                              <Select
                                                value={field.value && String(field.value).trim() !== '' ? field.value : '__default'}
                                                onValueChange={v => {
                                                  const next = v === '__default' ? '' : v
                                                  field.onChange(next)
                                                  applyTlsEchPatch({ echForceQuery: next })
                                                }}
                                              >
                                                <FormControl>
                                                  <SelectTrigger className="h-10 w-full min-w-0">
                                                    <SelectValue />
                                                  </SelectTrigger>
                                                </FormControl>
                                                <SelectContent>
                                                  <SelectItem value="__default">{t('coreEditor.inbound.ech.forceQueryDefault', { defaultValue: 'Default' })}</SelectItem>
                                                  <SelectItem value="none">none</SelectItem>
                                                  <SelectItem value="half">half</SelectItem>
                                                  <SelectItem value="full">full</SelectItem>
                                                </SelectContent>
                                              </Select>
                                              <FormMessage />
                                            </FormItem>
                                          )}
                                        />

                                        <FormField
                                          control={form.control}
                                          name={securityFieldName('echServerKeys')}
                                          render={({ field }) => (
                                            <FormItem className="w-full min-w-0 sm:col-span-2">
                                              <FormLabel className="text-muted-foreground text-xs font-medium">{t('coreEditor.inbound.ech.echKey', { defaultValue: 'ECH key' })}</FormLabel>
                                              <FormControl>
                                                <Textarea
                                                  dir="ltr"
                                                  rows={3}
                                                  className="min-h-[72px] w-full min-w-0 resize-y text-xs"
                                                  placeholder="ECH server keys (PEM or base64 per Xray TLS ECH docs)"
                                                  defaultValue={field.value ?? ''}
                                                  onBlur={e => {
                                                    const next = e.target.value
                                                    field.onChange(next)
                                                    applyTlsEchPatch({ echServerKeys: next })
                                                  }}
                                                />
                                              </FormControl>
                                              <FormMessage />
                                            </FormItem>
                                          )}
                                        />

                                        <FormField
                                          control={form.control}
                                          name={securityFieldName('echConfigList')}
                                          render={({ field }) => (
                                            <FormItem className="w-full min-w-0 sm:col-span-2">
                                              <FormLabel className="text-muted-foreground text-xs font-medium">{t('coreEditor.inbound.ech.echConfig', { defaultValue: 'ECH config' })}</FormLabel>
                                              <FormControl>
                                                <Textarea
                                                  dir="ltr"
                                                  rows={3}
                                                  className="min-h-[72px] w-full min-w-0 resize-y text-xs"
                                                  placeholder="ECH ECHConfigList (base64 per Xray docs)"
                                                  defaultValue={field.value ?? ''}
                                                  onBlur={e => {
                                                    const next = e.target.value
                                                    field.onChange(next)
                                                    applyTlsEchPatch({ echConfigList: next })
                                                  }}
                                                />
                                              </FormControl>
                                              <FormMessage />
                                            </FormItem>
                                          )}
                                        />
                                      </div>
                                      <LoaderButton
                                        type="button"
                                        onClick={handleGenerateEchCertificate}
                                        className="h-10 w-full text-sm font-medium transition-all hover:shadow-md sm:h-11"
                                        isLoading={false}
                                      >
                                        <span className="flex items-center gap-2 truncate">{t('coreEditor.inbound.ech.generateCert', { defaultValue: 'Generate ECH certificate' })}</span>
                                      </LoaderButton>
                                    </AccordionContent>
                                  </AccordionItem>
                                </Accordion>
                              )}
                              {isReality && jsonKey === 'serverNames' && (
                                <div className="sm:col-span-2">
                                  <LoaderButton
                                    type="button"
                                    onClick={() => void generateRealityKeys()}
                                    className="h-10 w-full text-sm font-medium transition-all hover:shadow-md sm:h-11"
                                    isLoading={isGeneratingRealityKeyPair}
                                    loadingText={t('coreConfigModal.generatingKeyPair')}
                                  >
                                    <span className="flex items-center gap-2 truncate">{t('coreConfigModal.generateKeyPair')}</span>
                                  </LoaderButton>
                                </div>
                              )}
                              {isReality && jsonKey === 'publicKey' && (
                                <div className="sm:col-span-2">
                                  <LoaderButton
                                    type="button"
                                    onClick={() => void generateShortId()}
                                    className="h-10 w-full text-sm font-medium transition-all hover:shadow-md sm:h-11"
                                    isLoading={isGeneratingRealityShortId}
                                    loadingText={t('coreConfigModal.generatingShortId')}
                                  >
                                    <span className="flex items-center gap-2 truncate">{t('coreConfigModal.generateShortId')}</span>
                                  </LoaderButton>
                                </div>
                              )}
                              {isReality && jsonKey === 'fingerprint' && (
                                <div className="sm:col-span-2">
                                  <LoaderButton
                                    type="button"
                                    onClick={() => void handleGenerateMldsa65()}
                                    className="h-10 w-full text-sm font-medium transition-all hover:shadow-md sm:h-11"
                                    isLoading={isGeneratingMldsa65}
                                    loadingText={t('coreConfigModal.generatingMldsa65')}
                                  >
                                    <span className="flex items-center gap-2 truncate">{t('coreConfigModal.generateMldsa65')}</span>
                                  </LoaderButton>
                                </div>
                              )}
                            </Fragment>
                          )
                        })}
                      </div>
                    </div>
                  </>
                )}
                {showTlsFallbacksEditor && inbound ? (
                  <div className="sm:col-span-2">
                    <InboundTlsFallbacksEditor fallbacks={inboundTlsFallbacks} onPersist={fb => patchInbound({ fallbacks: fb } as Partial<Inbound>)} />
                  </div>
                ) : null}
                {inboundSecurityType === 'tls' && inboundTlsBooleanGridFieldOrder.length > 0 ? (
                  <div className="sm:col-span-2">
                    <div className="grid gap-3 sm:grid-cols-2">
                      {inboundTlsBooleanGridFieldOrder.map(jsonKey => {
                        const def = caps.securityFieldDefinitions.tls?.[jsonKey]
                        if (!def) return null
                        const name = securityFieldName(jsonKey)
                        return (
                          <FormField
                            key={jsonKey}
                            control={form.control}
                            name={name}
                            render={({ field }) => (
                              <FormItem className="w-full min-w-0">
                                <XrayParityFormControl
                                  field={def}
                                  value={field.value ?? ''}
                                  renderBooleanAsToggleRow
                                  onChange={v => {
                                    field.onChange(v)
                                    try {
                                      patchSecurity({ [jsonKey]: parseOutboundSettingValue(def, v) })
                                    } catch {
                                      /* invalid JSON fragment — wait for valid input */
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
                  </div>
                ) : null}
                {renderInboundSockopt()}
                {inbound.protocol !== 'hysteria' ? renderSniffingAccordion() : null}
              </div>
            </form>
          </Form>
        )}

        {inbound && inbound.protocol !== 'unmanaged' && !('transport' in inbound) && isTunnelInboundProtocol(inbound.protocol) && (
          <Form {...form}>
            <form className="space-y-4" onSubmit={e => e.preventDefault()}>
              <div className="grid gap-3 sm:grid-cols-2">
                <FormField
                  control={form.control}
                  name="tag"
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
                            form.clearErrors('tag')
                            patchInbound({ tag: v })
                          }}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name="protocol"
                  render={({ field, fieldState }) => (
                    <FormItem>
                      <FormLabel>{t('coreEditor.field.protocol', { defaultValue: 'Protocol' })}</FormLabel>
                      <Select
                        dir="ltr"
                        value={field.value}
                        onValueChange={v => {
                          const protocol = v as Parameters<typeof createDefaultInboundForProtocol>[0]['protocol']
                          field.onChange(protocol)
                          const next = applyInboundEditorCreationDefaults(
                            createDefaultInboundForProtocol({
                              protocol,
                              ...kitArgsPreservingListenPort(inbound),
                              clientDefaults: 'empty',
                            }),
                          )
                          replaceEffectiveInbound(next)
                          form.setValue('protocol', next.protocol)
                          form.setValue('tag', next.tag ?? '')
                          form.setValue('listen', 'listen' in next ? listenAddressForForm(next.listen) : '')
                          form.setValue('port', 'port' in next && next.port !== undefined ? String(next.port) : '')
                          syncVlessFieldsFromInboundForm(form, next)
                          form.setValue('shadowsocksMethod', shadowsocksMethodFormValue(next))
                          form.setValue('shadowsocksPassword', shadowsocksPasswordFormValue(next))
                          form.setValue('shadowsocksNetwork', shadowsocksNetworkFormValue(next))
                          setShadowsocksPasswordJustGenerated(false)
                          setVlessDecryptionJustGenerated(false)
                          form.setValue('transport', 'transport' in next && next.transport ? next.transport.type : 'tcp')
                          form.setValue('security', 'security' in next && next.security ? next.security.type : 'none')
                          syncSecurityFormFields(next)
                          syncTransportFormFields(next)
                          syncTunnelFormFieldsFromInbound(next)
                          syncTunFormFieldsFromInbound(next)
                          syncWireguardFormFieldsFromInbound(next)
                        }}
                      >
                        <FormControl className={cn(!!fieldState.error && 'border-destructive')}>
                          <SelectTrigger className="h-10 py-2" dir="ltr">
                            <SelectValue />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent dir="ltr">
                          {protocolSelectOptions.map(p => (
                            <SelectItem key={p} value={p}>
                              {formatInboundProtocolForUi(p, t)}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name="listen"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>{t('coreEditor.field.listen', { defaultValue: 'Listen' })}</FormLabel>
                      <FormControl>
                        <Input
                          {...field}
                          className="h-10"
                          dir="ltr"
                          placeholder="0.0.0.0"
                          onChange={e => {
                            const v = e.target.value
                            field.onChange(v)
                            if (!shouldPersistInboundListen(v)) patchInbound({ listen: undefined } as Partial<Inbound>)
                            else patchInbound({ listen: v.trim() })
                          }}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name="port"
                  render={({ field, fieldState }) => (
                    <FormItem>
                      <FormLabel>{t('coreEditor.field.port', { defaultValue: 'Port' })}</FormLabel>
                      <FormControl>
                        <Input
                          {...field}
                          className="h-10"
                          dir="ltr"
                          isError={!!fieldState.error}
                          placeholder="443 or 1000-2000,444"
                          onChange={e => {
                            const v = e.target.value
                            field.onChange(v)
                            if (v.trim() === '') patchInbound({ port: undefined } as Partial<Inbound>)
                            else {
                              const n = Number(v)
                              patchInbound({ port: Number.isFinite(n) ? n : v } as Partial<Inbound>)
                            }
                          }}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <div className="grid gap-3 sm:col-span-2 sm:grid-cols-2 sm:gap-4">
                  <FormField
                    control={form.control}
                    name="tunnelRewriteAddress"
                    render={({ field }) => (
                      <FormItem className="min-w-0">
                        <FormLabel>{t('coreEditor.inbound.tunnel.targetAddress', { defaultValue: 'Target address' })}</FormLabel>
                        <FormControl>
                          <Input
                            {...field}
                            autoComplete="off"
                            dir="ltr"
                            className="h-10"
                            placeholder="8.8.8.8"
                            onChange={e => {
                              const v = e.target.value
                              field.onChange(v)
                              patchTunnelInboundFields({ rewriteAddress: v })
                            }}
                          />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                  <FormField
                    control={form.control}
                    name="tunnelRewritePort"
                    render={({ field }) => (
                      <FormItem className="min-w-0">
                        <FormLabel>{t('coreEditor.inbound.tunnel.destinationPort', { defaultValue: 'Destination port' })}</FormLabel>
                        <FormControl>
                          <Input
                            {...field}
                            autoComplete="off"
                            dir="ltr"
                            className="h-10"
                            placeholder="53"
                            onChange={e => {
                              const v = e.target.value
                              field.onChange(v)
                              patchTunnelInboundFields({ rewritePort: v })
                            }}
                          />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </div>

                <div className="space-y-3 sm:col-span-2">
                  <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between sm:gap-3">
                    <div className="min-w-0 space-y-1">
                      <FormLabel>{t('coreEditor.inbound.tunnel.portMapping', { defaultValue: 'Port mapping' })}</FormLabel>
                      <p className="text-muted-foreground text-xs leading-relaxed">{t('coreEditor.inbound.tunnel.mapHint', { defaultValue: 'Optional: host:port, :port, or host:.' })}</p>
                    </div>
                    <Button
                      type="button"
                      variant="outline"
                      size="icon"
                      className="size-9 shrink-0 self-start"
                      title={t('coreEditor.inbound.tunnel.addMapping', { defaultValue: 'Add mapping' })}
                      aria-label={t('coreEditor.inbound.tunnel.addMapping', { defaultValue: 'Add mapping' })}
                      onClick={() => setTunnelBlankPortMapRows(prev => [...prev, { listenPort: '', target: '' }])}
                    >
                      <Plus className="size-4" aria-hidden />
                    </Button>
                  </div>

                  {tunnelCommittedPortMapRows.length > 0 || tunnelBlankPortMapRows.length > 0 ? (
                    <div className="rounded-md border">
                      <div className={cn('text-muted-foreground hidden border-b px-3 py-2 text-xs font-medium', TUNNEL_PORT_MAP_ROW_GRID)}>
                        <span className="text-center tabular-nums">{t('coreEditor.inbound.tunnel.mapColIndex', { defaultValue: '#' })}</span>
                        <span>{t('coreEditor.inbound.tunnel.mapColLocalPort', { defaultValue: 'Local port' })}</span>
                        <span className="min-w-0">{t('coreEditor.inbound.tunnel.mapColRemote', { defaultValue: 'Remote target' })}</span>
                        <span className="sr-only">{t('coreEditor.inbound.tunnel.removeMappingShort', { defaultValue: 'Remove' })}</span>
                      </div>

                      <ul className="divide-y">
                        {tunnelCommittedPortMapRows.map((row, i) => {
                          const committed = tunnelCommittedPortMapRows
                          return (
                            <li key={`tunnel-map-c-${inbound.tag}-${i}-${row.listenPort}`} className="p-3 sm:p-2.5">
                              <div className={cn('grid gap-3', TUNNEL_PORT_MAP_ROW_GRID)}>
                                <span className="text-muted-foreground w-6 shrink-0 pt-2 text-center text-xs tabular-nums">
                                  <span className="sm:hidden">{t('coreEditor.inbound.tunnel.mapRowLabel', { defaultValue: 'Mapping' })} </span>
                                  {i + 1}
                                </span>
                                <div className="min-w-0 space-y-1">
                                  <span className="text-muted-foreground text-xs sm:hidden">{t('coreEditor.inbound.tunnel.mapColLocalPort', { defaultValue: 'Local port' })}</span>
                                  <Input
                                    dir="ltr"
                                    className="h-9 text-xs"
                                    inputMode="numeric"
                                    placeholder={t('coreEditor.inbound.tunnel.mapPortPlaceholder', { defaultValue: 'e.g. 5555' })}
                                    value={row.listenPort}
                                    aria-label={t('coreEditor.inbound.tunnel.mapColLocalPort', { defaultValue: 'Local port' })}
                                    onChange={e => {
                                      const v = e.target.value
                                      const next = [...committed]
                                      next[i] = { ...next[i], listenPort: v }
                                      persistTunnelPortMapRows(next)
                                    }}
                                  />
                                </div>
                                <div className="min-w-0 space-y-1">
                                  <span className="text-muted-foreground text-xs sm:hidden">{t('coreEditor.inbound.tunnel.mapColRemote', { defaultValue: 'Remote target' })}</span>
                                  <Input
                                    dir="ltr"
                                    className="h-9 text-xs"
                                    placeholder={t('coreEditor.inbound.tunnel.mapTargetPlaceholder', { defaultValue: 'e.g. 1.1.1.1:443' })}
                                    value={row.target}
                                    aria-label={t('coreEditor.inbound.tunnel.mapColRemote', { defaultValue: 'Remote target' })}
                                    onChange={e => {
                                      const v = e.target.value
                                      const next = [...committed]
                                      next[i] = { ...next[i], target: v }
                                      persistTunnelPortMapRows(next)
                                    }}
                                  />
                                </div>
                                <div className="flex justify-end pt-1 sm:justify-start sm:pt-0">
                                  <Button
                                    type="button"
                                    variant="ghost"
                                    size="icon"
                                    className="size-9 shrink-0"
                                    title={t('coreEditor.inbound.tunnel.removeMapping', { defaultValue: 'Remove row' })}
                                    aria-label={t('coreEditor.inbound.tunnel.removeMapping', { defaultValue: 'Remove row' })}
                                    onClick={() => persistTunnelPortMapRows(committed.filter((_, idx) => idx !== i))}
                                  >
                                    <Trash2 className="size-4" />
                                  </Button>
                                </div>
                              </div>
                            </li>
                          )
                        })}
                        {tunnelBlankPortMapRows.map((row, j) => {
                          const rowNum = tunnelCommittedPortMapRows.length + j + 1
                          return (
                            <li key={`tunnel-map-b-${j}`} className="p-3 sm:p-2.5">
                              <div className={cn('grid gap-3', TUNNEL_PORT_MAP_ROW_GRID)}>
                                <span className="text-muted-foreground w-6 shrink-0 pt-2 text-center text-xs tabular-nums">
                                  <span className="sm:hidden">{t('coreEditor.inbound.tunnel.mapRowLabel', { defaultValue: 'Mapping' })} </span>
                                  {rowNum}
                                </span>
                                <div className="min-w-0 space-y-1">
                                  <span className="text-muted-foreground text-xs sm:hidden">{t('coreEditor.inbound.tunnel.mapColLocalPort', { defaultValue: 'Local port' })}</span>
                                  <Input
                                    dir="ltr"
                                    className="h-9 text-xs"
                                    inputMode="numeric"
                                    placeholder={t('coreEditor.inbound.tunnel.mapPortPlaceholder', { defaultValue: 'e.g. 5555' })}
                                    value={row.listenPort}
                                    aria-label={t('coreEditor.inbound.tunnel.mapColLocalPort', { defaultValue: 'Local port' })}
                                    onChange={e => {
                                      const v = e.target.value
                                      setTunnelBlankPortMapRows(prev => prev.map((r, k) => (k === j ? { ...r, listenPort: v } : r)))
                                    }}
                                  />
                                </div>
                                <div className="min-w-0 space-y-1">
                                  <span className="text-muted-foreground text-xs sm:hidden">{t('coreEditor.inbound.tunnel.mapColRemote', { defaultValue: 'Remote target' })}</span>
                                  <Input
                                    dir="ltr"
                                    className="h-9 text-xs"
                                    placeholder={t('coreEditor.inbound.tunnel.mapTargetPlaceholder', { defaultValue: 'e.g. 1.1.1.1:443' })}
                                    value={row.target}
                                    aria-label={t('coreEditor.inbound.tunnel.mapColRemote', { defaultValue: 'Remote target' })}
                                    onChange={e => {
                                      const v = e.target.value
                                      setTunnelBlankPortMapRows(prev => prev.map((r, k) => (k === j ? { ...r, target: v } : r)))
                                    }}
                                    onBlur={() => commitTunnelBlankPortMapSlot(j)}
                                  />
                                </div>
                                <div className="flex justify-end pt-1 sm:justify-start sm:pt-0">
                                  <Button
                                    type="button"
                                    variant="ghost"
                                    size="icon"
                                    className="size-9 shrink-0"
                                    title={t('coreEditor.inbound.tunnel.discardDraftRow', { defaultValue: 'Clear row' })}
                                    aria-label={t('coreEditor.inbound.tunnel.discardDraftRow', { defaultValue: 'Clear row' })}
                                    onClick={() => setTunnelBlankPortMapRows(prev => (prev.length <= 1 ? [] : prev.filter((_, k) => k !== j)))}
                                  >
                                    <Trash2 className="size-4" />
                                  </Button>
                                </div>
                              </div>
                            </li>
                          )
                        })}
                      </ul>
                    </div>
                  ) : null}
                </div>

                <FormField
                  control={form.control}
                  name="tunnelAllowedNetwork"
                  render={({ field }) => (
                    <FormItem className="min-w-0 sm:col-span-2">
                      <FormLabel>{t('coreEditor.inbound.tunnel.network', { defaultValue: 'Network' })}</FormLabel>
                      <Select
                        value={field.value}
                        onValueChange={v => {
                          field.onChange(v)
                          patchTunnelInboundFields({ allowedNetwork: v })
                        }}
                      >
                        <FormControl>
                          <SelectTrigger className="h-10 w-full min-w-0">
                            <SelectValue />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          <SelectItem value="tcp">TCP</SelectItem>
                          <SelectItem value="udp">UDP</SelectItem>
                          <SelectItem value="tcp,udp">TCP,UDP</SelectItem>
                        </SelectContent>
                      </Select>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="tunnelFollowRedirect"
                  render={({ field }) => (
                    <FormItem className="border-border bg-background/60 flex flex-row items-center justify-between gap-3 space-y-0 rounded-md border px-3 py-2.5 shadow-sm sm:col-span-2">
                      <FormLabel className="cursor-pointer text-sm font-medium">{t('coreEditor.inbound.tunnel.followRedirect', { defaultValue: 'Follow redirect' })}</FormLabel>
                      <FormControl>
                        <Switch
                          checked={field.value === 'true'}
                          onCheckedChange={(checked: boolean) => {
                            const v = checked ? 'true' : 'false'
                            field.onChange(v)
                            patchTunnelInboundFields({ followRedirect: checked })
                          }}
                        />
                      </FormControl>
                    </FormItem>
                  )}
                />

                {renderInboundSockopt()}
                {renderSniffingAccordion()}
              </div>
            </form>
          </Form>
        )}

        {inbound && inbound.protocol !== 'unmanaged' && !('transport' in inbound) && !isTunnelInboundProtocol(inbound.protocol) && (
          <Form {...form}>
            <form className="space-y-4" onSubmit={e => e.preventDefault()}>
              <div className="grid gap-3 sm:grid-cols-2">
                <FormField
                  control={form.control}
                  name="tag"
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
                            form.clearErrors('tag')
                            patchInbound({ tag: v })
                          }}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name="protocol"
                  render={({ field, fieldState }) => (
                    <FormItem>
                      <FormLabel>{t('coreEditor.field.protocol', { defaultValue: 'Protocol' })}</FormLabel>
                      <Select
                        dir="ltr"
                        value={field.value}
                        onValueChange={v => {
                          const protocol = v as Parameters<typeof createDefaultInboundForProtocol>[0]['protocol']
                          field.onChange(protocol)
                          const next = applyInboundEditorCreationDefaults(
                            createDefaultInboundForProtocol({
                              protocol,
                              ...kitArgsPreservingListenPort(inbound),
                              clientDefaults: 'empty',
                            }),
                          )
                          replaceEffectiveInbound(next)
                          form.setValue('protocol', next.protocol)
                          form.setValue('tag', next.tag ?? '')
                          form.setValue('listen', 'listen' in next ? listenAddressForForm(next.listen) : '')
                          form.setValue('port', 'port' in next && next.port !== undefined ? String(next.port) : '')
                          syncVlessFieldsFromInboundForm(form, next)
                          form.setValue('shadowsocksMethod', shadowsocksMethodFormValue(next))
                          form.setValue('shadowsocksPassword', shadowsocksPasswordFormValue(next))
                          form.setValue('shadowsocksNetwork', shadowsocksNetworkFormValue(next))
                          setShadowsocksPasswordJustGenerated(false)
                          setVlessDecryptionJustGenerated(false)
                          form.setValue('transport', 'transport' in next && next.transport ? next.transport.type : 'tcp')
                          form.setValue('security', 'security' in next && next.security ? next.security.type : 'none')
                          syncSecurityFormFields(next)
                          syncTransportFormFields(next)
                          syncTunnelFormFieldsFromInbound(next)
                          syncTunFormFieldsFromInbound(next)
                          syncWireguardFormFieldsFromInbound(next)
                        }}
                      >
                        <FormControl className={cn(!!fieldState.error && 'border-destructive')}>
                          <SelectTrigger className="h-10 py-2" dir="ltr">
                            <SelectValue />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent dir="ltr">
                          {protocolSelectOptions.map(p => (
                            <SelectItem key={p} value={p}>
                              {formatInboundProtocolForUi(p, t)}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name="listen"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>{t('coreEditor.field.listen', { defaultValue: 'Listen' })}</FormLabel>
                      <FormControl>
                        <Input
                          {...field}
                          className="h-10"
                          dir="ltr"
                          placeholder="0.0.0.0"
                          onChange={e => {
                            const v = e.target.value
                            field.onChange(v)
                            if (!shouldPersistInboundListen(v)) patchInbound({ listen: undefined } as Partial<Inbound>)
                            else patchInbound({ listen: v.trim() })
                          }}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                {inbound.protocol !== 'tun' && (
                  <FormField
                    control={form.control}
                    name="port"
                    render={({ field, fieldState }) => (
                      <FormItem>
                        <FormLabel>{t('coreEditor.field.port', { defaultValue: 'Port' })}</FormLabel>
                        <FormControl>
                          <Input
                            {...field}
                            className="h-10"
                            dir="ltr"
                            isError={!!fieldState.error}
                            placeholder="443 or 1000-2000,444"
                            onChange={e => {
                              const v = e.target.value
                              field.onChange(v)
                              if (v.trim() === '') patchInbound({ port: undefined } as Partial<Inbound>)
                              else {
                                const n = Number(v)
                                patchInbound({ port: Number.isFinite(n) ? n : v } as Partial<Inbound>)
                              }
                            }}
                          />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                )}

                {inbound.protocol === 'tun' && (
                  <div className="grid gap-3 rounded-md border p-3 sm:col-span-2">
                    <FormField
                      control={form.control}
                      name="tunName"
                      render={({ field, fieldState }) => (
                        <FormItem>
                          <FormLabel className="text-sm">{t('coreEditor.inbound.tun.name', { defaultValue: 'Interface Name' })}</FormLabel>
                          <FormControl>
                            <Input
                              {...field}
                              dir="ltr"
                              className="h-10"
                              isError={!!fieldState.error}
                              onChange={e => {
                                const v = e.target.value
                                field.onChange(v)
                                patchInbound({ name: v.trim() === '' ? undefined : v } as Partial<Inbound>)
                              }}
                            />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />

                    <FormField
                      control={form.control}
                      name="tunMtu"
                      render={({ field, fieldState }) => (
                        <FormItem>
                          <FormLabel className="text-sm">{t('coreEditor.inbound.tun.mtu', { defaultValue: 'MTU' })}</FormLabel>
                          <FormControl>
                            <Input
                              {...field}
                              dir="ltr"
                              inputMode="numeric"
                              className="h-10"
                              isError={!!fieldState.error}
                              onChange={e => {
                                const raw = e.target.value
                                field.onChange(raw)
                                const v = raw.trim()
                                if (v === '') {
                                  patchInbound({ mtu: undefined } as Partial<Inbound>)
                                  return
                                }
                                const n = Number(v)
                                patchInbound({ mtu: Number.isFinite(n) ? Math.trunc(n) : undefined } as Partial<Inbound>)
                              }}
                            />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />

                    <div className="grid gap-2">
                      <FormLabel className="text-sm">{t('coreEditor.inbound.tun.gateway', { defaultValue: 'Gateway' })}</FormLabel>
                      <StringArrayPopoverInput
                        value={stringListFromUnknown((inbound as { gateway?: unknown }).gateway)}
                        onChange={next => {
                          patchInbound({ gateway: next.length > 0 ? next : undefined } as Partial<Inbound>)
                        }}
                        placeholder={t('coreEditor.inbound.tun.gatewayHint', { defaultValue: 'One CIDR per line, e.g. 10.0.0.1/16' })}
                        addPlaceholder={t('coreEditor.inbound.tun.gatewayAddPlaceholder', {
                          defaultValue: 'Add gateway CIDR',
                        })}
                        addButtonLabel={t('coreEditor.inbound.tun.addItem', { defaultValue: 'Add' })}
                        itemsLabel={t('coreEditor.inbound.tun.gatewayItems', { defaultValue: 'Gateway CIDRs' })}
                        emptyMessage={t('coreEditor.inbound.tun.noGatewayItems', { defaultValue: 'No gateway CIDR added.' })}
                        className="h-10"
                      />
                    </div>

                    <div className="grid gap-2">
                      <FormLabel className="text-sm">{t('coreEditor.inbound.tun.dns', { defaultValue: 'DNS' })}</FormLabel>
                      <StringArrayPopoverInput
                        value={stringListFromUnknown((inbound as { dns?: unknown }).dns)}
                        onChange={next => {
                          patchInbound({ dns: next.length > 0 ? next : undefined } as Partial<Inbound>)
                        }}
                        placeholder={t('coreEditor.inbound.tun.dnsHint', { defaultValue: 'One DNS server per line, e.g. 1.1.1.1' })}
                        addPlaceholder={t('coreEditor.inbound.tun.dnsAddPlaceholder', {
                          defaultValue: 'Add DNS server',
                        })}
                        addButtonLabel={t('coreEditor.inbound.tun.addItem', { defaultValue: 'Add' })}
                        itemsLabel={t('coreEditor.inbound.tun.dnsItems', { defaultValue: 'DNS servers' })}
                        emptyMessage={t('coreEditor.inbound.tun.noDnsItems', { defaultValue: 'No DNS server added.' })}
                        className="h-10"
                      />
                    </div>

                    <div className="grid gap-2">
                      <FormLabel className="text-sm">
                        {t('coreEditor.inbound.tun.autoSystemRoutingTable', {
                          defaultValue: 'Auto System Routing Table',
                        })}
                      </FormLabel>
                      <StringArrayPopoverInput
                        value={stringListFromUnknown((inbound as { autoSystemRoutingTable?: unknown }).autoSystemRoutingTable)}
                        onChange={next => {
                          patchInbound({ autoSystemRoutingTable: next.length > 0 ? next : undefined } as Partial<Inbound>)
                        }}
                        placeholder={t('coreEditor.inbound.tun.autoSystemRoutingTableHint', {
                          defaultValue: 'One CIDR per line, e.g. 0.0.0.0/0',
                        })}
                        addPlaceholder={t('coreEditor.inbound.tun.autoRouteAddPlaceholder', {
                          defaultValue: 'Add route CIDR',
                        })}
                        addButtonLabel={t('coreEditor.inbound.tun.addItem', { defaultValue: 'Add' })}
                        itemsLabel={t('coreEditor.inbound.tun.autoRouteItems', { defaultValue: 'Route CIDRs' })}
                        emptyMessage={t('coreEditor.inbound.tun.noAutoRouteItems', { defaultValue: 'No route CIDR added.' })}
                        className="h-10"
                      />
                    </div>

                    <div className="grid gap-2 sm:grid-cols-[128px_minmax(0,1fr)] sm:items-center">
                      <FormLabel className="text-sm">{t('coreEditor.inbound.tun.autoOutboundsInterface', { defaultValue: 'Auto Outbounds Interface' })}</FormLabel>
                      <Input
                        dir="ltr"
                        className="h-10"
                        placeholder="auto"
                        value={
                          typeof (inbound as { autoOutboundsInterface?: unknown }).autoOutboundsInterface === 'string'
                            ? String((inbound as { autoOutboundsInterface?: unknown }).autoOutboundsInterface)
                            : ''
                        }
                        onChange={e => {
                          const v = e.target.value
                          patchInbound({ autoOutboundsInterface: v.trim() === '' ? undefined : v } as Partial<Inbound>)
                        }}
                      />
                    </div>
                  </div>
                )}

                {inbound.protocol === 'wireguard' && (
                  <div className="grid w-full min-w-0 gap-3 rounded-md border p-3 sm:col-span-2">
                    <FormField
                      control={form.control}
                      name="wgSecretKey"
                      render={({ field, fieldState }) => (
                        <FormItem className="w-full min-w-0">
                          <FormLabel className="text-sm">{t('coreEditor.inbound.wireguard.secretKey', { defaultValue: 'Secret Key' })}</FormLabel>
                          <FormControl className="w-full">
                            <PasswordInput
                              {...field}
                              dir="ltr"
                              className="h-10 w-full text-xs"
                              autoComplete="new-password"
                              isError={!!fieldState.error}
                              onChange={e => {
                                const v = e.target.value
                                field.onChange(v)
                                patchInbound({ secretKey: v.trim() === '' ? undefined : v } as Partial<Inbound>)
                              }}
                            />
                          </FormControl>
                          <div className="mt-2">
                            <LoaderButton
                              type="button"
                              onClick={() => {
                                const keyPair = generateWireGuardKeyPair()
                                form.setValue('wgSecretKey', keyPair.privateKey)
                                patchInbound({ secretKey: keyPair.privateKey } as Partial<Inbound>)
                                toast.success(
                                  t('coreConfigModal.wireguardKeyPairGenerated', {
                                    defaultValue: 'WireGuard keypair generated',
                                  }),
                                )
                              }}
                              className="h-10 w-full text-sm font-medium transition-all hover:shadow-md sm:h-11"
                              isLoading={false}
                            >
                              <span className="flex items-center gap-2 truncate">{t('coreEditor.inbound.wireguard.generateSecretKey', { defaultValue: 'Generate secret key' })}</span>
                            </LoaderButton>
                          </div>
                          <FormMessage />
                        </FormItem>
                      )}
                    />

                    <FormField
                      control={form.control}
                      name="wgMtu"
                      render={({ field, fieldState }) => (
                        <FormItem className="w-full min-w-0">
                          <FormLabel className="text-sm">{t('coreEditor.inbound.wireguard.mtu', { defaultValue: 'MTU' })}</FormLabel>
                          <FormControl className="w-full">
                            <Input
                              {...field}
                              dir="ltr"
                              inputMode="numeric"
                              className="h-10 w-full min-w-0"
                              isError={!!fieldState.error}
                              onChange={e => {
                                const raw = e.target.value
                                field.onChange(raw)
                                const v = raw.trim()
                                if (v === '') {
                                  patchInbound({ mtu: undefined } as Partial<Inbound>)
                                  return
                                }
                                const n = Number(v)
                                patchInbound({ mtu: Number.isFinite(n) ? Math.trunc(n) : undefined } as Partial<Inbound>)
                              }}
                            />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />

                    <div className="space-y-2">
                      <div className="flex items-center justify-between gap-2">
                        <FormLabel className="text-sm font-medium">{t('coreEditor.inbound.wireguard.peers', { defaultValue: 'Peers' })}</FormLabel>
                        <Button
                          type="button"
                          variant="outline"
                          size="icon"
                          className="size-9"
                          title={t('coreEditor.inbound.wireguard.addPeer', { defaultValue: 'Add peer' })}
                          aria-label={t('coreEditor.inbound.wireguard.addPeer', { defaultValue: 'Add peer' })}
                          onClick={() => {
                            if (!isWireguardInboundProtocol(inbound.protocol)) return
                            const peers = wireguardPeersForUi(inbound)
                            const keyPair = generateWireGuardKeyPair()
                            const nextIndex = peers.length
                            setWireguardPeerPrivateKeys(prev => ({ ...prev, [nextIndex]: keyPair.privateKey }))
                            patchInbound({
                              peers: [
                                ...peers,
                                {
                                  publicKey: keyPair.publicKey,
                                  preSharedKey: undefined,
                                  allowedIPs: wireguardDefaultAllowedIpsForNewPeer(nextIndex),
                                },
                              ],
                            } as Partial<Inbound>)
                          }}
                        >
                          <Plus className="size-4" aria-hidden />
                        </Button>
                      </div>

                      <div className="rounded-md border">
                        {wireguardPeersForUi(inbound).length === 0 ? (
                          <div className="text-muted-foreground px-3 py-2 text-xs">{t('coreEditor.inbound.wireguard.noPeers', { defaultValue: 'No peers added.' })}</div>
                        ) : (
                          <div className="divide-y">
                            {wireguardPeersForUi(inbound).map((peer, index) => (
                              <div key={`wg-peer-${index}`} className="w-full min-w-0 space-y-3 p-3">
                                <div className="flex items-center justify-between">
                                  <span className="text-muted-foreground text-xs font-medium">
                                    {t('coreEditor.inbound.wireguard.peerLabel', { defaultValue: 'Peer' })} {index + 1}
                                  </span>
                                  <Button
                                    type="button"
                                    variant="ghost"
                                    size="icon"
                                    className="text-destructive hover:text-destructive size-8"
                                    title={t('coreEditor.inbound.wireguard.removePeer', { defaultValue: 'Remove peer' })}
                                    aria-label={t('coreEditor.inbound.wireguard.removePeer', { defaultValue: 'Remove peer' })}
                                    onClick={() => {
                                      if (!isWireguardInboundProtocol(inbound.protocol)) return
                                      const nextPeers = wireguardPeersForUi(inbound).filter((_, i) => i !== index)
                                      setWireguardPeerPrivateKeys(prev => {
                                        const next: Record<number, string> = {}
                                        for (const [k, v] of Object.entries(prev)) {
                                          const oldIndex = Number(k)
                                          if (Number.isNaN(oldIndex) || oldIndex === index) continue
                                          next[oldIndex > index ? oldIndex - 1 : oldIndex] = v
                                        }
                                        return next
                                      })
                                      patchInbound({ peers: nextPeers.length > 0 ? nextPeers : undefined } as Partial<Inbound>)
                                    }}
                                  >
                                    <Trash2 className="size-4" aria-hidden />
                                  </Button>
                                </div>

                                <div className="w-full min-w-0 space-y-1.5">
                                  <FormLabel className="text-sm">{t('coreEditor.inbound.wireguard.privateKey', { defaultValue: 'Private Key' })}</FormLabel>
                                  <div dir="ltr" className={`flex w-full min-w-0 items-center gap-2 ${dir === 'rtl' ? 'flex-row-reverse' : 'flex-row'}`}>
                                    <PasswordInput
                                      className="h-10 min-w-0 flex-1 basis-0 text-xs"
                                      autoComplete="new-password"
                                      value={wireguardPeerPrivateKeys[index] ?? ''}
                                      onChange={e => {
                                        if (!isWireguardInboundProtocol(inbound.protocol)) return
                                        const privateKey = e.target.value
                                        setWireguardPeerPrivateKeys(prev => ({ ...prev, [index]: privateKey }))
                                        const nextPeers = wireguardPeersForUi(inbound)
                                        nextPeers[index] = {
                                          ...nextPeers[index],
                                          publicKey: getWireGuardPublicKey(privateKey),
                                        }
                                        patchInbound({ peers: nextPeers } as Partial<Inbound>)
                                      }}
                                    />
                                    <Button
                                      size="icon"
                                      type="button"
                                      variant="ghost"
                                      className="size-10 shrink-0"
                                      onClick={() => {
                                        if (!isWireguardInboundProtocol(inbound.protocol)) return
                                        const keyPair = generateWireGuardKeyPair()
                                        setWireguardPeerPrivateKeys(prev => ({ ...prev, [index]: keyPair.privateKey }))
                                        const nextPeers = wireguardPeersForUi(inbound)
                                        nextPeers[index] = { ...nextPeers[index], publicKey: keyPair.publicKey }
                                        patchInbound({ peers: nextPeers } as Partial<Inbound>)
                                        toast.success(
                                          t('coreEditor.inbound.wireguard.publicKeyGenerated', {
                                            defaultValue: 'Peer public key generated',
                                          }),
                                        )
                                      }}
                                      title={t('coreEditor.inbound.wireguard.generateWireGuardKeyPair', {
                                        defaultValue: 'Generate WireGuard keypair',
                                      })}
                                    >
                                      <RefreshCcw className="h-3 w-3" />
                                    </Button>
                                  </div>
                                </div>

                                <div className="w-full min-w-0 space-y-1.5">
                                  <FormLabel className="text-sm">{t('coreEditor.inbound.wireguard.publicKey', { defaultValue: 'Public Key' })}</FormLabel>
                                  <Input dir="ltr" className="h-10 w-full min-w-0 text-xs" value={peer.publicKey} disabled />
                                </div>

                                <div className="w-full min-w-0 space-y-1.5">
                                  <FormLabel className="text-sm">{t('coreEditor.inbound.wireguard.preSharedKey', { defaultValue: 'PreShared Key' })}</FormLabel>
                                  <div dir="ltr" className={`flex w-full min-w-0 items-center gap-2 ${dir === 'rtl' ? 'flex-row-reverse' : 'flex-row'}`}>
                                    <PasswordInput
                                      className="h-10 min-w-0 flex-1 basis-0 text-xs"
                                      autoComplete="new-password"
                                      value={peer.preSharedKey ?? ''}
                                      onChange={e => {
                                        if (!isWireguardInboundProtocol(inbound.protocol)) return
                                        const nextPeers = wireguardPeersForUi(inbound)
                                        nextPeers[index] = {
                                          ...nextPeers[index],
                                          preSharedKey: e.target.value.trim() === '' ? undefined : e.target.value,
                                        }
                                        patchInbound({ peers: nextPeers } as Partial<Inbound>)
                                      }}
                                    />
                                    <Button
                                      size="icon"
                                      type="button"
                                      variant="ghost"
                                      className="size-10 shrink-0"
                                      onClick={() => {
                                        if (!isWireguardInboundProtocol(inbound.protocol)) return
                                        const keyPair = generateWireGuardKeyPair()
                                        const nextPeers = wireguardPeersForUi(inbound)
                                        nextPeers[index] = { ...nextPeers[index], preSharedKey: keyPair.privateKey }
                                        patchInbound({ peers: nextPeers } as Partial<Inbound>)
                                      }}
                                      title={t('coreEditor.inbound.wireguard.generatePreSharedKey', {
                                        defaultValue: 'Generate pre-shared key',
                                      })}
                                    >
                                      <RefreshCcw className="h-3 w-3" />
                                    </Button>
                                  </div>
                                </div>

                                <div className="w-full min-w-0 space-y-1.5">
                                  <FormLabel className="text-sm">{t('coreEditor.inbound.wireguard.allowedIPs', { defaultValue: 'Allowed IPs' })}</FormLabel>
                                  <StringArrayPopoverInput
                                    value={peer.allowedIPs}
                                    onChange={nextAllowedIps => {
                                      if (!isWireguardInboundProtocol(inbound.protocol)) return
                                      const nextPeers = wireguardPeersForUi(inbound)
                                      nextPeers[index] = { ...nextPeers[index], allowedIPs: nextAllowedIps }
                                      patchInbound({ peers: nextPeers } as Partial<Inbound>)
                                    }}
                                    placeholder={t('coreEditor.inbound.wireguard.allowedIPsHint', {
                                      defaultValue: 'Example: 10.0.0.2/32',
                                    })}
                                    addPlaceholder={t('coreEditor.inbound.wireguard.allowedIPsAddPlaceholder', {
                                      defaultValue: 'Add CIDR',
                                    })}
                                    addButtonLabel={t('coreEditor.inbound.wireguard.addItem', { defaultValue: 'Add' })}
                                    itemsLabel={t('coreEditor.inbound.wireguard.allowedIPsItems', { defaultValue: 'Allowed IPs' })}
                                    emptyMessage={t('coreEditor.inbound.wireguard.noAllowedIPs', {
                                      defaultValue: 'No CIDR added.',
                                    })}
                                    className="h-10 w-full max-w-none min-w-0"
                                  />
                                </div>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                )}

                {isHttpInboundProtocol(inbound.protocol) && (
                  <>
                    <div className="grid gap-3 rounded-md border p-3 sm:col-span-2">
                      <div className="flex items-center justify-between gap-3">
                        <FormLabel className="text-sm font-medium">{t('coreEditor.inbound.http.allowTransparent', { defaultValue: 'Allow Transparent' })}</FormLabel>
                        <Switch
                          checked={(inbound as { allowTransparent?: boolean }).allowTransparent === true}
                          onCheckedChange={checked => {
                            patchInbound({ allowTransparent: checked } as Partial<Inbound>)
                          }}
                        />
                      </div>
                      <div className="flex items-center justify-between gap-3">
                        <FormLabel className="text-sm font-medium">{t('coreEditor.inbound.http.passwordEnabled', { defaultValue: 'Password' })}</FormLabel>
                        <Switch
                          checked={userPassAccountsForUi(inbound).length > 0}
                          onCheckedChange={checked => {
                            if (!isHttpInboundProtocol(inbound.protocol)) return
                            const existingAccounts = userPassAccountsForUi(inbound)
                            patchInbound({
                              accounts: checked ? (existingAccounts.length > 0 ? existingAccounts : [generateMixedAccountCredentials()]) : undefined,
                            } as Partial<Inbound>)
                          }}
                        />
                      </div>
                    </div>

                    {userPassAccountsForUi(inbound).length > 0 && (
                      <div className="space-y-2 sm:col-span-2">
                        <div className="text-muted-foreground grid grid-cols-[minmax(0,1fr)_minmax(0,1fr)_44px] items-center gap-2 text-sm">
                          <span>{t('coreEditor.inbound.http.username', { defaultValue: 'Username' })}</span>
                          <span>{t('coreEditor.inbound.http.password', { defaultValue: 'Password' })}</span>
                          <Button
                            type="button"
                            variant="outline"
                            size="icon"
                            className="size-9 justify-self-end"
                            title={t('coreEditor.inbound.http.addAccount', { defaultValue: 'Add account' })}
                            aria-label={t('coreEditor.inbound.http.addAccount', { defaultValue: 'Add account' })}
                            onClick={() => {
                              if (!isHttpInboundProtocol(inbound.protocol)) return
                              const nextAccounts = [...userPassAccountsForUi(inbound), generateMixedAccountCredentials()]
                              patchInbound({ accounts: nextAccounts } as Partial<Inbound>)
                            }}
                          >
                            <Plus className="size-4" aria-hidden />
                          </Button>
                        </div>

                        <div className="rounded-md border">
                          {userPassAccountsForUi(inbound).length === 0 ? (
                            <div className="text-muted-foreground px-3 py-2 text-xs">{t('coreEditor.inbound.http.noAccounts', { defaultValue: 'No accounts yet.' })}</div>
                          ) : (
                            <div className="divide-y">
                              {userPassAccountsForUi(inbound).map((account, index) => (
                                <div key={`http-account-${index}`} className="grid grid-cols-[minmax(0,1fr)_minmax(0,1fr)_44px] gap-2 p-2">
                                  <Input
                                    dir="ltr"
                                    className="h-9"
                                    value={account.user}
                                    onChange={e => {
                                      if (!isHttpInboundProtocol(inbound.protocol)) return
                                      const nextAccounts = userPassAccountsForUi(inbound)
                                      nextAccounts[index] = { ...nextAccounts[index], user: e.target.value }
                                      patchInbound({ accounts: nextAccounts } as Partial<Inbound>)
                                    }}
                                  />
                                  <PasswordInput
                                    dir="ltr"
                                    className="h-9"
                                    autoComplete="new-password"
                                    value={account.pass}
                                    onChange={e => {
                                      if (!isHttpInboundProtocol(inbound.protocol)) return
                                      const nextAccounts = userPassAccountsForUi(inbound)
                                      nextAccounts[index] = { ...nextAccounts[index], pass: e.target.value }
                                      patchInbound({ accounts: nextAccounts } as Partial<Inbound>)
                                    }}
                                  />
                                  <Button
                                    type="button"
                                    variant="ghost"
                                    size="icon"
                                    className="text-destructive hover:text-destructive size-9"
                                    title={t('coreEditor.inbound.http.removeAccount', { defaultValue: 'Remove account' })}
                                    aria-label={t('coreEditor.inbound.http.removeAccount', { defaultValue: 'Remove account' })}
                                    onClick={() => {
                                      if (!isHttpInboundProtocol(inbound.protocol)) return
                                      const nextAccounts = userPassAccountsForUi(inbound).filter((_, i) => i !== index)
                                      patchInbound({ accounts: nextAccounts.length > 0 ? nextAccounts : undefined } as Partial<Inbound>)
                                    }}
                                  >
                                    <Trash2 className="size-4" aria-hidden />
                                  </Button>
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      </div>
                    )}
                  </>
                )}

                {isMixedLikeInboundProtocol(inbound.protocol) && (
                  <>
                    <div className="grid gap-3 rounded-md border p-3 sm:col-span-2">
                      <div className="flex items-center justify-between gap-3">
                        <FormLabel className="text-sm font-medium">{t('coreEditor.inbound.mixed.udpEnabled', { defaultValue: 'Enabled UDP' })}</FormLabel>
                        <Switch
                          checked={(inbound as { udp?: boolean }).udp === true}
                          onCheckedChange={checked => {
                            patchInbound({ udp: checked } as Partial<Inbound>)
                          }}
                        />
                      </div>
                      {(inbound as { udp?: boolean }).udp === true && (
                        <div className="grid gap-2 sm:grid-cols-[96px_minmax(0,1fr)] sm:items-center">
                          <FormLabel className="text-sm">{t('coreEditor.inbound.mixed.ip', { defaultValue: 'IP' })}</FormLabel>
                          <Input
                            dir="ltr"
                            className="h-10"
                            value={typeof (inbound as Record<string, unknown>).ip === 'string' ? String((inbound as Record<string, unknown>).ip) : ''}
                            onChange={e => {
                              const v = e.target.value
                              patchInbound({ ip: v.trim() === '' ? undefined : v } as Partial<Inbound>)
                            }}
                          />
                        </div>
                      )}
                      <div className="flex items-center justify-between gap-3">
                        <FormLabel className="text-sm font-medium">{t('coreEditor.inbound.mixed.passwordEnabled', { defaultValue: 'Password' })}</FormLabel>
                        <Switch
                          checked={(inbound as { auth?: string }).auth === 'password'}
                          onCheckedChange={checked => {
                            if (!isMixedLikeInboundProtocol(inbound.protocol)) return
                            const existingAccounts = userPassAccountsForUi(inbound)
                            patchInbound({
                              auth: checked ? 'password' : 'noauth',
                              accounts: checked ? (existingAccounts.length > 0 ? existingAccounts : [generateMixedAccountCredentials()]) : undefined,
                            } as Partial<Inbound>)
                          }}
                        />
                      </div>
                    </div>

                    {(inbound as { auth?: string }).auth === 'password' && (
                      <div className="space-y-2 sm:col-span-2">
                        <div className="text-muted-foreground grid grid-cols-[minmax(0,1fr)_minmax(0,1fr)_44px] items-center gap-2 text-sm">
                          <span>{t('coreEditor.inbound.mixed.username', { defaultValue: 'Username' })}</span>
                          <span>{t('coreEditor.inbound.mixed.password', { defaultValue: 'Password' })}</span>
                          <Button
                            type="button"
                            variant="outline"
                            size="icon"
                            className="size-9 justify-self-end"
                            title={t('coreEditor.inbound.mixed.addAccount', { defaultValue: 'Add account' })}
                            aria-label={t('coreEditor.inbound.mixed.addAccount', { defaultValue: 'Add account' })}
                            onClick={() => {
                              if (!isMixedLikeInboundProtocol(inbound.protocol)) return
                              const nextAccounts = [...userPassAccountsForUi(inbound), generateMixedAccountCredentials()]
                              patchInbound({ accounts: nextAccounts } as Partial<Inbound>)
                            }}
                          >
                            <Plus className="size-4" aria-hidden />
                          </Button>
                        </div>

                        <div className="rounded-md border">
                          {userPassAccountsForUi(inbound).length === 0 ? (
                            <div className="text-muted-foreground px-3 py-2 text-xs">{t('coreEditor.inbound.mixed.noAccounts', { defaultValue: 'No accounts yet.' })}</div>
                          ) : (
                            <div className="divide-y">
                              {userPassAccountsForUi(inbound).map((account, index) => (
                                <div key={`mixed-account-${index}`} className="grid grid-cols-[minmax(0,1fr)_minmax(0,1fr)_44px] gap-2 p-2">
                                  <Input
                                    dir="ltr"
                                    className="h-9"
                                    value={account.user}
                                    onChange={e => {
                                      if (!isMixedLikeInboundProtocol(inbound.protocol)) return
                                      const nextAccounts = userPassAccountsForUi(inbound)
                                      nextAccounts[index] = { ...nextAccounts[index], user: e.target.value }
                                      patchInbound({ accounts: nextAccounts } as Partial<Inbound>)
                                    }}
                                  />
                                  <PasswordInput
                                    dir="ltr"
                                    className="h-9"
                                    autoComplete="new-password"
                                    value={account.pass}
                                    onChange={e => {
                                      if (!isMixedLikeInboundProtocol(inbound.protocol)) return
                                      const nextAccounts = userPassAccountsForUi(inbound)
                                      nextAccounts[index] = { ...nextAccounts[index], pass: e.target.value }
                                      patchInbound({ accounts: nextAccounts } as Partial<Inbound>)
                                    }}
                                  />
                                  <Button
                                    type="button"
                                    variant="ghost"
                                    size="icon"
                                    className="text-destructive hover:text-destructive size-9"
                                    title={t('coreEditor.inbound.mixed.removeAccount', { defaultValue: 'Remove account' })}
                                    aria-label={t('coreEditor.inbound.mixed.removeAccount', { defaultValue: 'Remove account' })}
                                    onClick={() => {
                                      if (!isMixedLikeInboundProtocol(inbound.protocol)) return
                                      const nextAccounts = userPassAccountsForUi(inbound).filter((_, i) => i !== index)
                                      patchInbound({ accounts: nextAccounts.length > 0 ? nextAccounts : undefined } as Partial<Inbound>)
                                    }}
                                  >
                                    <Trash2 className="size-4" aria-hidden />
                                  </Button>
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      </div>
                    )}
                  </>
                )}

                {renderInboundSockopt()}
                {renderSniffingAccordion()}
              </div>
            </form>
          </Form>
        )}
      </CoreEditorFormDialog>

      <VlessAdvancedGenerationModal
        open={vlessAdvancedOpen}
        onOpenChange={setVlessAdvancedOpen}
        seedOptions={vlessAdvancedSeed}
        onSuccess={({ result, variant }) => {
          const dec = variant === 'mlkem768' ? result.mlkem768.decryption : result.x25519.decryption
          const enc = variant === 'mlkem768' ? result.mlkem768.encryption : result.x25519.encryption
          const encMethod = result.options.encryptionMethod
          const methodForm = VLESS_ENCRYPTION_METHODS.some(m => m.value === encMethod) ? encMethod : 'none'
          form.setValue('decryption', dec)
          form.setValue('encryption', enc)
          form.setValue('vlessEncryptionMethod', methodForm)
          patchInbound({ decryption: dec, encryption: enc } as Partial<Inbound>)
          setVlessDecryptionJustGenerated(true)
          toast.success(t('coreConfigModal.vlessEncryptionGenerated'))
        }}
      />

      <AlertDialog open={discardDraftOpen} onOpenChange={setDiscardDraftOpen}>
        <AlertDialogContent dir={dir}>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('coreEditor.inbound.discardDraftTitle', { defaultValue: 'Discard new inbound?' })}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('coreEditor.inbound.discardDraftDescription', {
                defaultValue: 'This inbound is not in the list yet. Close without adding it will discard your changes.',
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
              {t('coreEditor.inbound.discardDraftAction', { defaultValue: 'Discard' })}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={discardEditOpen} onOpenChange={setDiscardEditOpen}>
        <AlertDialogContent dir={dir}>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('coreEditor.inbound.discardEditTitle', { defaultValue: 'Discard changes?' })}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('coreEditor.inbound.discardEditDescription', {
                defaultValue: 'Your modifications to this inbound will be lost if you close now.',
              })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('cancel')}</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                if (dialogMode === 'edit' && editOriginalInbound) {
                  updateXrayProfile(p => replaceInbound(p, selected, editOriginalInbound))
                }
                setDiscardEditOpen(false)
                finalizeDetailClose()
              }}
            >
              {t('coreEditor.inbound.discardDraftAction', { defaultValue: 'Discard' })}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={blockAddWhileDraftOpen} onOpenChange={setBlockAddWhileDraftOpen}>
        <AlertDialogContent dir={dir}>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('coreEditor.inbound.finishCurrentTitle', { defaultValue: 'Finish the current inbound first' })}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('coreEditor.inbound.finishCurrentDescription', {
                defaultValue: 'Add it to the list, or close the dialog and discard the draft, before starting another inbound.',
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
