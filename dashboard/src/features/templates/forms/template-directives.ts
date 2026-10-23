import type { ClientTemplateType } from '@/service/api'

// `pasarguard` directive in client templates (see app/subscription/template_directives.py).
export const SERVER_GROUP_TEMPLATE_TYPES: readonly ClientTemplateType[] = ['xray_subscription', 'singbox_subscription', 'clash_subscription']

export const supportsServerGroups = (templateType: string) => (SERVER_GROUP_TEMPLATE_TYPES as readonly string[]).includes(templateType)

// Cheap check for list badges: a `pasarguard` key in JSON (`"pasarguard":`) or YAML (`pasarguard:`).
export const hasServerGroupDirective = (content: string | null | undefined) => /(^|[\s{,"'])pasarguard["']?\s*:/m.test(content ?? '')

// What "Insert example" adds to an Xray template: every server of the user as extra outbounds proxy-1, proxy-2, …
// per_host keeps the template's own `proxy` outbound, so an existing config keeps working.
export const XRAY_SERVER_GROUP_DIRECTIVE = { mode: 'per_host', inject: [{ select: {}, tag_prefix: 'proxy' }] }

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
