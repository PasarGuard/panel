import { describe, expect, it } from 'bun:test'

import { buildHappRoutingLink, HAPP_ROUTING_LINK_PREFIX } from './happ-routing'

const decode = (link: string) => {
  const binary = atob(link.slice(HAPP_ROUTING_LINK_PREFIX.length))
  return new TextDecoder().decode(Uint8Array.from(binary, char => char.charCodeAt(0)))
}

describe('buildHappRoutingLink', () => {
  it('encodes compact UTF-8 JSON as standard base64', () => {
    const link = buildHappRoutingLink('{\n  "Name": "Профиль",\n  "DirectIp": ["10.0.0.0/8"]\n}')
    expect(link).not.toBeNull()
    expect(link!.startsWith(HAPP_ROUTING_LINK_PREFIX)).toBe(true)
    expect(decode(link!)).toBe('{"Name":"Профиль","DirectIp":["10.0.0.0/8"]}')
  })

  it('matches the backend literal for non-ASCII content', () => {
    // Same literal as test_build_happ_routing_link_is_compact_utf8_json_in_standard_base64 in
    // tests/api/test_happ_routing.py (standard Base64: it has "/" and "+")
    expect(buildHappRoutingLink('{\n  "Name": "Профиль",\n  "DirectIp": ["10.0.0.0/8"]\n}')).toBe(
      'happ://routing/onadd/eyJOYW1lIjoi0J/RgNC+0YTQuNC70YwiLCJEaXJlY3RJcCI6WyIxMC4wLjAuMC84Il19',
    )
  })

  it('matches the backend encoding for ASCII content', () => {
    // base64.b64encode(json.dumps({"Name": "a"}, separators=(",", ":")).encode())
    expect(buildHappRoutingLink('{"Name": "a"}')).toBe(`${HAPP_ROUTING_LINK_PREFIX}eyJOYW1lIjoiYSJ9`)
  })

  it('returns null for invalid JSON or non-objects', () => {
    expect(buildHappRoutingLink('{')).toBeNull()
    expect(buildHappRoutingLink('[]')).toBeNull()
    expect(buildHappRoutingLink('"x"')).toBeNull()
  })
})
