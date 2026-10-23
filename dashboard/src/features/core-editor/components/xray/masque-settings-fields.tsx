import { Button } from '@/components/ui/button'
import {
  FieldMessages,
  OtherFieldMessages,
  ParsedTextField,
  SelectField,
  StreamFormHint,
  StringListField,
  TrimmedTextField,
  type StreamFormT,
} from '@/features/core-editor/components/xray/stream-form-inputs'
import { ignoreValidity, useInvalidFieldsReporter } from '@/features/core-editor/components/xray/stream-form-validity'
import {
  applyMasqueClientAuthMode,
  hasMasqueClientOnlySettings,
  MASQUE_CLIENT_ONLY_FIELDS,
  masqueAlpnForMode,
  masqueClientAuthMode,
  masqueClientShowsBasicAuthFields,
  masqueHttpMode,
  masqueShownFields,
  parseMasqueMtuInput,
  removeMasqueClientOnlySettings,
  type MasqueClientAuthMode,
  type MasqueHttpMode,
} from '@/features/core-editor/kit/masque-fields'
import {
  cleanStringList,
  formatJsonObjectInput,
  formatNumberInput,
  formatTextInput,
  isPlainObject,
  parseJsonObjectInput,
  parsePortInput,
  setRecordKey,
} from '@/features/core-editor/kit/stream-form-fields'
import type { ParsedInput, StreamFieldIssue } from '@/features/core-editor/kit/stream-form-fields'
import { MASQUE_DEFAULTS } from '@pasarguard/xray-config-kit'
import { useState } from 'react'

export interface MasqueSettingsFieldsProps {
  side: 'server' | 'client'
  /** server: { address, mtu, remoteDNS } of the inbound model; client: the outbound `settings` ({ address, port, remoteDNS }) */
  settings: Record<string, unknown>
  onSettingsChange: (next: Record<string, unknown>) => void
  /** the masque transport model (inbound) or `streamSettings.masqueSettings` (outbound) */
  transport: Record<string, unknown>
  onTransportChange: (next: Record<string, unknown>) => void
  alpn: unknown
  /** `null` while the inbound's security is not TLS: there is no ALPN to write, so the HTTP version select is disabled. */
  onAlpnChange: ((alpn: string[]) => void) | null
  issues: readonly StreamFieldIssue[]
  onInvalidInputsChange: (fields: readonly string[]) => void
  t: StreamFormT
}

function storedNumber(value: unknown): number | undefined {
  return typeof value === 'number' ? value : undefined
}

function storedObject(value: unknown): Record<string, unknown> | undefined {
  return isPlainObject(value) ? value : undefined
}

/** An empty JSON object means "not set", so typing `{}` keeps its text while nothing is written. */
function withEmptyObjectUnset(parsed: ParsedInput<Record<string, unknown> | undefined>): ParsedInput<Record<string, unknown> | undefined> {
  if (parsed.ok && parsed.value !== undefined && Object.keys(parsed.value).length === 0) return { ok: true, value: undefined }
  return parsed
}

const parseHeadersInput = (raw: string) => withEmptyObjectUnset(parseJsonObjectInput(raw, { stringValues: true }))
// xmux values are numbers or "min-max" strings, so any JSON object parses (no text-only check as for headers).
const parseXmuxInput = (raw: string) => withEmptyObjectUnset(parseJsonObjectInput(raw))

/** `pass` is written exactly as typed; empty means "not set". */
function parsePasswordInput(raw: string): ParsedInput<string | undefined> {
  return { ok: true, value: raw === '' ? undefined : raw }
}

/** MASQUE settings shared by the inbound (`side="server"`) and outbound (`side="client"`) forms. */
export function MasqueSettingsFields({ side, settings, onSettingsChange, transport, onTransportChange, alpn, onAlpnChange, issues, onInvalidInputsChange, t }: MasqueSettingsFieldsProps) {
  const report = useInvalidFieldsReporter(onInvalidInputsChange)
  const isServer = side === 'server'
  const storedAuthMode = isServer ? 'none' : masqueClientAuthMode(transport)
  // "User and password" with both empty is stored like "None", so Basic stays chosen here once it is picked or stored:
  // clearing the user does not take the inputs away. Picking None or WARP resets it.
  const [basicChosen, setBasicChosen] = useState(storedAuthMode === 'basic')
  if (storedAuthMode === 'basic' && !basicChosen) setBasicChosen(true)
  const authMode: MasqueClientAuthMode = storedAuthMode === 'none' && basicChosen ? 'basic' : storedAuthMode
  const showBasicAuthFields = !isServer && masqueClientShowsBasicAuthFields(transport, authMode)
  const warp = isPlainObject(transport.warp) ? transport.warp : {}
  const showClientOnly = isServer && (hasMasqueClientOnlySettings(transport) || issues.some(issue => (MASQUE_CLIENT_ONLY_FIELDS as readonly string[]).includes(issue.field)))

  const setSettingsKey = (key: string, value: unknown) => onSettingsChange(setRecordKey(settings, key, value))
  const setTransportKey = (key: string, value: unknown) => onTransportChange(setRecordKey(transport, key, value))
  // The WARP object keeps all three keys (as the auth switch seeds them); empty text writes "".
  const setWarpKey = (key: 'privateKey' | 'publicKey' | 'address', value: unknown) => onTransportChange({ ...transport, warp: { ...warp, [key]: value } })

  const httpOptions: { value: MasqueHttpMode; label: string }[] = [
    ...(isServer ? [{ value: 'both' as const, label: t('coreEditor.masque.httpBoth', { defaultValue: 'HTTP/3 and HTTP/2 (h3, h2)' }) }] : []),
    { value: 'h3', label: t('coreEditor.masque.httpH3', { defaultValue: 'HTTP/3 over UDP (h3)' }) },
    { value: 'h2', label: t('coreEditor.masque.httpH2', { defaultValue: 'HTTP/2 over TCP (h2)' }) },
  ]
  const authOptions: { value: MasqueClientAuthMode; label: string }[] = [
    { value: 'none', label: t('coreEditor.masque.authNone', { defaultValue: 'None' }) },
    { value: 'basic', label: t('coreEditor.masque.authBasic', { defaultValue: 'User and password' }) },
    { value: 'warp', label: t('coreEditor.masque.authWarp', { defaultValue: 'Cloudflare WARP keys' }) },
  ]

  return (
    <div className="grid w-full min-w-0 gap-3 rounded-md border p-3 sm:col-span-2">
      <p className="text-sm font-medium">{t('coreEditor.masque.title', { defaultValue: 'MASQUE' })}</p>

      {isServer ? (
        <>
          <StringListField
            label={t('coreEditor.masque.addressPool', { defaultValue: 'Server address pool' })}
            hint={t('coreEditor.masque.addressPoolHint', {
              defaultValue: "The server's own address with its prefix, at most one IPv4 and one IPv6 (for example 10.14.0.1/16 and fd14::1/64). Clients get addresses from these subnets.",
            })}
            placeholder={t('coreEditor.stringArrayPopover.noValuesPlaceholder', { defaultValue: 'No values' })}
            value={cleanStringList(settings.address)}
            onChange={list => setSettingsKey('address', list)}
            t={t}
          >
            <FieldMessages issues={issues} field="address" />
          </StringListField>
          <div className="grid gap-3 sm:grid-cols-2">
            <ParsedTextField
              label={t('coreEditor.masque.mtu', { defaultValue: 'MTU' })}
              hint={t('coreEditor.masque.mtuHint', { defaultValue: 'Empty or 0 means 1280. Otherwise 1280 to 65535.' })}
              placeholder={String(MASQUE_DEFAULTS.mtu)}
              stored={storedNumber(settings.mtu)}
              parse={parseMasqueMtuInput}
              format={formatNumberInput}
              invalidMessage={t('coreEditor.masque.mtuInvalid', { defaultValue: 'MTU must be 0 or a whole number from 1280 to 65535.' })}
              onValue={value => setSettingsKey('mtu', value)}
              onValidityChange={invalid => report('mtu', invalid)}
            >
              <FieldMessages issues={issues} field="mtu" />
            </ParsedTextField>
            <StringListField
              label={t('coreEditor.masque.clientDns', { defaultValue: 'Client DNS' })}
              hint={t('coreEditor.masque.clientDnsHint', { defaultValue: 'DNS servers the panel puts in client configs. IP addresses only; Xray does not read this.' })}
              placeholder={t('coreEditor.stringArrayPopover.noValuesPlaceholder', { defaultValue: 'No values' })}
              value={cleanStringList(settings.remoteDNS)}
              onChange={list => setSettingsKey('remoteDNS', list.length > 0 ? list : undefined)}
              t={t}
            >
              <FieldMessages issues={issues} field="remoteDNS" />
            </StringListField>
          </div>
        </>
      ) : (
        <>
          <div className="grid gap-3 sm:grid-cols-2">
            <TrimmedTextField label={t('coreEditor.masque.serverAddress', { defaultValue: 'Server address' })} stored={settings.address} onValue={value => setSettingsKey('address', value)}>
              <FieldMessages issues={issues} field="address" />
            </TrimmedTextField>
            <ParsedTextField
              label={t('coreEditor.masque.serverPort', { defaultValue: 'Server port' })}
              stored={storedNumber(settings.port)}
              parse={parsePortInput}
              format={formatNumberInput}
              invalidMessage={t('coreEditor.masque.portInvalid', { defaultValue: 'Enter one port from 1 to 65535.' })}
              onValue={value => setSettingsKey('port', value)}
              onValidityChange={invalid => report('port', invalid)}
            >
              <FieldMessages issues={issues} field="port" />
            </ParsedTextField>
          </div>
          <StringListField
            label={t('coreEditor.masque.remoteDns', { defaultValue: 'Remote DNS' })}
            hint={t('coreEditor.masque.remoteDnsHint', { servers: MASQUE_DEFAULTS.clientRemoteDNS.join(', '), defaultValue: 'IP addresses only. Empty uses {{servers}}.' })}
            placeholder={MASQUE_DEFAULTS.clientRemoteDNS.join(', ')}
            value={cleanStringList(settings.remoteDNS)}
            onChange={list => setSettingsKey('remoteDNS', list.length > 0 ? list : undefined)}
            t={t}
          >
            <FieldMessages issues={issues} field="remoteDNS" />
          </StringListField>
        </>
      )}

      <SelectField
        label={t('coreEditor.masque.httpVersion', { defaultValue: 'HTTP version' })}
        hint={
          onAlpnChange === null
            ? t('coreEditor.masque.httpNeedsTls', { defaultValue: 'Set Security to TLS to choose the HTTP version.' })
            : isServer
              ? t('coreEditor.masque.httpServerHint', { defaultValue: 'Saved as the TLS ALPN. h3 listens on UDP, h2 on TCP, and both listens on both.' })
              : t('coreEditor.masque.httpClientHint', { defaultValue: 'Saved as the TLS ALPN. The server must accept the same version.' })
        }
        value={masqueHttpMode(alpn, side)}
        options={httpOptions}
        onValueChange={mode => onAlpnChange?.(masqueAlpnForMode(mode as MasqueHttpMode))}
        disabled={onAlpnChange === null}
      />

      {!isServer && (
        <SelectField
          label={t('coreEditor.masque.auth', { defaultValue: 'Authentication' })}
          value={authMode}
          options={authOptions}
          onValueChange={value => {
            const mode = value as MasqueClientAuthMode
            setBasicChosen(mode === 'basic')
            onTransportChange(applyMasqueClientAuthMode(transport, mode))
          }}
        />
      )}

      {showBasicAuthFields && (
        <div className="grid gap-3 sm:grid-cols-2">
          <TrimmedTextField
            label={t('coreEditor.masque.user', { defaultValue: 'User' })}
            hint={t('coreEditor.masque.userHint', { defaultValue: 'Sent as HTTP Basic auth, so it cannot contain a colon.' })}
            stored={transport.user}
            onValue={value => setTransportKey('user', value)}
          >
            <FieldMessages issues={issues} field="user" />
          </TrimmedTextField>
          <ParsedTextField
            label={t('coreEditor.field.password', { defaultValue: 'Password' })}
            password
            stored={typeof transport.pass === 'string' && transport.pass !== '' ? transport.pass : undefined}
            parse={parsePasswordInput}
            format={formatTextInput}
            invalidMessage=""
            onValue={value => setTransportKey('pass', value)}
            onValidityChange={ignoreValidity}
          >
            <FieldMessages issues={issues} field="pass" />
          </ParsedTextField>
        </div>
      )}

      {authMode === 'warp' && (
        <div className="grid w-full min-w-0 gap-3">
          <div className="grid gap-3 sm:grid-cols-2">
            <TrimmedTextField
              label={t('coreEditor.masque.warpPrivateKey', { defaultValue: 'WARP private key' })}
              multiline
              stored={warp.privateKey}
              onValue={value => setWarpKey('privateKey', value ?? '')}
            >
              <FieldMessages issues={issues} field="warp.privateKey" />
            </TrimmedTextField>
            <TrimmedTextField
              label={t('coreEditor.masque.warpPublicKey', { defaultValue: 'WARP public key' })}
              multiline
              stored={warp.publicKey}
              onValue={value => setWarpKey('publicKey', value ?? '')}
            >
              <FieldMessages issues={issues} field="warp.publicKey" />
            </TrimmedTextField>
          </div>
          <StreamFormHint>{t('coreEditor.masque.warpKeysHint', { defaultValue: 'From your WARP MASQUE registration: P-256 keys as PEM or base64 DER.' })}</StreamFormHint>
          <StringListField
            label={t('coreEditor.masque.warpAddress', { defaultValue: 'WARP tunnel addresses' })}
            hint={t('coreEditor.masque.warpAddressHint', { defaultValue: 'The addresses from the registration, at most one IPv4 and one IPv6.' })}
            placeholder={t('coreEditor.stringArrayPopover.noValuesPlaceholder', { defaultValue: 'No values' })}
            value={cleanStringList(warp.address)}
            onChange={list => setWarpKey('address', list)}
            t={t}
          >
            <FieldMessages issues={issues} field="warp.address" />
          </StringListField>
          <FieldMessages issues={issues} field="warp" />
          <StreamFormHint>
            {t('coreEditor.masque.warpDefaultsHint', {
              host: MASQUE_DEFAULTS.warpHost,
              path: MASQUE_DEFAULTS.warpPath,
              defaultValue: 'With WARP, an empty host means {{host}} and an empty path means {{path}}.',
            })}
          </StreamFormHint>
        </div>
      )}

      <div className="grid gap-3 sm:grid-cols-2">
        <TrimmedTextField
          label={t('coreEditor.field.path', { defaultValue: 'Path' })}
          hint={t('coreEditor.masque.pathHint', { defaultValue: 'Starts with /. Only the {target} and {ipproto} variables are allowed.' })}
          placeholder={authMode === 'warp' ? MASQUE_DEFAULTS.warpPath : MASQUE_DEFAULTS.path}
          stored={transport.path}
          onValue={value => setTransportKey('path', value)}
        >
          <FieldMessages issues={issues} field="path" />
        </TrimmedTextField>
        <TrimmedTextField
          label={t('coreEditor.masque.host', { defaultValue: 'Host' })}
          hint={t('coreEditor.masque.hostHint', { defaultValue: 'Optional host name or host:port, without scheme or path.' })}
          placeholder={authMode === 'warp' ? MASQUE_DEFAULTS.warpHost : undefined}
          stored={transport.host}
          onValue={value => setTransportKey('host', value)}
        >
          <FieldMessages issues={issues} field="host" />
        </TrimmedTextField>
      </div>

      <ParsedTextField
        label={t('coreEditor.masque.headers', { defaultValue: 'Headers (JSON object)' })}
        hint={t('coreEditor.masque.headersHint', { defaultValue: 'Host and Capsule-Protocol are not allowed, and Authorization is not allowed with a user or password.' })}
        multiline
        stored={storedObject(transport.headers)}
        parse={parseHeadersInput}
        format={formatJsonObjectInput}
        invalidMessage={t('coreEditor.masque.headersInvalid', { defaultValue: 'Headers must be a JSON object with text values.' })}
        onValue={value => setTransportKey('headers', value)}
        onValidityChange={invalid => report('headers', invalid)}
      >
        <FieldMessages issues={issues} field="headers" />
      </ParsedTextField>

      {!isServer && (
        <ParsedTextField
          label={t('coreEditor.masque.xmux', { defaultValue: 'XMUX (JSON object)' })}
          hint={t('coreEditor.masque.xmuxHint', { defaultValue: 'Optional connection reuse limits, as in XHTTP. Set maxConnections or maxConcurrency, not both.' })}
          multiline
          stored={storedObject(transport.xmux)}
          parse={parseXmuxInput}
          format={formatJsonObjectInput}
          invalidMessage={t('coreEditor.masque.xmuxInvalid', { defaultValue: 'XMUX must be a JSON object.' })}
          onValue={value => setTransportKey('xmux', value)}
          onValidityChange={invalid => report('xmux', invalid)}
        >
          <FieldMessages issues={issues} field="xmux" />
        </ParsedTextField>
      )}

      {showClientOnly && (
        <div className="grid w-full min-w-0 gap-1.5 rounded-md border border-dashed p-2">
          {MASQUE_CLIENT_ONLY_FIELDS.map(field => (
            <FieldMessages key={field} issues={issues} field={field} />
          ))}
          <div>
            <Button type="button" variant="outline" size="sm" className="h-8 text-xs" onClick={() => onTransportChange(removeMasqueClientOnlySettings(transport))}>
              {t('coreEditor.masque.removeClientOnly', { defaultValue: 'Remove client-only settings' })}
            </Button>
          </div>
        </div>
      )}

      <OtherFieldMessages issues={issues} shownFields={masqueShownFields(side, authMode, transport)} />
    </div>
  )
}
