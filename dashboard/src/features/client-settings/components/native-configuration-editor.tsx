import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import {
  atPath,
  decodeNativeRule,
  encodeNativeRule,
  nativeTargets,
  nativeRuleInsertionIndex,
  object,
  readNativeConfiguration,
  routingPath,
  referencedDNSServerTags,
  splitEntries,
  validDNS,
  validDomain,
  validIP,
  type MatchKind,
  type NativeDocument,
  type NativeFormat,
  type NativeSection,
} from '../forms/native-configuration'

export interface NativeConfigurationEditorProps {
  format: NativeFormat
  content: string
  onChange: (content: string) => void
  section: NativeSection
  onValidityChange?: (valid: boolean) => void
  onDirtyChange?: (dirty: boolean) => void
  onOpenCode?: () => void
}
const selectStyle = 'border-input bg-background h-10 w-full rounded-md border px-3 text-sm'

/** Draft controls are mounted independently from the serialized value. Explicit
 * Apply prevents partial input from rewriting source or changing React keys. */
function DraftField({
  label,
  value,
  multiline,
  validate,
  onApply,
  onDirty,
}: {
  label: string
  value: string
  multiline?: boolean
  validate?: (value: string) => boolean
  onApply: (value: string) => void
  onDirty: (dirty: boolean) => void
}) {
  const { t } = useTranslation()
  const [draft, setDraft] = useState(value)
  useEffect(() => {
    setDraft(value)
  }, [value])
  const dirty = draft !== value
  useEffect(() => {
    onDirty(dirty)
    return () => onDirty(false)
  }, [dirty, onDirty])
  const valid = !validate || validate(draft)
  return (
    <div className="space-y-2">
      <label className="grid gap-1.5 text-sm">
        <span className="font-medium">{label}</span>
        {multiline ? (
          <Textarea value={draft} onChange={event => setDraft(event.target.value)} className="min-h-24 font-mono text-xs" />
        ) : (
          <Input value={draft} onChange={event => setDraft(event.target.value)} />
        )}
      </label>
      {dirty && (
        <div className="flex items-center gap-2">
          <Button type="button" size="sm" disabled={!valid} onClick={() => onApply(draft)}>
            {t('clientSettings.native.apply', 'Apply')}
          </Button>
          <Button type="button" size="sm" variant="ghost" onClick={() => setDraft(value)}>
            {t('clientSettings.native.cancel', 'Cancel')}
          </Button>
          {!valid && (
            <span role="alert" className="text-destructive text-xs">
              {t('clientSettings.native.invalidValue', 'Enter a valid value.')}
            </span>
          )}
        </div>
      )}
    </div>
  )
}

export function NativeConfigurationEditor(props: NativeConfigurationEditorProps) {
  const { t } = useTranslation()
  const { format, content, onChange, section, onValidityChange, onDirtyChange, onOpenCode } = props
  const parsed = useMemo(() => {
    try {
      return { doc: readNativeConfiguration(format, content, section), error: '' }
    } catch (error) {
      return { doc: null, error: error instanceof SyntaxError ? 'invalidJson' : error instanceof Error ? error.message : 'invalidObject' }
    }
  }, [format, content, section])
  const [dirtyFields, setDirtyFields] = useState<Record<string, boolean>>({})
  const [writeError, setWriteError] = useState(false)
  // Cached callbacks keep draft effect dependencies stable while typing.
  const dirtyCallbacks = useMemo(() => new Map<string, (dirty: boolean) => void>(), [])
  const dirty = (key: string) => {
    if (!dirtyCallbacks.has(key)) dirtyCallbacks.set(key, value => setDirtyFields(previous => (previous[key] === value ? previous : { ...previous, [key]: value })))
    return dirtyCallbacks.get(key)!
  }
  const valid = !!parsed.doc && !Object.values(dirtyFields).some(Boolean) && !writeError
  const hasLocalDraft = Object.values(dirtyFields).some(Boolean) || writeError
  useEffect(() => {
    onValidityChange?.(valid)
  }, [valid, onValidityChange])
  useEffect(() => {
    onDirtyChange?.(hasLocalDraft)
  }, [hasLocalDraft, onDirtyChange])
  const update = (change: () => string) => {
    try {
      const next = change()
      setWriteError(false)
      onChange(next)
      return true
    } catch {
      setWriteError(true)
      return false
    }
  }
  const codeLink = (
    <Button type="button" variant="link" className="h-auto p-0" onClick={onOpenCode}>
      {t('clientSettings.native.openCode', 'Open code')}
    </Button>
  )
  if (!parsed.doc)
    return (
      <div className="space-y-2 rounded-md border p-4">
        <p role="status">
          {parsed.error === 'templatedSection'
            ? t('clientSettings.native.templatedSection', 'This section contains template logic. Edit it in code.')
            : t('clientSettings.native.parseError', 'This configuration cannot be edited visually. Check its syntax and structure in code.')}
        </p>
        {codeLink}
      </div>
    )
  const doc = parsed.doc
  return (
    <div className="space-y-5">
      {format === 'happ' ? (
        <HappEditor doc={doc} section={section} update={update} dirty={dirty} codeLink={codeLink} />
      ) : section === 'routing' ? (
        <RoutingEditor format={format} doc={doc} update={update} onDirty={dirty('routing-draft')} codeLink={codeLink} />
      ) : (
        <DNSEditor format={format} doc={doc} update={update} dirty={dirty} codeLink={codeLink} />
      )}
      {Object.values(dirtyFields).some(Boolean) && (
        <p role="status" className="text-muted-foreground text-sm">
          {t('clientSettings.native.pending', 'Apply or cancel your edits before saving or changing mode.')}
        </p>
      )}
      {writeError && (
        <p role="alert" className="text-destructive text-sm">
          {t('clientSettings.native.writeError', 'This structure needs to be edited in code. Your source has not changed.')} {codeLink}
        </p>
      )}
    </div>
  )
}

type Common = { doc: NativeDocument; update: (change: () => string) => boolean; codeLink: React.ReactNode }
const targetKey = (id: string, action?: 'reject') => JSON.stringify([action ?? 'outbound', id])
function RoutingEditor({ format, doc, update, onDirty, codeLink }: Common & { format: NativeFormat; onDirty: (dirty: boolean) => void }) {
  const { t } = useTranslation()
  const path = routingPath(format)
  const raw = atPath(doc.data, path)
  const rules = Array.isArray(raw) ? raw : []
  const targets = nativeTargets(format, doc.data)
  const [editing, setEditing] = useState<number | null>(null)
  const [kind, setKind] = useState<MatchKind>('domain')
  const [values, setValues] = useState('')
  const [target, setTarget] = useState('')
  const pending = editing !== null || !!values
  useEffect(() => {
    onDirty(pending)
    return () => onDirty(false)
  }, [pending, onDirty])
  const entries = splitEntries(values)
  const selectedTarget = target || (targets[0] ? targetKey(targets[0].id, targets[0].action) : '')
  const selected = targets.find(item => targetKey(item.id, item.action) === selectedTarget)
  const valid = entries.length > 0 && entries.every(kind === 'ip' ? validIP : validDomain) && !!selected && !selected.id.includes(',')
  if (raw !== undefined && !Array.isArray(raw))
    return (
      <p>
        {t('clientSettings.native.complexSection', 'This section uses an advanced structure.')} {codeLink}
      </p>
    )
  const commit = () => {
    if (!selected) return
    const encoded = encodeNativeRule(format, { kind, values: entries, target: selected.id, action: selected.action })
    const next = [...rules],
      indices: (number | null)[] = rules.map((_, index) => index)
    if (editing === null) {
      const insertion = nativeRuleInsertionIndex(format, rules)
      next.splice(insertion, 0, ...encoded)
      indices.splice(insertion, 0, ...encoded.map(() => null))
    } else {
      next.splice(editing, 1, ...encoded)
      indices.splice(editing, 1, ...encoded.map((_, index) => (index === 0 ? editing : null)))
    }
    if (update(() => doc.list(path, next, indices))) {
      setEditing(null)
      setValues('')
      setTarget('')
    }
  }
  const move = (index: number, direction: number) => {
    const next = [...rules],
      indices = rules.map((_, i) => i)
    ;[next[index], next[index + direction]] = [next[index + direction], next[index]]
    ;[indices[index], indices[index + direction]] = [indices[index + direction], indices[index]]
    update(() => doc.list(path, next, indices))
  }
  const label = (id: string, action?: 'reject') => {
    if (action === 'reject') return t('clientSettings.native.block', 'Block')
    const item = targets.find(option => option.id === id && !option.action)
    return item?.label === 'Direct'
      ? `${t('clientSettings.native.direct', 'Direct')} · ${id}`
      : item?.label === 'Block'
        ? `${t('clientSettings.native.block', 'Block')} · ${id}`
        : item?.label === 'Proxy' || id === 'PROXY' || id === 'proxy'
          ? `${t('clientSettings.native.vpn', 'Through VPN')} · ${id}`
          : id
  }
  return (
    <div className="space-y-4">
      <p className="text-muted-foreground text-sm">{t('clientSettings.native.orderHelp', 'Rules are evaluated from top to bottom. The first matching rule wins.')}</p>
      <div className="space-y-2">
        {rules.map((rule, index) => {
          const simple = decodeNativeRule(format, rule)
          return (
            <div key={index} className="flex flex-wrap items-center gap-2 rounded-md border p-3">
              <span className="text-muted-foreground text-xs">{index + 1}</span>
              <div className="min-w-0 flex-1">
                {simple ? (
                  <>
                    <span className="text-xs font-medium">
                      {simple.kind === 'domain'
                        ? t('clientSettings.native.domain', 'Exact domain')
                        : simple.kind === 'suffix'
                          ? t('clientSettings.native.suffix', 'Domain and subdomains')
                          : t('clientSettings.native.ip', 'IP / CIDR')}{' '}
                      → {label(simple.target, simple.action)}
                    </span>
                    <p className="font-mono text-xs break-all">{simple.values.join(', ')}</p>
                  </>
                ) : (
                  <>
                    <p className="text-sm">{t('clientSettings.native.complexRule', 'Advanced rule — preserved in its original form')}</p>
                    <pre className="max-h-24 overflow-auto text-xs break-all whitespace-pre-wrap">{typeof rule === 'string' ? rule : JSON.stringify(rule)}</pre>
                    {codeLink}
                  </>
                )}
              </div>
              {simple && (
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  disabled={pending}
                  onClick={() => {
                    setEditing(index)
                    setKind(simple.kind)
                    setValues(simple.values.join('\n'))
                    setTarget(targetKey(simple.target, simple.action))
                  }}
                >
                  {t('clientSettings.native.edit', 'Edit')}
                </Button>
              )}
              <Button type="button" variant="ghost" size="sm" aria-label={t('clientSettings.native.moveUp', 'Move up')} disabled={index === 0 || pending} onClick={() => move(index, -1)}>
                ↑
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                aria-label={t('clientSettings.native.moveDown', 'Move down')}
                disabled={index === rules.length - 1 || pending}
                onClick={() => move(index, 1)}
              >
                ↓
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                disabled={pending}
                onClick={() =>
                  update(() =>
                    doc.list(
                      path,
                      rules.filter((_, i) => i !== index),
                      rules.map((_, i) => i).filter(i => i !== index),
                    ),
                  )
                }
              >
                {t('clientSettings.native.remove', 'Remove')}
              </Button>
            </div>
          )
        })}
      </div>
      <div className="space-y-3 rounded-md border p-4">
        <h4 className="font-medium">{editing === null ? t('clientSettings.native.addRule', 'Add rule') : t('clientSettings.native.editRule', 'Edit rule')}</h4>
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="grid gap-1 text-sm">
            {t('clientSettings.native.match', 'Match')}
            <select className={selectStyle} value={kind} onChange={event => setKind(event.target.value as MatchKind)}>
              <option value="domain">{t('clientSettings.native.domain', 'Exact domain')}</option>
              <option value="suffix">{t('clientSettings.native.suffix', 'Domain and subdomains')}</option>
              <option value="ip">{t('clientSettings.native.ip', 'IP / CIDR')}</option>
            </select>
          </label>
          <label className="grid gap-1 text-sm">
            {t('clientSettings.native.target', 'Destination')}
            <select className={selectStyle} value={selectedTarget} onChange={event => setTarget(event.target.value)}>
              {!targets.length && <option value="">{t('clientSettings.native.noTargets', 'Add an outbound in code first')}</option>}
              {target && !selected && (
                <option value={target} disabled>
                  {t('clientSettings.native.missingTarget', 'The existing destination is missing. Select an available destination or edit the code.')}
                </option>
              )}
              {targets.map(item => (
                <option value={targetKey(item.id, item.action)} key={targetKey(item.id, item.action)}>
                  {label(item.id, item.action)}
                </option>
              ))}
            </select>
          </label>
        </div>
        <label className="grid gap-1 text-sm">
          {t('clientSettings.native.entries', 'Entries — one per line, or paste a list')}
          <Textarea value={values} onChange={event => setValues(event.target.value)} className="min-h-24 font-mono text-xs" />
        </label>
        {!!values && !valid && (
          <p role="alert" className="text-destructive text-sm">
            {t('clientSettings.native.invalidEntries', 'Check every domain or IP/CIDR and select a destination.')}
          </p>
        )}
        <div className="flex gap-2">
          <Button type="button" disabled={!valid} onClick={commit}>
            {editing === null ? t('clientSettings.native.add', 'Add') : t('clientSettings.native.apply', 'Apply')}
          </Button>
          {pending && (
            <Button
              type="button"
              variant="outline"
              onClick={() => {
                setEditing(null)
                setValues('')
                setTarget('')
              }}
            >
              {t('clientSettings.native.cancel', 'Cancel')}
            </Button>
          )}
        </div>
      </div>
    </div>
  )
}

function HappEditor({ doc, section, update, dirty, codeLink }: Common & { section: NativeSection; dirty: (key: string) => (dirty: boolean) => void }) {
  const { t } = useTranslation()
  const field = (key: string, validate?: (value: string) => boolean, multiline = false, label = key) => {
    const value = doc.data[key]
    if (value !== undefined && (multiline ? !Array.isArray(value) || !value.every(item => typeof item === 'string') : typeof value !== 'string' && typeof value !== 'boolean'))
      return (
        <div key={key}>
          {key}: {t('clientSettings.native.complexSection', 'This section uses an advanced structure.')} {codeLink}
        </div>
      )
    return (
      <DraftField
        key={key}
        label={label}
        value={multiline ? ((value as string[] | undefined)?.join('\n') ?? '') : value === undefined ? '' : String(value)}
        multiline={multiline}
        validate={validate}
        onDirty={dirty(key)}
        onApply={next => update(() => doc.set([key], multiline ? splitEntries(next) : typeof value === 'boolean' ? next === 'true' : next))}
      />
    )
  }
  const boolean = (key: string, label = key) => {
    const value = doc.data[key]
    if (value !== undefined && !['true', 'false', true, false].includes(value as string | boolean))
      return (
        <p>
          {key}: {codeLink}
        </p>
      )
    return (
      <label className="grid gap-1 text-sm" key={key}>
        {label}
        <select
          className={selectStyle}
          value={value === undefined ? '' : String(value)}
          onChange={event => update(() => doc.set([key], typeof value === 'boolean' ? event.target.value === 'true' : event.target.value))}
        >
          <option value="" disabled>
            {t('clientSettings.native.default', 'Client default')}
          </option>
          <option value="true">{key === 'GlobalProxy' ? t('clientSettings.native.vpn', 'Through VPN') : t('clientSettings.native.enabled', 'Enabled')}</option>
          <option value="false">{key === 'GlobalProxy' ? t('clientSettings.native.direct', 'Direct') : t('clientSettings.native.disabled', 'Disabled')}</option>
        </select>
      </label>
    )
  }
  if (section === 'routing')
    return (
      <div className="space-y-5">
        {field('Name', value => !!value.trim(), false, t('clientSettings.native.happName', 'Profile name in Happ'))}
        {boolean('GlobalProxy', t('clientSettings.native.remainingTraffic', 'Remaining traffic'))}
        {(['Direct', 'Proxy', 'Block'] as const).map(action => (
          <fieldset key={action} className="space-y-3 rounded-md border p-4">
            <legend className="px-1 font-medium">
              {action === 'Direct' ? t('clientSettings.native.direct', 'Direct') : action === 'Proxy' ? t('clientSettings.native.vpn', 'Through VPN') : t('clientSettings.native.block', 'Block')}
            </legend>
            <div className="grid gap-4 md:grid-cols-2">
              {field(
                `${action}Sites`,
                value => splitEntries(value).every(item => validDomain(item) || /^(?:geosite|domain|full|regexp|keyword|ext):\S+$/.test(item)),
                true,
                t('clientSettings.native.domains', 'Domains'),
              )}
              {field(`${action}Ip`, value => splitEntries(value).every(item => validIP(item) || /^geoip:[\w!@.-]+$/.test(item)), true, t('clientSettings.native.ip', 'IP / CIDR'))}
            </div>
          </fieldset>
        ))}
      </div>
    )
  return (
    <div className="space-y-5">
      {['Remote', 'Domestic'].map(prefix => (
        <fieldset key={prefix} className="space-y-3 rounded-md border p-4">
          <legend className="px-1 font-medium">{prefix === 'Remote' ? t('clientSettings.native.remoteDNS', 'Tunnel DNS') : t('clientSettings.native.domesticDNS', 'Direct DNS')}</legend>
          <label className="grid gap-1 text-sm">
            {t('clientSettings.native.dnsProtocol', 'DNS protocol')}
            <select
              className={selectStyle}
              value={typeof doc.data[`${prefix}DNSType`] === 'string' ? String(doc.data[`${prefix}DNSType`]) : ''}
              onChange={event => update(() => doc.set([`${prefix}DNSType`], event.target.value))}
            >
              <option value="" disabled>
                {t('clientSettings.native.default', 'Client default')}
              </option>
              {[...new Set(['DoH', 'DoU', ...(typeof doc.data[`${prefix}DNSType`] === 'string' ? [String(doc.data[`${prefix}DNSType`])] : [])])].map(value => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </label>
          {field(`${prefix}DNSIP`, value => !value || (validIP(value) && !value.includes('/')), false, t('clientSettings.native.dnsAddress', 'DNS server IP'))}
          {field(`${prefix}DNSDomain`, value => !value || validDNS(value) || validDomain(value), false, t('clientSettings.native.dnsUrl', 'DNS URL or domain'))}
        </fieldset>
      ))}
      {boolean('FakeDNS')}
      {doc.data.DnsHosts !== undefined && (
        <div className="rounded-md border p-3">
          <p>DnsHosts</p>
          <pre className="overflow-auto text-xs">{JSON.stringify(doc.data.DnsHosts, null, 2)}</pre>
          {codeLink}
        </div>
      )}
    </div>
  )
}

function DNSEditor({ format, doc, update, dirty, codeLink }: Common & { format: NativeFormat; dirty: (key: string) => (dirty: boolean) => void }) {
  const { t } = useTranslation()
  const dns = doc.data.dns
  if (dns !== undefined && !object(dns))
    return (
      <p>
        {t('clientSettings.native.complexSection', 'This section uses an advanced structure.')} {codeLink}
      </p>
    )
  const config = object(dns) ? dns : {}
  if (format === 'clash')
    return (
      <div className="space-y-4">
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={config.enable === true} onChange={event => update(() => doc.set(['dns', 'enable'], event.target.checked))} />
          {t('clientSettings.native.enableDNS', 'Enable DNS')}
        </label>
        {['nameserver', 'fallback', 'default-nameserver', 'proxy-server-nameserver'].map(key => {
          const value = config[key]
          if (value !== undefined && (!Array.isArray(value) || !value.every(item => typeof item === 'string')))
            return (
              <p key={key}>
                {key}: {codeLink}
              </p>
            )
          return (
            <DraftField
              key={key}
              label={key}
              value={(value as string[] | undefined)?.join('\n') ?? ''}
              multiline
              validate={value => splitEntries(value).every(item => validDNS(item, 'clash'))}
              onDirty={dirty(key)}
              onApply={next => update(() => doc.list(['dns', key], splitEntries(next)))}
            />
          )
        })}
        {Object.keys(config).filter(key => !['enable', 'nameserver', 'fallback', 'default-nameserver', 'proxy-server-nameserver'].includes(key)).length > 0 && (
          <div className="rounded-md border p-3">
            <p>{t('clientSettings.native.otherDNS', 'Additional DNS settings and policies are preserved.')}</p>
            {codeLink}
          </div>
        )}
      </div>
    )
  return <ServerEditor format={format} doc={doc} config={config} update={update} onDirty={dirty('server-draft')} codeLink={codeLink} />
}

function ServerEditor({ format, doc, config, update, onDirty, codeLink }: Common & { format: NativeFormat; config: Record<string, unknown>; onDirty: (dirty: boolean) => void }) {
  const { t } = useTranslation()
  const [editing, setEditing] = useState<number | null>(null)
  const [address, setAddress] = useState('')
  const [tag, setTag] = useState('')
  const [transport, setTransport] = useState('udp')
  const [port, setPort] = useState('')
  const pending = editing !== null || !!address || !!tag || !!port
  useEffect(() => {
    onDirty(pending)
    return () => onDirty(false)
  }, [pending, onDirty])
  if (config.servers !== undefined && !Array.isArray(config.servers))
    return (
      <p>
        {t('clientSettings.native.complexSection', 'This section uses an advanced structure.')} {codeLink}
      </p>
    )
  const servers = Array.isArray(config.servers) ? config.servers : []
  const references = format === 'sing_box' ? referencedDNSServerTags(doc.data) : new Set<string>()
  const isReferenced = (server: unknown) => object(server) && typeof server.tag === 'string' && references.has(server.tag)
  const referenceHelp = (
    <p className="text-muted-foreground basis-full text-xs">
      {t('clientSettings.native.referencedDNS', 'This server is referenced by DNS rules or resolvers. Update those references in code before renaming or removing it.')} {codeLink}
    </p>
  )
  const original = editing !== null ? servers[editing] : undefined
  const tagLocked = isReferenced(original)
  const modern = format === 'sing_box' && !(object(original) && typeof original.address === 'string')
  const valid =
    !!address &&
    (modern ? validDomain(address) || (validIP(address) && !address.includes('/')) : validDNS(address)) &&
    (!modern || !!tag.trim()) &&
    (!port || (/^\d+$/.test(port) && Number(port) > 0 && Number(port) <= 65535)) &&
    (!modern || !servers.some((server, index) => index !== editing && object(server) && server.tag === tag))
  const supported = (server: unknown) =>
    format === 'xray'
      ? typeof server === 'string' || (object(server) && typeof server.address === 'string')
      : object(server) && (typeof server.address === 'string' || (['udp', 'tcp', 'tls', 'https', 'quic', 'h3'].includes(String(server.type)) && typeof server.server === 'string'))
  const reset = () => {
    setEditing(null)
    setAddress('')
    setTag('')
    setPort('')
    setTransport('udp')
  }
  const apply = () => {
    if (tagLocked && object(original) && tag !== original.tag) return
    let value: unknown
    if (modern) {
      value = { ...(object(original) ? original : {}), type: transport, tag, server: address }
      if (object(value) && port) value.server_port = Number(port)
      else if (object(value)) delete value.server_port
    } else value = object(original) ? { ...original, address } : address
    const next = [...servers]
    if (editing === null) next.push(value)
    else next[editing] = value
    if (update(() => doc.list(['dns', 'servers'], next))) reset()
  }
  return (
    <div className="space-y-4">
      <div className="space-y-2">
        {servers.map((server, index) => (
          <div key={index} className="flex flex-wrap items-center gap-2 rounded-md border p-3">
            <pre className="min-w-0 flex-1 overflow-auto text-xs break-all whitespace-pre-wrap">{typeof server === 'string' ? server : JSON.stringify(server, null, 2)}</pre>
            {supported(server) ? (
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={pending}
                onClick={() => {
                  setEditing(index)
                  setAddress(typeof server === 'string' ? server : String(object(server) ? (server.address ?? server.server) : ''))
                  setTag(object(server) && typeof server.tag === 'string' ? server.tag : '')
                  setTransport(object(server) && typeof server.type === 'string' ? server.type : 'udp')
                  setPort(object(server) && server.server_port !== undefined ? String(server.server_port) : '')
                }}
              >
                {t('clientSettings.native.edit', 'Edit')}
              </Button>
            ) : (
              codeLink
            )}
            <Button
              type="button"
              variant="ghost"
              size="sm"
              disabled={pending || isReferenced(server)}
              onClick={() =>
                !isReferenced(server) &&
                update(() =>
                  doc.list(
                    ['dns', 'servers'],
                    servers.filter((_, i) => i !== index),
                  ),
                )
              }
            >
              {t('clientSettings.native.remove', 'Remove')}
            </Button>
            {isReferenced(server) && referenceHelp}
          </div>
        ))}
      </div>
      <div className="space-y-3 rounded-md border p-4">
        <h4 className="font-medium">{editing === null ? t('clientSettings.native.addServer', 'Add DNS server') : t('clientSettings.native.editServer', 'Edit DNS server')}</h4>
        {modern && (
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="grid gap-1 text-sm">
              {t('clientSettings.native.tag', 'Server ID')}
              <Input value={tag} disabled={tagLocked} onChange={event => setTag(event.target.value)} />
            </label>
            <label className="grid gap-1 text-sm">
              {t('clientSettings.native.transport', 'Transport')}
              <select className={selectStyle} value={transport} onChange={event => setTransport(event.target.value)}>
                {['udp', 'tcp', 'tls', 'https', 'quic', 'h3'].map(value => (
                  <option key={value} value={value}>
                    {value}
                  </option>
                ))}
              </select>
            </label>
          </div>
        )}
        {tagLocked && referenceHelp}
        <label className="grid gap-1 text-sm">
          {modern ? t('clientSettings.native.serverHost', 'Server IP or hostname') : t('clientSettings.native.serverAddress', 'DNS IP or URL')}
          <Input value={address} onChange={event => setAddress(event.target.value)} />
        </label>
        {modern && (
          <label className="grid gap-1 text-sm">
            {t('clientSettings.native.port', 'Port (optional)')}
            <Input value={port} onChange={event => setPort(event.target.value)} inputMode="numeric" />
          </label>
        )}
        {pending && !valid && (
          <p role="alert" className="text-destructive text-sm">
            {t('clientSettings.native.invalidServer', 'Check the DNS address, unique server ID and port.')}
          </p>
        )}
        <div className="flex gap-2">
          <Button type="button" disabled={!valid} onClick={apply}>
            {editing === null ? t('clientSettings.native.add', 'Add') : t('clientSettings.native.apply', 'Apply')}
          </Button>
          {pending && (
            <Button type="button" variant="outline" onClick={reset}>
              {t('clientSettings.native.cancel', 'Cancel')}
            </Button>
          )}
        </div>
      </div>
      {Object.keys(config).some(key => key !== 'servers') && (
        <div className="rounded-md border p-3">
          <p>{t('clientSettings.native.otherDNS', 'Additional DNS settings and policies are preserved.')}</p>
          {codeLink}
        </div>
      )}
    </div>
  )
}
