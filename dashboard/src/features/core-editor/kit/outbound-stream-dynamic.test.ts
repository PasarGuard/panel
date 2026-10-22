import { test } from 'node:test'
import assert from 'node:assert/strict'

import { validateOutboundDraft } from '@pasarguard/xray-config-kit'
import type { Outbound } from '@pasarguard/xray-config-kit'
import {
  applyOutboundStreamNetwork,
  getOutboundStreamNetworkSelectValues,
  getOutboundStreamSecuritySelectValues,
  outboundMuxForProtocolSwitch,
  outboundStreamNetworkCompatibleWithReality,
  outboundStreamSectionNetwork,
  outboundStreamSettingsForProtocolSwitch,
  outboundStreamTransportName,
  outboundWithStreamNetwork,
} from '@/features/core-editor/kit/outbound-stream-dynamic'

const ALL = ['tcp', 'kcp', 'ws', 'h2', 'grpc', 'xhttp', 'splithttp', 'xdrive']
// Xray v26.10.17 allows the xdrive network on VLESS outbounds only.
const NOT_VLESS = ALL.filter(network => network !== 'xdrive')

test('outbound network choices', () => {
  assert.deepEqual(getOutboundStreamNetworkSelectValues('none', 'tcp', 'vless'), ALL)
  assert.deepEqual(getOutboundStreamNetworkSelectValues('reality', 'tcp', 'vless'), ['tcp', 'grpc', 'xhttp', 'splithttp'])
  assert.deepEqual(getOutboundStreamNetworkSelectValues('reality', 'xdrive', 'vless'), ['xdrive', 'tcp', 'grpc', 'xhttp', 'splithttp'])
  assert.deepEqual(getOutboundStreamNetworkSelectValues('tls', 'masque', 'masque'), ['masque'])
  assert.deepEqual(getOutboundStreamNetworkSelectValues('tls', 'tcp', 'masque'), ['tcp', 'masque'])
  assert.deepEqual(getOutboundStreamNetworkSelectValues('tls', 'masque', 'vless'), ['masque', ...ALL])
  assert.deepEqual(getOutboundStreamNetworkSelectValues('none', 'httpupgrade', 'vless'), ['httpupgrade', ...ALL])
  assert.equal(outboundStreamNetworkCompatibleWithReality('xdrive'), false)
})

test('xdrive is offered for VLESS only, and a stored xdrive stays selectable', () => {
  assert.deepEqual(getOutboundStreamNetworkSelectValues('none', 'tcp', 'vmess'), NOT_VLESS)
  assert.deepEqual(getOutboundStreamNetworkSelectValues('tls', 'ws', 'trojan'), NOT_VLESS)
  assert.deepEqual(getOutboundStreamNetworkSelectValues('none', 'xdrive', 'shadowsocks'), ['xdrive', ...NOT_VLESS])
  // Without a protocol (the two-argument form) xdrive is not offered either.
  assert.deepEqual(getOutboundStreamNetworkSelectValues('none', 'httpupgrade'), ['httpupgrade', ...NOT_VLESS])
  assert.deepEqual(getOutboundStreamNetworkSelectValues('none', ' XDrive ', 'vless'), ALL)
  assert.deepEqual(getOutboundStreamNetworkSelectValues('none', '', 'vless'), ALL)
})

test('outbound security choices', () => {
  assert.deepEqual(getOutboundStreamSecuritySelectValues('masque', 'tls'), ['tls'])
  assert.deepEqual(getOutboundStreamSecuritySelectValues('masque', 'none'), ['none', 'tls'])
  assert.deepEqual(getOutboundStreamSecuritySelectValues('masque', 'reality'), ['reality', 'tls'])
  assert.deepEqual(getOutboundStreamSecuritySelectValues('vless', 'none'), ['none', 'tls', 'reality'])
  assert.deepEqual(getOutboundStreamSecuritySelectValues('vmess', 'reality'), ['none', 'tls', 'reality'])
})

test('outboundStreamTransportName reads method before network', () => {
  assert.equal(outboundStreamTransportName({ method: 'XDrive', network: 'tcp' }), 'xdrive')
  assert.equal(outboundStreamTransportName({ network: ' WS ' }), 'ws')
  assert.equal(outboundStreamTransportName({ method: null, network: 'grpc' }), 'grpc')
  assert.equal(outboundStreamTransportName({ network: 5 }), '')
  assert.equal(outboundStreamTransportName(undefined), '')
  assert.equal(outboundStreamTransportName(null), '')
  // Xray reads any `method` string first (an empty one is an unknown transport), like the kit's validator.
  assert.equal(outboundStreamTransportName({ method: '', network: 'ws' }), '')
  assert.equal(outboundStreamTransportName({ method: 7, network: 'masque' }), 'masque')
})

test('applyOutboundStreamNetwork writes the key in use and drops stale blocks', () => {
  assert.deepEqual(applyOutboundStreamNetwork({ network: 'tcp', security: 'tls' }, 'xdrive'), {
    network: 'xdrive',
    security: 'tls',
    xdriveSettings: { service: 'Google Drive', remoteFolder: '', secrets: ['', '', ''] },
  })
  const kept = { service: 'local', remoteFolder: '/x' }
  assert.deepEqual(applyOutboundStreamNetwork({ network: 'tcp', xdriveSettings: kept }, 'xdrive'), { network: 'xdrive', xdriveSettings: kept })
  assert.deepEqual(applyOutboundStreamNetwork({ method: 'xdrive', security: 'none', xdriveSettings: kept }, 'ws'), { method: 'ws', security: 'none' })
  assert.deepEqual(applyOutboundStreamNetwork({ network: 'masque', masqueSettings: { path: '/p' } }, 'tcp'), { network: 'tcp' })
  assert.deepEqual(applyOutboundStreamNetwork({}, 'grpc'), { network: 'grpc' })
})

test('applyOutboundStreamNetwork leaves its input alone and replaces a non-record xdriveSettings', () => {
  const stream = { method: 'tcp', network: 'ws', xdriveSettings: 'broken' }
  assert.deepEqual(applyOutboundStreamNetwork(stream, 'xdrive'), {
    method: 'xdrive',
    network: 'ws',
    xdriveSettings: { service: 'Google Drive', remoteFolder: '', secrets: ['', '', ''] },
  })
  assert.deepEqual(stream, { method: 'tcp', network: 'ws', xdriveSettings: 'broken' })
  const masque = { network: 'masque', masqueSettings: { path: '/p' } }
  assert.deepEqual(applyOutboundStreamNetwork(masque, 'masque'), masque)
})

test('outboundWithStreamNetwork enables mux when entering xdrive', () => {
  assert.deepEqual(outboundWithStreamNetwork({ protocol: 'vless', tag: 'x', streamSettings: { network: 'tcp', security: 'tls' } }, 'xdrive'), {
    protocol: 'vless',
    tag: 'x',
    streamSettings: { network: 'xdrive', security: 'tls', xdriveSettings: { service: 'Google Drive', remoteFolder: '', secrets: ['', '', ''] } },
    mux: { enabled: true },
  })
  // Fields Xray accepts with xdrive stay; a negative concurrency and xudpProxyUDP443 "skip" go.
  const mux = { enabled: false, concurrency: 8, xudpConcurrency: -1, xudpProxyUDP443: 'skip' }
  assert.deepEqual(outboundWithStreamNetwork({ protocol: 'vless', mux }, 'xdrive').mux, { enabled: true, concurrency: 8 })
  assert.deepEqual(outboundWithStreamNetwork({ protocol: 'vless', mux: { concurrency: -1, xudpConcurrency: 16, xudpProxyUDP443: 'allow' } }, 'xdrive').mux, {
    enabled: true,
    xudpConcurrency: 16,
    xudpProxyUDP443: 'allow',
  })
  assert.deepEqual(outboundWithStreamNetwork({ protocol: 'vless', mux: 'broken' }, 'xdrive').mux, { enabled: true })
  assert.deepEqual(mux, { enabled: false, concurrency: 8, xudpConcurrency: -1, xudpProxyUDP443: 'skip' })
})

test('outboundWithStreamNetwork keeps mux as it is on other networks', () => {
  const plain = outboundWithStreamNetwork({ protocol: 'vless', streamSettings: { network: 'xdrive', xdriveSettings: { service: 'local' } }, mux: { enabled: true, concurrency: 4 } }, 'ws')
  assert.deepEqual(plain, { protocol: 'vless', streamSettings: { network: 'ws' }, mux: { enabled: true, concurrency: 4 } })
  const noMux = outboundWithStreamNetwork({ protocol: 'vmess' }, 'grpc')
  assert.deepEqual(noMux, { protocol: 'vmess', streamSettings: { network: 'grpc' } })
  assert.equal('mux' in noMux, false)
})

test('an outbound switched to xdrive passes the kit mux rule', () => {
  const vless = {
    protocol: 'vless',
    tag: 'xdrive-out',
    settings: { address: 'example.com', port: 443, id: '3f1d8d4c-0b8e-4f57-9a0e-2b7f4b0c9d11', encryption: 'mlkem768x25519plus.native.0rtt.abc' },
    streamSettings: { network: 'tcp', security: 'none' },
  }
  const muxIssues = (outbound: Record<string, unknown>) =>
    validateOutboundDraft(outbound as unknown as Outbound)
      .filter(issue => issue.code === 'XCK_SEMANTIC_XDRIVE_MUX_REQUIRED')
      .map(issue => issue.path)
  assert.notDeepEqual(muxIssues({ ...vless, streamSettings: applyOutboundStreamNetwork(vless.streamSettings, 'xdrive') }), [])
  assert.deepEqual(muxIssues(outboundWithStreamNetwork(vless, 'xdrive')), [])
  assert.deepEqual(muxIssues(outboundWithStreamNetwork({ ...vless, mux: { enabled: true, concurrency: -1, xudpProxyUDP443: 'skip' } }, 'xdrive')), [])
})

test('outboundStreamSettingsForProtocolSwitch', () => {
  const sockopt = { mark: 255 }
  const finalmask = { udp: [{ type: 'salamander', settings: { password: 'x' } }] }
  assert.deepEqual(
    outboundStreamSettingsForProtocolSwitch(
      { network: 'ws', security: 'tls', tlsSettings: { serverName: 'a.com', alpn: ['h2', 'http/1.1'] }, wsSettings: { path: '/w' }, sockopt, finalmask },
      'masque',
    ),
    { network: 'masque', security: 'tls', tlsSettings: { serverName: 'a.com' }, sockopt, finalmask },
  )
  assert.deepEqual(outboundStreamSettingsForProtocolSwitch({ network: 'tcp', security: 'reality', realitySettings: { serverName: 'a' } }, 'masque'), { network: 'masque', security: 'tls' })
  assert.deepEqual(outboundStreamSettingsForProtocolSwitch(undefined, 'masque'), { network: 'masque', security: 'tls' })
  assert.deepEqual(outboundStreamSettingsForProtocolSwitch({ network: 'masque', security: 'tls', tlsSettings: { serverName: 'a.com' }, masqueSettings: { path: '/p' }, sockopt }, 'vless'), {
    security: 'tls',
    tlsSettings: { serverName: 'a.com' },
    sockopt,
  })
  assert.equal(outboundStreamSettingsForProtocolSwitch({ network: 'masque' }, 'vless'), undefined)
  const plain = { network: 'ws', security: 'none' }
  assert.equal(outboundStreamSettingsForProtocolSwitch(plain, 'vless'), plain)
})

test('switching XDrive to a non-VLESS protocol drops its transport state', () => {
  const xdrive = { method: 'XDrive', network: 'tcp', security: 'tls', xdriveSettings: { service: 'local' }, sockopt: { mark: 1 } }
  assert.deepEqual(outboundStreamSettingsForProtocolSwitch(xdrive, 'trojan'), { security: 'tls', sockopt: { mark: 1 } })
  assert.deepEqual(xdrive.xdriveSettings, { service: 'local' })
  assert.equal(outboundStreamSettingsForProtocolSwitch({ network: 'xdrive' }, 'vmess'), undefined)
  assert.deepEqual(outboundStreamSettingsForProtocolSwitch({ network: 'ws', xdriveSettings: { service: 'local' }, wsSettings: { path: '/w' } }, 'trojan'), {
    wsSettings: { path: '/w' },
  })
  assert.equal(outboundStreamSettingsForProtocolSwitch(xdrive, 'vless'), xdrive)
  const plain = { network: 'ws', security: 'none' }
  assert.equal(outboundStreamSettingsForProtocolSwitch(plain, 'trojan'), plain)
})

test('outboundStreamSettingsForProtocolSwitch edge cases', () => {
  // Key order: network, security, tlsSettings, sockopt, finalmask.
  const toMasque = outboundStreamSettingsForProtocolSwitch({ finalmask: { tcp: [] }, sockopt: { mark: 1 }, tlsSettings: { serverName: 'a.com' }, security: 'tls', method: 'ws' }, 'masque')
  assert.deepEqual(Object.keys(toMasque ?? {}), ['network', 'security', 'tlsSettings', 'sockopt', 'finalmask'])
  // TLS settings with only ALPN, or TLS settings under another security, are not carried.
  assert.deepEqual(outboundStreamSettingsForProtocolSwitch({ network: 'tcp', security: 'tls', tlsSettings: { alpn: ['h2'] } }, 'masque'), { network: 'masque', security: 'tls' })
  assert.deepEqual(outboundStreamSettingsForProtocolSwitch({ network: 'tcp', security: 'none', tlsSettings: { serverName: 'a.com' } }, 'masque'), { network: 'masque', security: 'tls' })
  assert.deepEqual(outboundStreamSettingsForProtocolSwitch({ network: 'tcp', sockopt: 'broken', finalmask: [] }, 'masque'), { network: 'masque', security: 'tls' })
  // A method-keyed MASQUE stream, and a stale masqueSettings on another network, are both cleaned.
  assert.deepEqual(outboundStreamSettingsForProtocolSwitch({ method: 'MASQUE', network: 'tcp', security: 'tls' }, 'vmess'), { security: 'tls' })
  assert.deepEqual(outboundStreamSettingsForProtocolSwitch({ network: 'ws', masqueSettings: { path: '/p' }, wsSettings: { path: '/w' } }, 'trojan'), { wsSettings: { path: '/w' } })
  assert.deepEqual(outboundStreamSettingsForProtocolSwitch({ network: 'masque', masqueSettings: {}, xdriveSettings: {}, security: 'tls' }, 'vless'), { security: 'tls' })
})

test('switching away from MASQUE drops the HTTP version ALPN, like switching to it', () => {
  const sockopt = { mark: 255 }
  // The ALPN of a MASQUE stream is its HTTP version; another protocol would offer it as its own TLS ALPN.
  assert.deepEqual(
    outboundStreamSettingsForProtocolSwitch({ network: 'masque', security: 'tls', tlsSettings: { serverName: 'a.com', alpn: ['h3'] }, masqueSettings: { path: '/p' }, sockopt }, 'vless'),
    { security: 'tls', tlsSettings: { serverName: 'a.com' }, sockopt },
  )
  // TLS settings left empty are dropped, as on the way in.
  assert.deepEqual(outboundStreamSettingsForProtocolSwitch({ network: 'masque', security: 'tls', tlsSettings: { alpn: ['h3', 'h2'] } }, 'trojan'), { security: 'tls' })
  assert.equal(outboundStreamSettingsForProtocolSwitch({ method: 'masque', tlsSettings: { alpn: ['h2'] } }, 'vmess'), undefined)
  // A stale masqueSettings on another network leaves that network's ALPN alone.
  assert.deepEqual(outboundStreamSettingsForProtocolSwitch({ network: 'ws', security: 'tls', tlsSettings: { alpn: ['http/1.1'] }, masqueSettings: { path: '/p' } }, 'vless'), {
    security: 'tls',
    tlsSettings: { alpn: ['http/1.1'] },
  })
  // A TLS block that is not a record is left for the Advanced tab.
  assert.deepEqual(outboundStreamSettingsForProtocolSwitch({ network: 'masque', security: 'tls', tlsSettings: 'broken' }, 'vless'), { security: 'tls', tlsSettings: 'broken' })
})

test('switching to MASQUE drops mux (Xray v26.10.10 and older refuse it there)', () => {
  const mux = { enabled: true, concurrency: 8 }
  assert.equal(outboundMuxForProtocolSwitch(mux, 'masque'), undefined)
  assert.equal(outboundMuxForProtocolSwitch(mux, 'vless'), mux)
  assert.equal(outboundMuxForProtocolSwitch(undefined, 'vmess'), undefined)
})

test('a stored raw network uses the TCP settings blocks; other names stay as stored', () => {
  assert.equal(outboundStreamSectionNetwork('raw'), 'tcp')
  assert.equal(outboundStreamSectionNetwork('tcp'), 'tcp')
  for (const network of ['websocket', 'mkcp', 'splithttp', 'xdrive', 'masque', 'ws']) assert.equal(outboundStreamSectionNetwork(network), network)
  // raw counts as REALITY compatible like tcp. It is not one of the offered names, so a stored raw stays first as stored.
  assert.equal(outboundStreamNetworkCompatibleWithReality('raw'), true)
  assert.deepEqual(getOutboundStreamNetworkSelectValues('reality', 'raw', 'vless'), ['raw', 'tcp', 'grpc', 'xhttp', 'splithttp'])
})
