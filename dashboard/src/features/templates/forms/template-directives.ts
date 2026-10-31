import type { ClientTemplateType } from '@/service/api'

// `pasarguard` directive in client templates (see app/subscription/template_directives.py).
export const SERVER_GROUP_TEMPLATE_TYPES: readonly ClientTemplateType[] = ['xray_subscription', 'singbox_subscription', 'clash_subscription']

export const supportsServerGroups = (templateType: string) => (SERVER_GROUP_TEMPLATE_TYPES as readonly string[]).includes(templateType)

// Cheap check for list badges: a `pasarguard` key in JSON (`"pasarguard":`) or YAML (`pasarguard:`, also as a list item).
// Comments and string values that merely contain the word do not count.
export const hasServerGroupDirective = (content: string | null | undefined) =>
  /"pasarguard"\s*:|^[ \t]*(?:-[ \t]+)?pasarguard[ \t]*:|[{,][ \t]*pasarguard[ \t]*:/m.test(content ?? '')

// What "Insert example" adds to an Xray template: one config with every server of the user as proxy-1, proxy-2, …
// "single" keeps the config small; "per_host" with an empty select would copy all servers into every config.
export const XRAY_SERVER_GROUP_DIRECTIVE = { mode: 'single', inject: [{ select: {}, tag_prefix: 'proxy' }] }

// True for an Xray template whose per-host configs each get all of the user's servers (n configs x n outbounds).
export const xrayDirectiveCopiesAllServersPerHost = (content: string): boolean => {
  let parsed: any
  try {
    parsed = JSON.parse(content)
  } catch {
    return false
  }
  const directive = parsed && typeof parsed === 'object' ? parsed.pasarguard : undefined
  if (!directive || typeof directive !== 'object' || (directive.mode ?? 'per_host') !== 'per_host' || !Array.isArray(directive.inject)) {
    return false
  }
  return directive.inject.some((inject: any) => {
    const select = inject && typeof inject === 'object' ? inject.select : undefined
    return select === undefined || select === null || (typeof select === 'object' && Object.keys(select).length === 0)
  })
}

// Puts `example` on lines of its own at the cursor (`offset`), so it never glues to the text around it:
// at the start of a line it goes before that line, otherwise after the end of the current line.
export const insertExampleOnOwnLine = (content: string, offset: number, example: string): string => {
  const cursor = Math.min(Math.max(offset, 0), content.length)
  if (cursor === 0 || content[cursor - 1] === '\n') {
    return `${content.slice(0, cursor)}${example}\n${content.slice(cursor)}`
  }
  const lineEnd = content.indexOf('\n', cursor)
  if (lineEnd === -1) {
    return `${content}\n${example}\n`
  }
  return `${content.slice(0, lineEnd)}\n${example}${content.slice(lineEnd)}`
}

export const SERVER_GROUP_EXAMPLES: Record<'xray_subscription' | 'singbox_subscription' | 'clash_subscription', string> = {
  xray_subscription: `{
  "remarks": "PasarGuard",
  "log": {"loglevel": "warning"},
  "inbounds": [{"tag": "socks", "listen": "127.0.0.1", "port": 10808, "protocol": "socks", "settings": {"udp": true}}],
  "outbounds": [
    {"tag": "direct", "protocol": "freedom"},
    {"tag": "block", "protocol": "blackhole"}
  ],
  "burstObservatory": {
    "subjectSelector": ["proxy-"],
    "pingConfig": {"destination": "https://www.gstatic.com/generate_204", "interval": "1m", "timeout": "5s", "sampling": 2}
  },
  "routing": {
    "domainStrategy": "IPIfNonMatch",
    "balancers": [{"tag": "auto", "selector": ["proxy-"], "strategy": {"type": "leastPing"}}],
    "rules": [
      {"type": "field", "ip": ["geoip:private"], "outboundTag": "direct"},
      {"type": "field", "network": "tcp,udp", "balancerTag": "auto"}
    ]
  },
  "pasarguard": {"mode": "single", "inject": [{"select": {}, "tag_prefix": "proxy"}]}
}`,
  singbox_subscription: `"outbounds": [
  {"type": "selector", "tag": "proxy", "outbounds": ["auto-reality", "auto-ws"], "pasarguard": {"include_proxies": true}},
  {"type": "urltest", "tag": "auto-reality", "outbounds": [], "url": "https://www.gstatic.com/generate_204", "interval": "3m",
   "pasarguard": {"select": {"inbound_tags": ["VLESS TCP REALITY"]}}},
  {"type": "urltest", "tag": "auto-ws", "outbounds": [], "pasarguard": {"select": {"inbound_tag_regex": "WS"}}},
  {"type": "direct", "tag": "direct"}
]`,
  clash_subscription: `proxy-groups:
- name: PROXY
  type: select
  proxies: [Germany, Fastest]
  pasarguard: {include-proxies: true}
- name: Germany
  type: url-test
  url: https://www.gstatic.com/generate_204
  interval: 300
  proxies: []
  pasarguard:
    include-proxies: true
    select:
      remark_regex: "(?i)^(DE|🇩🇪)"`,
}

export type XrayDirectiveMergeResult = { status: 'merged'; content: string } | { status: 'exists' } | { status: 'invalid' }

// Adds the top-level `pasarguard` key to an Xray JSON template. Never overwrites an existing directive.
export const mergeXrayServerGroupDirective = (content: string): XrayDirectiveMergeResult => {
  let parsed: unknown
  try {
    parsed = JSON.parse(content)
  } catch {
    return { status: 'invalid' }
  }
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    return { status: 'invalid' }
  }
  if ('pasarguard' in parsed) {
    return { status: 'exists' }
  }
  return { status: 'merged', content: JSON.stringify({ ...parsed, pasarguard: XRAY_SERVER_GROUP_DIRECTIVE }, null, 2) }
}
