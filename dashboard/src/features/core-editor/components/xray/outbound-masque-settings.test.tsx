import { test } from 'node:test'
import assert from 'node:assert/strict'
import { renderToStaticMarkup } from 'react-dom/server'
import type { Outbound } from '@pasarguard/xray-config-kit'
import type { TFunction } from 'i18next'

import { OutboundSpecialProtocolSettings } from '@/features/core-editor/components/xray/outbound-special-protocol-settings'
import { streamFieldIssuesForOutbound } from '@/features/core-editor/kit/stream-form-fields'

// Radix `SelectValue` renders no text on the server, so these tests assert labels, input values and messages only.
const t = ((key: string, options?: Record<string, unknown>) => (typeof options?.defaultValue === 'string' ? options.defaultValue : key)) as unknown as TFunction
const noop = () => {}

function masqueOutbound(streamSettings: Record<string, unknown>, extra: Record<string, unknown> = {}): Outbound {
  return { protocol: 'masque', tag: 'warp-out', settings: { address: 'engage.cloudflareclient.com', port: 443 }, streamSettings, ...extra } as unknown as Outbound
}

// The dialog computes the issues once and passes them down.
const render = (ob: Outbound) =>
  renderToStaticMarkup(<OutboundSpecialProtocolSettings ob={ob} patchOutbound={noop} t={t} streamIssues={streamFieldIssuesForOutbound(ob)} onInvalidInputsChange={noop} />)

const count = (html: string, text: string) => html.split(text).length - 1

test('MASQUE outbound: the client box edits the server and the masque transport, with the kit issues inline', () => {
  const html = render(masqueOutbound({ network: 'masque', security: 'tls', masqueSettings: { user: 'a:b', pass: 'secret' } }))
  for (const want of ['Server address', 'Server port', 'Remote DNS', 'HTTP version', 'Authentication', 'User', 'Password', 'Path', 'Host', 'Headers (JSON object)', 'XMUX (JSON object)']) {
    assert.ok(html.includes(want), want)
  }
  assert.ok(html.includes('value="engage.cloudflareclient.com"'))
  assert.ok(html.includes('value="443"'))
  assert.ok(html.includes('value="a:b"'))
  assert.equal(count(html, 'MASQUE user cannot contain'), 1)
})

test('MASQUE outbound: security and transport issues are left to the stream selects; other issues land in the box', () => {
  const html = render(masqueOutbound({ network: 'masque', security: 'none' }, { mux: { enabled: true } }))
  // Shown under the security select of the stream accordion instead.
  assert.ok(!html.includes('MASQUE requires TLS'))
  // Xray v26.10.17 accepts mux on MASQUE outbounds; the kit only warns for older releases.
  assert.equal(count(html, 'v26.10.10 and older'), 1)
})

test('MASQUE outbound: the box shows the issues the dialog passes and runs no kit check of its own', () => {
  const ob = masqueOutbound({ network: 'masque', security: 'tls', masqueSettings: { user: 'a:b' } })
  const html = renderToStaticMarkup(<OutboundSpecialProtocolSettings ob={ob} patchOutbound={noop} t={t} streamIssues={[]} onInvalidInputsChange={noop} />)
  assert.ok(html.includes('value="a:b"'))
  assert.equal(count(html, 'MASQUE user cannot contain'), 0)
})

test('outbounds of other protocols get no MASQUE box', () => {
  const html = render({ protocol: 'vless', tag: 'v', settings: {}, streamSettings: { network: 'masque', security: 'tls' } } as unknown as Outbound)
  assert.ok(!html.includes('Server port'))
})
