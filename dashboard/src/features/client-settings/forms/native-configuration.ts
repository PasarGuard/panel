import { applyEdits, modify, parseTree, type Node as JsonNode } from 'jsonc-parser'
import { isMap, isNode, isSeq, parseDocument, stringify } from 'yaml'
import { DEFAULT_TEMPLATE_CONTENT } from '../../templates/forms/client-template-form'

export type NativeFormat = 'happ' | 'xray' | 'sing_box' | 'clash'
export type NativeSection = 'routing' | 'dns'
type Path = (string | number)[]
export type NativeObject = Record<string, unknown>
export const object = (value: unknown): value is NativeObject => !!value && typeof value === 'object' && !Array.isArray(value)
const jinja = /\{[{%#]/

/** A section boundary, never a Jinja rendering or a reserialization of the template. */
function yamlBlock(source: string, key: string, allowTemplate = false) {
  const keys = [...source.matchAll(/^([A-Za-z_][\w-]*):(?=\s|$)/gm)]
  const matches = keys.filter(match => match[1] === key)
  if (matches.length > 1) throw new Error('duplicateSection')
  const match = matches[0]
  if (!match) return { start: source.length, end: source.length, text: '' }
  const next = keys.find(item => item.index! > match.index!)
  const start = match.index!
  const end = next?.index ?? source.length
  const text = source.slice(start, end)
  if (jinja.test(text) && !allowTemplate) throw new Error('templatedSection')
  // A surrounding Jinja condition/loop changes whether this section exists.
  let depth = 0
  for (const token of source.slice(0, start).matchAll(/\{%\s*(\w+)[\s\S]*?%\}/g)) {
    if (['if', 'for', 'macro', 'block', 'filter', 'with', 'call'].includes(token[1])) depth++
    if (token[1].startsWith('end')) depth--
  }
  if (depth !== 0) throw new Error('templatedSection')
  return { start, end, text }
}

export interface NativeDocument {
  data: NativeObject
  set: (path: Path, value: unknown) => string
  list: (path: Path, values: unknown[], sourceIndices?: (number | null)[]) => string
}

/** Read and patch the original source. Opening Visual mode never emits a write. */
export function readNativeConfiguration(format: NativeFormat, source: string, section: NativeSection): NativeDocument {
  if (format !== 'clash') {
    if (jinja.test(source)) throw new Error('templatedSection')
    const data: unknown = JSON.parse(source)
    if (!object(data)) throw new Error('invalidObject')
    const tree = parseTree(source)
    // JSON.parse silently accepts duplicate keys; a visual editor must not.
    const check = (node: JsonNode | undefined) => {
      if (node?.type === 'object') {
        const keys = node.children?.map(child => child.children?.[0].value)
        if (keys && new Set(keys).size !== keys.length) throw new Error('duplicateSection')
      }
      node?.children?.forEach(check)
    }
    check(tree)
    const set = (path: Path, value: unknown) => applyEdits(source, modify(source, path, value, { formattingOptions: { insertSpaces: true, tabSize: 2, eol: source.includes('\r\n') ? '\r\n' : '\n' } }))
    return { data, set, list: (path, values) => set(path, values) }
  }
  const key = section === 'routing' ? 'rules' : 'dns'
  // Quoted top-level keys and root flow mappings are valid YAML, but are not
  // safe boundaries for the targeted block editor. Never append a duplicate.
  if (/^\s*\{(?![{%#])/.test(source) || new RegExp(`^["']${key}["']\\s*:`, 'm').test(source)) throw new Error('unsupportedShape')
  const block = yamlBlock(source, key)
  if (!jinja.test(source)) {
    const whole = parseDocument(source, { uniqueKeys: true })
    if (whole.errors.length || (whole.contents !== null && !isMap(whole.contents))) throw new Error('invalidYaml')
  }
  const doc = parseDocument(block.text || `${key}: ${key === 'rules' ? '[]' : '{}'}\n`, { keepSourceTokens: true, uniqueKeys: true })
  if (doc.errors.length || !isMap(doc.contents)) throw new Error('invalidYaml')
  const data = doc.toJS({ maxAliasCount: 0 }) as NativeObject
  // Only inspect static target sections. They may legitimately contain Jinja.
  for (const targetKey of ['proxies', 'proxy-groups']) {
    try {
      const target = yamlBlock(source, targetKey, true)
      if (target.text) {
        // Static names are still usable when a group's member list is templated.
        // This read-only projection never gets written back to source.
        const projection = target.text
          .split('\n')
          .filter(line => !jinja.test(line))
          .join('\n')
        const parsed = parseDocument(projection)
        if (!parsed.errors.length) Object.assign(data, parsed.toJS({ maxAliasCount: 0 }))
      }
    } catch {
      /* Dynamic targets remain visible on existing rules. */
    }
  }
  const checked = (next: string) => {
    readNativeConfiguration(format, next, section)
    return next
  }
  const replace = (start: number, end: number, text: string) => checked(source.slice(0, block.start + start) + text + source.slice(block.start + end))
  const set = (path: Path, value: unknown): string => {
    const node = doc.getIn(path, true)
    if (block.text && isNode(node) && node.range) {
      // JSON flow values are valid YAML and do not alter neighbouring comments/keys.
      const separator = /(?:\r?\n[ \t]*)+$/.exec(block.text.slice(node.range[0], node.range[1]))?.[0] ?? ''
      return replace(node.range[0], node.range[1], JSON.stringify(value) + separator)
    }
    if (!block.text) {
      const nested = path.length === 1 ? value : { [String(path[1])]: value }
      return checked(source + (source.endsWith('\n') || !source ? '' : '\n') + stringify({ [key]: nested }))
    }
    const parent = doc.getIn(path.slice(0, -1), true)
    if (isMap(parent) && !parent.flow && parent.range) {
      const indent = path.length > 1 ? '  ' : ''
      const at = parent.range[1]
      return replace(at, at, `${block.text[at - 1] === '\n' ? '' : '\n'}${indent}${String(path[path.length - 1])}: ${JSON.stringify(value)}\n`)
    }
    if (isMap(parent) && parent.flow && parent.range && parent.items.length === 0) {
      return replace(parent.range[0], parent.range[1], JSON.stringify({ [String(path[path.length - 1])]: value }))
    }
    throw new Error('unsupportedShape')
  }
  const list = (path: Path, values: unknown[], sourceIndices?: (number | null)[]) => {
    const node = doc.getIn(path, true)
    if (!sourceIndices && isSeq(node)) {
      const available = node.items.map((item, index) => ({ value: JSON.stringify(isNode(item) ? item.toJSON() : item), index }))
      sourceIndices = values.map(value => {
        const found = available.findIndex(item => item.value === JSON.stringify(value))
        return found < 0 ? null : available.splice(found, 1)[0].index
      })
      if (values.length === node.items.length) sourceIndices = sourceIndices.map(index => index ?? available.shift()?.index ?? null)
    }
    if (!block.text || !isSeq(node) || node.flow || !node.range || !sourceIndices || !node.items.length) return set(path, values)
    // Preserve the exact source slice of each existing block-sequence item,
    // including comments. A changed/new scalar is the only serialized item.
    const ranges = node.items.map(item => {
      if (!isNode(item) || !item.range) throw new Error('unsupportedShape')
      const start = block.text.lastIndexOf('\n', item.range[0] - 1) + 1
      if (!/^\s*-\s/.test(block.text.slice(start, item.range[0]))) throw new Error('unsupportedShape')
      return { start, end: item.range[2] }
    })
    const start = ranges[0].start
    const end = node.range[2]
    const indent = block.text.slice(start).match(/^\s*/)?.[0] ?? ''
    if (!values.length) return replace(node.range[0], node.range[1], '[]\n')
    const text = values
      .map((value, index) => {
        const old = sourceIndices[index]
        if (old !== null && old !== undefined && ranges[old]) {
          const item = node.items[old]
          const raw = block.text.slice(ranges[old].start, ranges[old + 1]?.start ?? end)
          if (isNode(item) && item.range && JSON.stringify(item.toJSON()) !== JSON.stringify(value)) {
            const relativeStart = item.range[0] - ranges[old].start
            const relativeEnd = item.range[1] - ranges[old].start
            return raw.slice(0, relativeStart) + JSON.stringify(value) + raw.slice(relativeEnd)
          }
          return raw
        }
        return `${indent}- ${JSON.stringify(value)}\n`
      })
      .join('')
    return replace(start, end, text)
  }
  return { data, set, list }
}

export const routingPath = (format: NativeFormat): Path => (format === 'clash' ? ['rules'] : [format === 'sing_box' ? 'route' : 'routing', 'rules'])
export function atPath(data: NativeObject, path: Path): unknown {
  return path.reduce<unknown>((value, key) => (object(value) || Array.isArray(value) ? (value as Record<string | number, unknown>)[key] : undefined), data)
}
export type MatchKind = 'domain' | 'suffix' | 'ip'
export interface SimpleNativeRule {
  kind: MatchKind
  values: string[]
  target: string
  action?: 'reject'
}
export function decodeNativeRule(format: NativeFormat, rule: unknown): SimpleNativeRule | null {
  if (format === 'clash') {
    if (typeof rule !== 'string') return null
    const parts = rule.split(',')
    const kind: MatchKind | undefined = ({ DOMAIN: 'domain', 'DOMAIN-SUFFIX': 'suffix', 'IP-CIDR': 'ip', 'IP-CIDR6': 'ip' } as Record<string, MatchKind>)[parts[0]]
    if (!kind || parts.length !== 3 || !parts[2]) return null
    return { kind, values: [parts[1]], target: parts[2] }
  }
  if (!object(rule)) return null
  if (format === 'xray') {
    if (Object.keys(rule).some(key => !['type', 'domain', 'ip', 'outboundTag'].includes(key)) || (rule.type !== undefined && rule.type !== 'field') || typeof rule.outboundTag !== 'string') return null
    if (rule.ip && rule.domain) return null
    if (Array.isArray(rule.ip) && rule.ip.length && rule.ip.every(value => typeof value === 'string' && validIP(value))) return { kind: 'ip', values: rule.ip, target: rule.outboundTag }
    if (!Array.isArray(rule.domain) || !rule.domain.length || !rule.domain.every(value => typeof value === 'string')) return null
    const prefix = rule.domain.every(value => value.startsWith('full:')) ? 'full:' : rule.domain.every(value => value.startsWith('domain:')) ? 'domain:' : null
    return prefix ? { kind: prefix === 'full:' ? 'domain' : 'suffix', values: rule.domain.map(value => value.slice(prefix.length)), target: rule.outboundTag } : null
  }
  if (
    Object.keys(rule).some(key => !['domain', 'domain_suffix', 'ip_cidr', 'outbound', 'action'].includes(key)) ||
    (rule.action !== undefined && rule.action !== 'route' && rule.action !== 'reject') ||
    (rule.action === 'reject' ? rule.outbound !== undefined : typeof rule.outbound !== 'string')
  )
    return null
  const keys = ['domain', 'domain_suffix', 'ip_cidr'].filter(key => rule[key] !== undefined)
  if (keys.length !== 1) return null
  const raw = rule[keys[0]],
    values = typeof raw === 'string' ? [raw] : raw
  if (!Array.isArray(values) || !values.length || !values.every(value => typeof value === 'string')) return null
  return {
    kind: keys[0] === 'domain' ? 'domain' : keys[0] === 'domain_suffix' ? 'suffix' : 'ip',
    values,
    target: rule.action === 'reject' ? 'reject' : (rule.outbound as string),
    ...(rule.action === 'reject' ? { action: 'reject' as const } : {}),
  }
}
export function encodeNativeRule(format: NativeFormat, rule: SimpleNativeRule): unknown[] {
  if (format === 'clash')
    return rule.values.map(value => `${rule.kind === 'domain' ? 'DOMAIN' : rule.kind === 'suffix' ? 'DOMAIN-SUFFIX' : value.includes(':') ? 'IP-CIDR6' : 'IP-CIDR'},${value},${rule.target}`)
  if (format === 'xray')
    return [
      {
        type: 'field',
        [rule.kind === 'ip' ? 'ip' : 'domain']: rule.values.map(value => (rule.kind === 'domain' ? `full:${value}` : rule.kind === 'suffix' ? `domain:${value}` : value)),
        outboundTag: rule.target,
      },
    ]
  return [{ [rule.kind === 'ip' ? 'ip_cidr' : rule.kind === 'suffix' ? 'domain_suffix' : 'domain']: rule.values, ...(rule.action === 'reject' ? { action: 'reject' } : { outbound: rule.target }) }]
}
export interface NativeTarget {
  id: string
  label: string
  action?: 'reject'
}
export function nativeTargets(format: NativeFormat, data: NativeObject): NativeTarget[] {
  const result: NativeTarget[] = []
  const add = (id: unknown, label?: string) => {
    if (typeof id === 'string' && id && !result.some(item => item.id === id)) result.push({ id, label: label ?? id })
  }
  if (format === 'clash') {
    add('DIRECT', 'Direct')
    add('REJECT', 'Block')
    for (const key of ['proxies', 'proxy-groups']) if (Array.isArray(data[key])) for (const item of data[key]) if (object(item)) add(item.name)
  } else {
    if (format === 'xray') add('proxy', 'Proxy') // app/subscription/xray.py generates this exact tag.
    for (const key of ['outbounds', 'endpoints'])
      if (Array.isArray(data[key]))
        for (const item of data[key])
          if (object(item)) {
            const type = item.protocol ?? item.type
            add(item.tag, ['direct', 'freedom'].includes(String(type)) ? 'Direct' : ['block', 'blackhole'].includes(String(type)) ? 'Block' : undefined)
          }
  }
  if (format === 'sing_box') result.push({ id: 'reject', label: 'Block', action: 'reject' })
  return result
}

/** Only provably unconditional native rules form an insertion boundary. */
export function nativeRuleInsertionIndex(format: NativeFormat, rules: unknown[]): number {
  const index = rules.findIndex(rule => {
    if (format === 'clash') return typeof rule === 'string' && /^MATCH,[^,]+$/.test(rule)
    if (!object(rule)) return false
    if (format === 'sing_box')
      return (
        Object.keys(rule).every(key => ['action', 'outbound'].includes(key)) &&
        (rule.action === 'reject' ? rule.outbound === undefined : (rule.action === undefined || rule.action === 'route') && typeof rule.outbound === 'string')
      )
    if (format === 'xray') {
      if (Object.keys(rule).some(key => !['type', 'network', 'outboundTag', 'balancerTag'].includes(key))) return false
      return (
        (rule.type === undefined || rule.type === 'field') &&
        (typeof rule.outboundTag === 'string' || typeof rule.balancerTag === 'string') &&
        typeof rule.network === 'string' &&
        rule.network.split(',').sort().join(',') === 'tcp,udp'
      )
    }
    return false
  })
  return index < 0 ? rules.length : index
}

/** Reference guard covers native DNS policies and dial/domain resolvers. */
export function referencedDNSServerTags(data: NativeObject): Set<string> {
  const tags = new Set<string>()
  const add = (value: unknown) => {
    if (typeof value === 'string' && value) tags.add(value)
    else if (object(value) && typeof value.server === 'string') tags.add(value.server)
  }
  if (object(data.dns)) {
    add(data.dns.final)
    const rules = (value: unknown) => {
      if (Array.isArray(value)) value.forEach(rules)
      else if (object(value)) {
        add(value.server)
        Object.values(value).forEach(rules)
      }
    }
    rules(data.dns.rules)
  }
  const walk = (value: unknown) => {
    if (Array.isArray(value)) value.forEach(walk)
    else if (object(value))
      for (const [key, child] of Object.entries(value)) {
        if (key === 'domain_resolver' || key === 'default_domain_resolver') add(child)
        walk(child)
      }
  }
  walk(data)
  return tags
}

export function splitEntries(text: string): string[] {
  return text
    .split(/[\s,;]+/)
    .map(value => value.trim())
    .filter(Boolean)
}
export function validIP(value: string): boolean {
  const [address, prefix, extra] = value.split('/')
  if (extra !== undefined || !address || (prefix !== undefined && !/^\d+$/.test(prefix))) return false
  const ipv4 = (ip: string) => /^(?:\d{1,3}\.){3}\d{1,3}$/.test(ip) && ip.split('.').every(part => Number(part) <= 255 && (part === '0' || !part.startsWith('0')))
  if (ipv4(address)) return prefix === undefined || Number(prefix) <= 32
  if (!address.includes(':') || !/^[\da-fA-F:.]+$/.test(address)) return false
  const chunks = address.split('::')
  if (chunks.length > 2 || address.includes(':::')) return false
  const groups = address.split(':').filter(Boolean)
  let count = 0
  for (let index = 0; index < groups.length; index++) {
    const group = groups[index]
    if (group.includes('.')) {
      if (index !== groups.length - 1 || !ipv4(group)) return false
      count += 2
    } else {
      if (!/^[\da-fA-F]{1,4}$/.test(group)) return false
      count++
    }
  }
  if (chunks.length === 1 && (address.startsWith(':') || address.endsWith(':'))) return false
  return (chunks.length === 2 ? count < 8 : count === 8) && (prefix === undefined || Number(prefix) <= 128)
}
export function validDomain(value: string): boolean {
  if (!value || value.length > 253 || /[\s\\/:*?#@,;%]/.test(value)) return false
  try {
    const host = new URL(`https://${value}`).hostname
    return host.split('.').every(label => /^[a-z\d](?:[a-z\d-]{0,61}[a-z\d])?$/i.test(label))
  } catch {
    return false
  }
}
export function validDNS(value: string, format?: NativeFormat): boolean {
  if (['localhost', 'local', 'system'].includes(value) || (validIP(value) && !value.includes('/'))) return true
  if (!/^[a-z][a-z+\d.-]*:\/\/[^/\s]/i.test(value) || /[\s\\]/.test(value)) return false
  try {
    const url = new URL(value)
    return (
      ['https:', 'https+local:', 'tls:', 'tcp:', 'udp:', 'quic:', 'h3:'].includes(url.protocol) &&
      !!url.hostname &&
      !url.username &&
      !url.password &&
      (!url.hash || format === 'clash') &&
      (validDomain(url.hostname) || validIP(url.hostname.replace(/^\[|\]$/g, ''))) &&
      (url.port === '' || Number(url.port) > 0)
    )
  } catch {
    return false
  }
}
export function makeClientConfiguration(format: NativeFormat): string {
  if (format === 'happ')
    return JSON.stringify(
      {
        Name: 'Happ routing',
        GlobalProxy: 'true',
        RemoteDNSType: 'DoH',
        RemoteDNSDomain: 'https://cloudflare-dns.com/dns-query',
        RemoteDNSIP: '1.1.1.1',
        DomesticDNSType: 'DoH',
        DomesticDNSDomain: 'https://dns.google/dns-query',
        DomesticDNSIP: '8.8.8.8',
        DirectSites: [],
        DirectIp: [],
        ProxySites: [],
        ProxyIp: [],
        BlockSites: [],
        BlockIp: [],
      },
      null,
      2,
    )
  const source = DEFAULT_TEMPLATE_CONTENT[format === 'xray' ? 'xray_subscription' : format === 'sing_box' ? 'singbox_subscription' : 'clash_subscription']
  if (format === 'clash') return source
  const fresh = JSON.parse(source) as NativeObject
  if (format === 'xray' && Array.isArray(fresh.inbounds)) for (const inbound of fresh.inbounds) if (object(inbound)) inbound.listen = '127.0.0.1'
  if (format === 'sing_box' && object(fresh.route)) {
    delete fresh.route.override_android_vpn
    const servers = object(fresh.dns) && Array.isArray(fresh.dns.servers) ? fresh.dns.servers : []
    const local = servers.find(server => object(server) && server.type === 'local' && typeof server.tag === 'string')
    if (object(local)) fresh.route.default_domain_resolver = local.tag
  }
  return JSON.stringify(fresh, null, 2)
}
