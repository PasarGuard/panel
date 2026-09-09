import { describe, expect, test } from 'bun:test'
import {
  decodeNativeRule,
  encodeNativeRule,
  makeClientConfiguration,
  nativeTargets,
  nativeRuleInsertionIndex,
  referencedDNSServerTags,
  readNativeConfiguration,
  validDNS,
  validDomain,
  validIP,
} from './native-configuration'

describe('lossless native source editing', () => {
  test('opening a JSON document does not normalize it; an explicit edit preserves unknown fields', () => {
    const source = '{"Name":"Original", "custom": {"n":1}, "DirectSites":["geosite:private"],"GlobalProxy":true}'
    const doc = readNativeConfiguration('happ', source, 'routing')
    expect(doc.data.Name).toBe('Original')
    const next = doc.set(['DirectSites'], ['domain:example.com'])
    expect(JSON.parse(next)).toEqual({ Name: 'Original', custom: { n: 1 }, DirectSites: ['domain:example.com'], GlobalProxy: true })
    expect(next).toContain('"custom": {"n":1}')
  })
  test('complex native rules stay complex rather than losing match conditions', () => {
    expect(decodeNativeRule('xray', { type: 'field', domain: ['domain:example.com'], port: '443', outboundTag: 'custom' })).toBeNull()
    expect(decodeNativeRule('xray', { type: 'field', domain: ['keyword:video'], outboundTag: 'custom' })).toBeNull()
    expect(decodeNativeRule('sing_box', { domain: ['example.com'], action: 'reject', method: 'drop' })).toBeNull()
    expect(decodeNativeRule('clash', 'IP-CIDR,10.0.0.0/8,DIRECT,no-resolve')).toBeNull()
  })
  test('native target IDs and generated Xray proxy remain exact', () => {
    const data = {
      outbounds: [
        { tag: 'custom-direct', protocol: 'freedom' },
        { tag: 'deny', protocol: 'blackhole' },
      ],
      routing: { rules: [{ domain: ['full:example.com'], outboundTag: 'retired-id' }] },
    }
    expect(nativeTargets('xray', data)).toEqual([
      { id: 'proxy', label: 'Proxy' },
      { id: 'custom-direct', label: 'Direct' },
      { id: 'deny', label: 'Block' },
    ])
    expect(encodeNativeRule('xray', { kind: 'suffix', values: ['example.com'], target: 'custom-direct' })).toEqual([{ type: 'field', domain: ['domain:example.com'], outboundTag: 'custom-direct' }])
  })
  test('sing-box block is an action distinct from a real outbound named reject', () => {
    const targets = nativeTargets('sing_box', { outbounds: [{ type: 'direct', tag: 'reject' }] })
    expect(targets).toEqual([
      { id: 'reject', label: 'Direct' },
      { id: 'reject', label: 'Block', action: 'reject' },
    ])
    const rule = { domain: ['example.com'], action: 'reject' }
    const decoded = decodeNativeRule('sing_box', rule)!
    expect(encodeNativeRule('sing_box', decoded)).toEqual([rule])
    expect(encodeNativeRule('sing_box', { kind: 'domain', values: ['example.com'], target: 'reject' })).toEqual([{ domain: ['example.com'], outbound: 'reject' }])
  })
  test('missing existing targets never become destinations for new rules', () => {
    const data = { rules: ['DOMAIN,one.example,Missing', 'MATCH,Missing', 'IP-CIDR,10.0.0.0/8,Missing,no-resolve'] }
    expect(nativeTargets('clash', data)).toEqual([
      { id: 'DIRECT', label: 'Direct' },
      { id: 'REJECT', label: 'Block' },
    ])
    expect(data.rules).toHaveLength(3)
  })
  test('new rules go before only recognised unconditional terminal rules', () => {
    expect(nativeRuleInsertionIndex('clash', ['DOMAIN,one.example,DIRECT', 'MATCH,PROXY'])).toBe(1)
    expect(
      nativeRuleInsertionIndex('xray', [
        { type: 'field', domain: ['full:a.example'], outboundTag: 'direct' },
        { type: 'field', network: 'tcp,udp', outboundTag: 'proxy' },
      ]),
    ).toBe(1)
    expect(nativeRuleInsertionIndex('xray', [{ type: 'field', network: 'tcp', outboundTag: 'proxy' }])).toBe(1)
    expect(nativeRuleInsertionIndex('sing_box', [{ protocol: 'dns', action: 'hijack-dns' }, { outbound: 'proxy' }])).toBe(1)
    expect(nativeRuleInsertionIndex('sing_box', [{ domain: ['one.example'], action: 'reject' }, { action: 'reject' }])).toBe(1)
  })
  test('all supported native DNS references lock server IDs', () => {
    const data = {
      dns: { final: 'final', rules: [{ type: 'logical', rules: [{ server: 'nested' }] }] },
      route: { default_domain_resolver: { server: 'default' } },
      outbounds: [{ domain_resolver: 'dial' }, { domain_resolver: { server: 'dial-object' } }],
    }
    expect([...referencedDNSServerTags(data)].sort()).toEqual(['default', 'dial', 'dial-object', 'final', 'nested'])
  })
  test('new native defaults use local listeners and a present bootstrap resolver', () => {
    const xray = JSON.parse(makeClientConfiguration('xray'))
    expect(xray.inbounds.every((inbound: { listen: string }) => inbound.listen === '127.0.0.1')).toBe(true)
    const singbox = JSON.parse(makeClientConfiguration('sing_box'))
    expect(singbox.route.override_android_vpn).toBeUndefined()
    expect(singbox.route.default_domain_resolver).toBe('dns-local')
    expect(singbox.dns.servers.find((server: { tag: string }) => server.tag === singbox.route.default_domain_resolver).type).toBe('local')
    const existing = '{"route":{"override_android_vpn":true},"inbounds":[{"listen":"0.0.0.0"}]}'
    expect(readNativeConfiguration('sing_box', existing, 'routing').data.route).toEqual({ override_android_vpn: true })
  })
  test('Clash block DNS list replacement preserves newline, comments, and following fields', () => {
    const source = 'dns:\n  nameserver:\n    - 1.1.1.1 # primary\n    - 8.8.8.8 # secondary\n  enable: true # enabled\nrules: []\n'
    const next = readNativeConfiguration('clash', source, 'dns').list(['dns', 'nameserver'], ['9.9.9.9', '8.8.8.8'])
    expect(next).toBe(source.replace('1.1.1.1', '"9.9.9.9"'))
    expect(readNativeConfiguration('clash', next, 'dns').data.dns).toEqual({ nameserver: ['9.9.9.9', '8.8.8.8'], enable: true })
    const empty = readNativeConfiguration('clash', source, 'dns').list(['dns', 'nameserver'], [])
    expect(readNativeConfiguration('clash', empty, 'dns').data.dns).toEqual({ nameserver: [], enable: true })
    expect(empty).toContain('  enable: true # enabled\n')
  })
  test('Clash static rules can be edited with Jinja elsewhere byte-for-byte preserved', () => {
    const before = '# header\nproxies:\n{% for proxy in proxies %}\n  - {{ proxy }}\n{% endfor %}\n'
    const after = 'dns:\n  enable: true # retained\n  nameserver: [1.1.1.1]\n'
    const source = before + 'rules:\n  - DOMAIN,old.example,DIRECT # local rule\n  - MATCH,Proxy # terminal\n' + after
    const doc = readNativeConfiguration('clash', source, 'routing')
    const next = doc.list(['rules'], ['DOMAIN,new.example,DIRECT', 'MATCH,Proxy'], [null, 1])
    expect(next.startsWith(before)).toBe(true)
    expect(next.endsWith(after)).toBe(true)
    expect(next).toContain('  - MATCH,Proxy # terminal\n')
    expect(readNativeConfiguration('clash', next, 'routing').data.rules).toEqual(['DOMAIN,new.example,DIRECT', 'MATCH,Proxy'])
  })
  test('Clash reorder preserves original quoting and comments on untouched rows', () => {
    const source = 'rules:\n  - "DOMAIN,one.example,DIRECT" # first\n  - MATCH,Proxy # fallback\n'
    const next = readNativeConfiguration('clash', source, 'routing').list(['rules'], ['MATCH,Proxy', 'DOMAIN,one.example,DIRECT'], [1, 0])
    expect(next).toBe('rules:\n  - MATCH,Proxy # fallback\n  - "DOMAIN,one.example,DIRECT" # first\n')
  })
  test('editing one Clash row retains its inline comment', () => {
    const source = 'rules:\n  - DOMAIN,one.example,DIRECT # first\n  - MATCH,Proxy # fallback\n'
    const next = readNativeConfiguration('clash', source, 'routing').list(['rules'], ['DOMAIN,two.example,DIRECT', 'MATCH,Proxy'], [0, 1])
    expect(next).toBe('rules:\n  - "DOMAIN,two.example,DIRECT" # first\n  - MATCH,Proxy # fallback\n')
  })
  test('existing full Clash template provides static group IDs despite Jinja members', () => {
    const source = makeClientConfiguration('clash')
    const doc = readNativeConfiguration('clash', source, 'routing')
    expect(nativeTargets('clash', doc.data).map(item => item.id)).toEqual(['DIRECT', 'REJECT', 'PROXY', 'Fastest'])
    expect(makeClientConfiguration('xray')).toContain('inbounds')
    expect(JSON.parse(makeClientConfiguration('happ')).Name).toBe('Happ routing')
  })
  test('Clash DNS edit preserves other keys and comments without rewriting the template', () => {
    const source = 'proxies:\n  - {{ proxy }}\ndns:\n  enable: true # toggle\n  nameserver: [1.1.1.1] # resolver\n  nameserver-policy:\n    "+.ru": 77.88.8.8 # special\nrules: []\n'
    const next = readNativeConfiguration('clash', source, 'dns').set(['dns', 'nameserver'], ['https://dns.google/dns-query'])
    expect(next).toBe(source.replace('[1.1.1.1]', '["https://dns.google/dns-query"]'))
  })
  test('Jinja within section and conditional section reject visual mutation', () => {
    expect(() => readNativeConfiguration('clash', 'rules:\n{% for rule in rules %}\n - {{ rule }}\n{% endfor %}\n', 'routing')).toThrow('templatedSection')
    expect(() => readNativeConfiguration('clash', '{% if enabled %}\nrules: []\n{% endif %}\n', 'routing')).toThrow('templatedSection')
  })
  test('malformed JSON, duplicate keys, and duplicate YAML sections are rejected', () => {
    expect(() => readNativeConfiguration('happ', '{', 'routing')).toThrow()
    expect(() => readNativeConfiguration('happ', '{"Name":"a","Name":"b"}', 'routing')).toThrow('duplicateSection')
    expect(() => readNativeConfiguration('clash', 'rules: []\nrules: []\n', 'routing')).toThrow('duplicateSection')
    expect(() => readNativeConfiguration('clash', 'rules: [oops\n', 'routing')).toThrow('invalidYaml')
    expect(() => readNativeConfiguration('clash', '"rules": []\n', 'routing')).toThrow('unsupportedShape')
    expect(() => readNativeConfiguration('clash', '{rules: []}', 'routing')).toThrow('unsupportedShape')
  })
  test('absent and empty YAML sections can be populated without replacing the file', () => {
    for (const source of ['# keep\n', '# keep\ndns: {}\n', '# keep\ndns:\n  enable: true\n']) {
      const next = readNativeConfiguration('clash', source, 'dns').set(['dns', 'nameserver'], ['1.1.1.1'])
      expect(next.startsWith('# keep\n')).toBe(true)
      expect(readNativeConfiguration('clash', next, 'dns').data.dns).toMatchObject({ nameserver: ['1.1.1.1'] })
    }
  })
  test('removing the last block rule leaves valid YAML and other sections intact', () => {
    const source = 'rules:\n  - MATCH,PROXY # last\ndns:\n  enable: true\n'
    const next = readNativeConfiguration('clash', source, 'routing').list(['rules'], [], [])
    expect(readNativeConfiguration('clash', next, 'routing').data.rules).toEqual([])
    expect(next.endsWith('dns:\n  enable: true\n')).toBe(true)
  })
})
describe('native input validation', () => {
  test('accepts valid IPv4 and IPv6 CIDRs', () => {
    for (const value of ['0.0.0.0/0', '192.168.1.1/32', '2001:db8::/32', '::1', '::/0', '::ffff:192.0.2.1/128']) expect(validIP(value)).toBe(true)
  })
  test('rejects malformed addresses and incorrect CIDR widths', () => {
    for (const value of ['999.1.1.1', '1.2.3.4/33', '1.2.3.4/-1', '1.2.3.4/', '2001:::1', '1:2:3:4:5:6:7:8:9', '2001:db8::/129', ':1:2:3:4:5:6:7', '::ffff:999.1.1.1'])
      expect(validIP(value)).toBe(false)
  })
  test('validates DNS protocols and URL syntax', () => {
    for (const value of ['1.1.1.1', '::1', 'https://dns.google/dns-query', 'tls://dns.google:853', 'udp://[2001:db8::1]:53']) expect(validDNS(value)).toBe(true)
    for (const value of ['https://', 'https:///dns-query', 'https://dns.google:99999', 'ftp://dns.google', 'https://user:secret@dns.google', '999.1.1.1', '1.1.1.1/24'])
      expect(validDNS(value)).toBe(false)
    expect(validDNS('https://1.1.1.1/dns-query#PROXY', 'clash')).toBe(true)
    expect(validDNS('https://1.1.1.1/dns-query#PROXY', 'xray')).toBe(false)
    expect(validDomain('пример.рф')).toBe(true)
    expect(validDomain('bad..example')).toBe(false)
  })
})
