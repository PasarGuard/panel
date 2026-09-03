// Requires Playwright and its browser, or PLAYWRIGHT_CHANNEL=msedge/chrome.
// All API calls and external requests are mocked; no real account or backend is used.
const fs = require('node:fs')
const path = require('node:path')
const http = require('node:http')
const assert = require('node:assert/strict')
const { chromium } = require('playwright')
assert.ok(process.argv[2], 'Usage: node scripts/check-form-submissions.cjs <production-build-directory>')
const build = path.resolve(process.argv[2])
const admin = {
  id: 1,
  username: 'test-admin',
  status: 'active',
  is_sudo: true,
  role: { id: 1, name: 'Owner', is_owner: true, permissions: {} },
  used_traffic: 0,
  lifetime_used_traffic: 0,
  data_limit: 0,
  users_data_usage: 0,
  users_data_limit: 0,
  created_at: '2026-01-01T00:00:00Z',
}
const user = {
  id: 1,
  username: 'perf-test-user',
  status: 'active',
  admin,
  used_traffic: 1000,
  lifetime_used_traffic: 1000,
  data_limit: 1073741824,
  data_limit_reset_strategy: 'no_reset',
  expire: null,
  on_hold_timeout: null,
  on_hold_expire_duration: null,
  note: '',
  group_ids: [],
  proxy_settings: { trojan: { password: 'synthetic-test-only' } },
  subscription_url: '/sub/test',
  created_at: '2026-01-01T00:00:00Z',
  online_at: null,
  next_plan: null,
  hwid_limit: null,
}
const settings = {
  subscription: { rules: [], applications: [], custom_variables: [{ key: 'CUSTOM_HOST', value: 'old.example.invalid' }] },
  notification_enable: {},
  notification_settings: {
    notify_telegram: true,
    notify_discord: false,
    max_retries: 3,
    telegram_api_token: 'synthetic-test-only',
    telegram_chat_id: -100000,
    channels: { admin: { telegram_chat_id: -1001, telegram_topic_id: 5 } },
  },
}
const host = {
  id: 1,
  remark: 'Contract test host',
  address: ['example.invalid'],
  inbound_tag: 'test-inbound',
  status: [],
  security: 'inbound_default',
  priority: 0,
  noise_settings: { xray: [{ type: 'array', packet: [0, 1, 255], delay: 0, apply_to: 'ip' }] },
  transport_settings: {
    xhttp_settings: {
      mode: 'auto',
      uplink_chunk_size: '100-200',
      xmux: { maxConcurrency: '1-4', maxConnections: '2', cMaxReuseTimes: '3', hMaxReusableSecs: '4-8', hMaxRequestTimes: '5', hKeepAlivePeriod: 0 },
    },
  },
}
const writes = []
const mime = { '.js': 'application/javascript', '.css': 'text/css', '.html': 'text/html', '.json': 'application/json', '.svg': 'image/svg+xml', '.woff2': 'font/woff2' }
const server = http.createServer((req, res) => {
  const file = path.resolve(build, '.' + decodeURIComponent(new URL(req.url, 'http://local').pathname === '/' ? '/index.html' : new URL(req.url, 'http://local').pathname))
  if (!file.startsWith(build + path.sep)) {
    res.writeHead(403).end()
    return
  }
  fs.readFile(file, (err, bytes) => {
    res.writeHead(err ? 404 : 200, { 'content-type': mime[path.extname(file)] || 'application/octet-stream' })
    res.end(err ? 'not found' : bytes)
  })
})
;(async () => {
  await new Promise(r => server.listen(0, '127.0.0.1', r))
  const base = `http://127.0.0.1:${server.address().port}`
  const browser = await chromium.launch({ headless: true, channel: process.env.PLAYWRIGHT_CHANNEL || undefined })
  try {
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, locale: 'en-US' })
    await context.addInitScript(() => localStorage.setItem('i18nextLng', 'en'))
    const page = await context.newPage()
    const errors = []
    page.on('pageerror', e => errors.push(e.message))
    await page.route('**/*', async route => {
      const url = new URL(route.request().url())
      if (url.pathname.startsWith('/api/')) {
        let body = {}
        const p = url.pathname
        if (route.request().method() !== 'GET') {
          writes.push({ path: p, body: route.request().postDataJSON() })
        }
        if (p === '/api/settings') body = settings
        else if (p === '/api/hosts') body = [host, { ...structuredClone(host), id: 2, remark: 'Second test host', priority: 1 }]
        else if (p === '/api/inbounds/details') body = [{ tag: 'test-inbound', protocol: 'vless', network: 'xhttp' }]
        else if (p === '/api/admin') body = admin
        else if (p === '/api/users') body = { users: [user], total: 1 }
        else if (p === '/api/user/by-id/1') body = user
        else if (p === '/api/groups/simple') body = { groups: [], total: 0 }
        else if (p === '/api/admins/simple') body = { admins: [admin], total: 1 }
        else if (p === '/api/user_templates/simple') body = { templates: [], total: 0 }
        else if (p === '/api/nodes/simple') body = { nodes: [{ id: 1, name: 'Test node', status: 'connected' }], total: 1 }
        else if (p.includes('/usage'))
          body = {
            start: url.searchParams.get('start') || '2026-09-01',
            end: url.searchParams.get('end') || '2026-09-04',
            stats: { 1: [{ period_start: new Date().toISOString(), total_traffic: 1073741824 }] },
          }
        else if (p.includes('/system')) body = { version: '1.0.0', total_user: 1, active_users: 1, online_users: 0, mem_total: 100, mem_used: 20, cpu_usage: 0 }
        else if (p.includes('/hwids')) body = { hwids: [], total: 0 }
        else if (p.includes('/subscription/')) return route.fulfill({ status: 200, contentType: 'text/plain', body: 'trojan://synthetic@example.invalid:443#Test' })
        return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
      }
      if (url.origin !== base) return route.fulfill({ status: 200, contentType: 'application/json', body: '{}' })
      return route.continue()
    })
    const saveSettings = () =>
      Promise.all([page.waitForResponse(r => r.url().endsWith('/api/settings') && r.request().method() === 'PUT'), page.getByRole('button', { name: 'Save', exact: true }).click()])
    await page.goto(base + '/#/settings/subscriptions')
    const keys = page.getByPlaceholder('CUSTOM_HOST', { exact: true })
    await keys.waitFor()
    await keys.fill('custom_new')
    await page.getByPlaceholder('{USERNAME}.example.com', { exact: true }).fill('  new.example.invalid  ')
    await page.getByRole('button', { name: 'Add Variable', exact: true }).click()
    await keys.nth(1).fill('CUSTOM_NEW')
    await page.getByRole('button', { name: 'Save', exact: true }).click()
    await page.getByText('Duplicate custom variable key.', { exact: true }).first().waitFor()
    await keys.nth(1).fill('USERNAME')
    await page.getByRole('button', { name: 'Save', exact: true }).click()
    await page.getByText('This key is reserved for a built-in variable.', { exact: true }).waitFor()
    await keys.nth(1).fill('CUSTOM_EMPTY')
    await saveSettings()
    assert.equal(writes.length, 1, 'invalid subscription drafts must not be submitted')
    assert.deepEqual(writes.at(-1).body.subscription.custom_variables, [
      { key: 'CUSTOM_NEW', value: 'new.example.invalid' },
      { key: 'CUSTOM_EMPTY', value: '' },
    ])
    console.log('PASS subscription add/edit, duplicate/reserved validation, normalized save')

    await page.goto(base + '/#/settings/notifications')
    await page.getByRole('switch', { name: 'Admins0/6', exact: true }).click()
    await page.getByText('Channel Overrides', { exact: true }).click()
    await page.locator('input[name="notification_settings.channels.admin.telegram_chat_id"]').fill('-100222')
    await page.locator('input[name="notification_settings.channels.admin.telegram_topic_id"]').fill('0')
    await page.getByRole('combobox').click()
    await page.getByRole('option', { name: 'Nodes', exact: true }).click()
    await page.locator('input[name="notification_settings.channels.node.telegram_chat_id"]').fill('-100333')
    await page.locator('input[name="notification_settings.channels.node.telegram_topic_id"]').fill('17')
    await saveSettings()
    const notification = writes.at(-1).body
    assert.equal(notification.notification_enable.admin.create, true)
    assert.equal(notification.notification_settings.channels.admin.telegram_chat_id, -100222)
    assert.equal(notification.notification_settings.channels.admin.telegram_topic_id, 0)
    assert.equal(notification.notification_settings.channels.node.telegram_chat_id, -100333)
    assert.equal(notification.notification_settings.channels.node.telegram_topic_id, 17)
    assert.deepEqual(Object.keys(notification.notification_settings.channels).sort(), ['admin', 'admin_role', 'core', 'group', 'host', 'node', 'user', 'user_template'])
    console.log('PASS notification toggle and channel switching/save')

    await page.goto(base + '/#/hosts')
    await page.getByText('Contract test host', { exact: true }).first().click()
    const dialog = page.getByRole('dialog')
    await dialog.waitFor()
    await dialog.getByRole('button', { name: 'Transport Settings', exact: true }).click()
    const chunkSize = dialog.locator('input[name="transport_settings.xhttp_settings.uplink_chunk_size"]')
    assert.equal(await chunkSize.inputValue(), '100-200')
    await chunkSize.fill('100-')
    await dialog.getByRole('button', { name: 'Modify', exact: true }).click()
    await dialog.getByText("Uplink Chunk Size must be in format like '10-20' or '10'", { exact: true }).waitFor()
    assert.equal(writes.length, 2)
    await chunkSize.fill('300-400')
    await Promise.all([page.waitForResponse(r => r.url().includes('/api/host/') && r.request().method() === 'PUT'), dialog.getByRole('button', { name: 'Modify', exact: true }).click()])
    const payload = writes.at(-1).body
    assert.equal(payload.transport_settings.xhttp_settings.uplink_chunk_size, '300-400')
    assert.deepEqual(payload.transport_settings.xhttp_settings.xmux, host.transport_settings.xhttp_settings.xmux)
    assert.deepEqual(payload.noise_settings, host.noise_settings)
    console.log('PASS host range edit/validation and save preserving XMux, array noise and zero delay')
    await page.goto(base + '/#/hosts')
    const handles = page.getByRole('button', { name: 'Drag to reorder', exact: true })
    await handles.nth(1).waitFor()
    const source = await handles.nth(0).boundingBox()
    const destination = await handles.nth(1).boundingBox()
    await page.mouse.move(source.x + source.width / 2, source.y + source.height / 2)
    await page.mouse.down()
    await page.mouse.move(destination.x + destination.width / 2, destination.y + destination.height / 2, { steps: 15 })
    await Promise.all([page.waitForResponse(r => r.url().endsWith('/api/hosts') && r.request().method() === 'PUT'), page.mouse.up()])
    const reordered = writes.at(-1).body
    assert.deepEqual(
      reordered.map(item => item.id),
      [2, 1],
    )
    for (const item of reordered) {
      assert.equal(item.transport_settings.xhttp_settings.uplink_chunk_size, '100-200')
      assert.deepEqual(item.transport_settings.xhttp_settings.xmux, host.transport_settings.xhttp_settings.xmux)
      assert.deepEqual(item.noise_settings, host.noise_settings)
    }
    console.log('PASS host reorder preserves API transport/noise values')
    assert.deepEqual(errors, [])
  } finally {
    await browser.close()
    server.close()
  }
})().catch(e => {
  console.error(e)
  server.close()
  process.exitCode = 1
})
