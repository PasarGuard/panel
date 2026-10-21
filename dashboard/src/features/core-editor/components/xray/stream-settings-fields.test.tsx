import { test } from 'node:test'
import assert from 'node:assert/strict'
import { renderToStaticMarkup } from 'react-dom/server'

import { MasqueSettingsFields } from '@/features/core-editor/components/xray/masque-settings-fields'
import type { StreamFormT } from '@/features/core-editor/components/xray/stream-form-inputs'
import { XdriveSettingsFields } from '@/features/core-editor/components/xray/xdrive-settings-fields'
import type { StreamFieldIssue } from '@/features/core-editor/kit/stream-form-fields'

// Radix `SelectValue` renders no text on the server, so these tests assert labels and input values only.
const t: StreamFormT = (key, options) => (typeof options?.defaultValue === 'string' ? options.defaultValue : key)
const noop = () => {}

const issue = (field: string, message: string, severity: StreamFieldIssue['severity'] = 'error'): StreamFieldIssue => ({ field, severity, code: 'XCK_SEMANTIC_MASQUE_TEST', message })

test('XDrive fields follow the service', () => {
  const gd = renderToStaticMarkup(
    <XdriveSettingsFields value={{ service: 'Google Drive', remoteFolder: 'xd', secrets: ['a', 'b', 'c'] }} onChange={noop} issues={[]} onInvalidInputsChange={noop} t={t} />,
  )
  for (const want of ['Storage service', 'Folder ID', 'Client ID', 'Client secret', 'Refresh token', 'Segment size (bytes)', 'placeholder="524288"', 'value="xd"']) assert.ok(gd.includes(want), want)
  assert.ok(!gd.includes('Template (JSON object)'))
  const tpl = renderToStaticMarkup(<XdriveSettingsFields value={{ service: 'template', template: { auth: { type: 'basic' } } }} onChange={noop} issues={[]} onInvalidInputsChange={noop} t={t} />)
  assert.ok(tpl.includes('Template (JSON object)'))
  assert.ok(!tpl.includes('Client ID'))
  const local = renderToStaticMarkup(
    <XdriveSettingsFields
      value={{ service: 'local', remoteFolder: '/srv/xd' }}
      onChange={noop}
      issues={[{ field: 'remoteFolder', severity: 'error', code: 'XCK_SEMANTIC_XDRIVE_REMOTE_FOLDER_REQUIRED', message: 'Folder message for test' }]}
      onInvalidInputsChange={noop}
      t={t}
    />,
  )
  assert.ok(local.includes('Folder path'))
  assert.ok(!local.includes('Client ID'))
  assert.ok(local.includes('Folder message for test'))
})

test('XDrive: the google-drive spelling is the Google Drive service; other issues land at the bottom', () => {
  const html = renderToStaticMarkup(
    <XdriveSettingsFields
      value={{ service: 'google-drive', remoteFolder: 'xd', secrets: ['id', 'secret', 'token'], segmentBytes: 1048576 }}
      onChange={noop}
      issues={[issue('secrets', 'Secrets message for test'), issue('mux', 'Mux message for test'), issue('segmentBytes', 'Cap message for test', 'warning')]}
      onInvalidInputsChange={noop}
      t={t}
    />,
  )
  for (const want of ['Folder ID', 'Client ID', 'value="id"', 'value="1048576"', 'Secrets message for test', 'Cap message for test', 'Mux message for test']) assert.ok(html.includes(want), want)
  assert.ok(html.indexOf('Mux message for test') > html.indexOf('Hole timeout (ms)'), 'the mux issue is listed after the last field')
  assert.ok(html.indexOf('Cap message for test') < html.indexOf('Flush interval (ms)'), 'the cap warning sits under its field')
})

test('MASQUE server variant', () => {
  const html = renderToStaticMarkup(
    <MasqueSettingsFields
      side="server"
      settings={{ address: ['10.14.0.1/16', 'fd14::1/64'], mtu: 1400, remoteDNS: ['1.1.1.1'] }}
      onSettingsChange={noop}
      transport={{ type: 'masque', path: '/masque' }}
      onTransportChange={noop}
      alpn={['h3', 'h2']}
      onAlpnChange={noop}
      issues={[]}
      onInvalidInputsChange={noop}
      t={t}
    />,
  )
  for (const want of ['Server address pool', '10.14.0.1/16, fd14::1/64', 'Client DNS', 'HTTP version', 'value="1400"', 'value="/masque"']) assert.ok(html.includes(want), want)
  for (const bad of ['Authentication', 'WARP private key', 'Server port', 'XMUX (JSON object)', 'Remove client-only settings']) assert.ok(!html.includes(bad), bad)
})

test('MASQUE server variant: the HTTP version select is disabled with a hint while security is not TLS', () => {
  const render = (onAlpnChange: ((alpn: string[]) => void) | null) =>
    renderToStaticMarkup(
      <MasqueSettingsFields
        side="server"
        settings={{ address: ['10.14.0.1/16'] }}
        onSettingsChange={noop}
        transport={{ type: 'masque' }}
        onTransportChange={noop}
        alpn={undefined}
        onAlpnChange={onAlpnChange}
        issues={[]}
        onInvalidInputsChange={noop}
        t={t}
      />,
    )
  const hint = 'Set Security to TLS to choose the HTTP version.'
  const locked = render(null)
  assert.ok(locked.includes(hint))
  assert.ok(locked.includes('data-disabled=""'), 'the select trigger is disabled')
  const open = render(noop)
  assert.ok(!open.includes(hint))
  assert.ok(!open.includes('data-disabled=""'))
})

test('MASQUE server variant: client-only keys show their issues with a remove action', () => {
  const html = renderToStaticMarkup(
    <MasqueSettingsFields
      side="server"
      settings={{ address: ['10.14.0.1/16'] }}
      onSettingsChange={noop}
      transport={{ type: 'masque', user: 'a:b', xmux: { maxConcurrency: '16-32' } }}
      onTransportChange={noop}
      alpn={['h3']}
      onAlpnChange={noop}
      issues={[issue('user', 'User message for test'), issue('xmux', 'Xmux message for test', 'warning'), issue('security', 'Security message for test')]}
      onInvalidInputsChange={noop}
      t={t}
    />,
  )
  for (const want of ['Remove client-only settings', 'User message for test', 'Xmux message for test', 'Security message for test']) assert.ok(html.includes(want), want)
  for (const bad of ['Authentication', 'value="a:b"', 'XMUX (JSON object)']) assert.ok(!html.includes(bad), bad)
  assert.ok(html.indexOf('Security message for test') > html.indexOf('Remove client-only settings'), 'other issues are listed at the bottom')
})

test('MASQUE client variant with WARP', () => {
  const html = renderToStaticMarkup(
    <MasqueSettingsFields
      side="client"
      settings={{ address: '162.159.198.1', port: 443 }}
      onSettingsChange={noop}
      transport={{ warp: { privateKey: 'k', publicKey: 'p', address: ['172.16.0.2/32'] } }}
      onTransportChange={noop}
      alpn={undefined}
      onAlpnChange={noop}
      issues={[]}
      onInvalidInputsChange={noop}
      t={t}
    />,
  )
  for (const want of ['Server address', 'Server port', 'value="443"', 'Authentication', 'WARP private key', 'WARP public key', '172.16.0.2/32', 'cloudflareaccess.com'])
    assert.ok(html.includes(want), want)
  for (const bad of ['Client DNS', 'Server address pool']) assert.ok(!html.includes(bad), bad)
})

test('MASQUE client variant: Basic auth, xmux, and issues of hidden fields at the bottom', () => {
  const html = renderToStaticMarkup(
    <MasqueSettingsFields
      side="client"
      settings={{ address: 'example.com', port: 443, remoteDNS: ['9.9.9.9'] }}
      onSettingsChange={noop}
      transport={{ user: 'alice', pass: 'secret', xmux: { maxConcurrency: '16-32' } }}
      onTransportChange={noop}
      alpn={['h2']}
      onAlpnChange={noop}
      issues={[issue('warp', 'Warp message for test'), issue('user', 'User message for test'), issue('transport', 'Transport message for test'), issue('mux', 'Mux message for test', 'warning')]}
      onInvalidInputsChange={noop}
      t={t}
    />,
  )
  for (const want of ['Remote DNS', '9.9.9.9', 'User', 'value="alice"', 'Password', 'XMUX (JSON object)', '16-32', 'User message for test', 'Warp message for test', 'Mux message for test'])
    assert.ok(html.includes(want), want)
  // The outbound stream accordion shows transport and security issues under its own selects.
  for (const bad of ['WARP private key', 'Transport message for test', 'Remove client-only settings']) assert.ok(!html.includes(bad), bad)
  assert.ok(html.indexOf('User message for test') < html.indexOf('Password'), 'the user issue sits under its field')
  assert.ok(html.indexOf('Warp message for test') > html.indexOf('XMUX (JSON object)'), 'the warp issue is listed at the bottom in Basic mode')
})

const occurrences = (html: string, text: string) => html.split(text).length - 1

test('MASQUE client variant: WARP with a stored user or pass shows them so the conflict can be cleared', () => {
  const warp = { privateKey: 'k', publicKey: 'p', address: ['172.16.0.2/32'] }
  const render = (transport: Record<string, unknown>) =>
    renderToStaticMarkup(
      <MasqueSettingsFields
        side="client"
        settings={{ address: '162.159.198.1', port: 443 }}
        onSettingsChange={noop}
        transport={transport}
        onTransportChange={noop}
        alpn={undefined}
        onAlpnChange={noop}
        issues={[issue('warp', 'Conflict message for test'), issue('user', 'User message for test')]}
        onInvalidInputsChange={noop}
        t={t}
      />,
    )
  const stale = render({ warp, user: 'a:b', pass: 'secret' })
  for (const want of ['WARP private key', 'value="a:b"', 'Password', 'value="secret"', 'Conflict message for test']) assert.ok(stale.includes(want), want)
  assert.equal(occurrences(stale, 'User message for test'), 1, 'the user issue is shown once')
  assert.ok(stale.indexOf('User message for test') < stale.indexOf('Password'), 'the user issue sits under its field')
  const clean = render({ warp })
  for (const bad of ['Password', 'value="a:b"']) assert.ok(!clean.includes(bad), bad)
  // Without a user input the user issue is listed once, at the bottom.
  assert.equal(occurrences(clean, 'User message for test'), 1)
  assert.ok(clean.indexOf('User message for test') > clean.indexOf('XMUX (JSON object)'))
})

test('XDrive: fields shown elsewhere are not repeated', () => {
  const render = (shownElsewhere?: readonly string[]) =>
    renderToStaticMarkup(
      <XdriveSettingsFields
        value={{ service: 'local', remoteFolder: '/srv/xd' }}
        onChange={noop}
        issues={[issue('transport', 'Protocol message for test'), issue('security', 'Security message for test'), issue('mux', 'Mux message for test')]}
        onInvalidInputsChange={noop}
        t={t}
        shownElsewhere={shownElsewhere}
      />,
    )
  const inbound = render()
  for (const want of ['Protocol message for test', 'Security message for test', 'Mux message for test']) assert.equal(occurrences(inbound, want), 1, want)
  const outbound = render(['transport', 'security'])
  for (const bad of ['Protocol message for test', 'Security message for test']) assert.ok(!outbound.includes(bad), bad)
  assert.equal(occurrences(outbound, 'Mux message for test'), 1)
})
