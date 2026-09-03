// Requires Playwright: node scripts/check-deferred-dialogs.cjs <build-directory>
// Set PLAYWRIGHT_CHANNEL=msedge (or chrome) to use an installed browser.
// Serves only the local build; all API and external requests use synthetic responses.
const fs = require('node:fs')
const path = require('node:path')
const http = require('node:http')
const { chromium } = require('playwright')
const assert = require('node:assert/strict')
const build = path.resolve(process.argv[2])
const manifest = JSON.parse(fs.readFileSync(path.join(build, '.vite/manifest.json')))
const dialogFile = name => manifest[`src/features/${name === 'subscription' ? 'subscriptions' : 'users'}/dialogs/${name}-modal.tsx`].file
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
    const requests = []
    page.on('pageerror', e => errors.push(e.message))
    page.on('request', r => requests.push(r.url()))
    await page.route('**/*', async route => {
      const url = new URL(route.request().url())
      if (url.pathname.startsWith('/api/')) {
        let body = {}
        const p = url.pathname
        if (p === '/api/admin') body = admin
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
    await page.goto(base + '/#/users')
    await page.getByText('perf-test-user', { exact: true }).first().waitFor()

    const countLoads = name => requests.filter(url => url.endsWith('/' + dialogFile(name))).length
    for (const name of ['user', 'usage', 'subscription']) assert.equal(countLoads(name), 0, `${name} loaded while closed`)
    const chartFiles = Object.values(manifest)
      .map(entry => entry.file)
      .filter(file => file.endsWith('.js') && fs.readFileSync(path.join(build, file)).includes('recharts-wrapper'))
    const chartLoaded = () => requests.some(url => chartFiles.some(file => url.endsWith('/' + file)))
    assert(chartFiles.length > 0)
    assert(!chartLoaded(), 'Users page loaded Recharts')

    // Hold the first dialog chunk: the page stays mounted and loading can be cancelled.
    let releaseChunk
    const chunkGate = new Promise(resolve => {
      releaseChunk = resolve
    })
    await page.route('**/' + dialogFile('user'), async route => {
      await chunkGate
      await route.fallback()
    })
    const createButton = page.getByRole('button', { name: 'Create User', exact: true })
    await createButton.click()
    await page.getByRole('dialog').getByRole('status').waitFor()
    assert(await page.getByText('perf-test-user', { exact: true }).first().isVisible(), 'Suspension hid the users page')
    await page.getByRole('dialog').getByRole('button', { name: 'Close', exact: true }).click()
    await page.getByRole('dialog').waitFor({ state: 'hidden' })
    const downloaded = page.waitForResponse(response => response.url().endsWith('/' + dialogFile('user')))
    releaseChunk()
    await downloaded
    assert.equal(await page.getByRole('dialog').count(), 0, 'Cancelled dialog reopened after loading')
    await createButton.click()
    await page.getByRole('dialog', { name: 'Create User', exact: true }).getByRole('textbox', { name: 'Enter username', exact: true }).waitFor()
    assert.equal(countLoads('user'), 1)
    assert(!chartLoaded(), 'Create form loaded Recharts')
    await page.getByRole('dialog').getByRole('button', { name: 'Cancel', exact: true }).click()
    await page.getByRole('dialog').waitFor({ state: 'hidden' })

    // The existing user and form values still reach the deferred editor.
    await page.getByText('perf-test-user', { exact: true }).first().click()
    const editDialog = page.getByRole('dialog', { name: 'Modify user', exact: true })
    await editDialog.getByRole('textbox', { name: 'Data Limit', exact: true }).waitFor()
    assert.equal(await editDialog.getByRole('textbox', { name: 'Enter username', exact: true }).inputValue(), user.username)
    assert.equal(await editDialog.getByRole('textbox', { name: 'Data Limit', exact: true }).inputValue(), '1')
    assert(!chartLoaded(), 'Edit form loaded Recharts')
    await editDialog.getByRole('button', { name: 'Close', exact: true }).click()
    await editDialog.waitFor({ state: 'hidden' })

    // Open from the global row-action host, close, and reopen without another chunk download.
    const row = page.getByRole('row').filter({ hasText: user.username })
    const openUsage = async () => {
      await row.getByRole('button').last().click()
      await page.getByRole('menuitem', { name: 'Usage', exact: true }).click()
      await page.getByRole('dialog', { name: 'Usage Chart', exact: true }).locator('.recharts-wrapper').waitFor()
    }
    await openUsage()
    assert(chartLoaded(), 'Usage did not load the chart renderer')
    assert.equal(countLoads('usage'), 1)
    await page.getByRole('dialog').getByRole('button', { name: 'Close', exact: true }).click()
    await page.getByRole('dialog').waitFor({ state: 'hidden' })
    await openUsage()
    assert.equal(countLoads('usage'), 1)
    await page.getByRole('dialog').getByRole('button', { name: 'Close', exact: true }).click()
    await page.getByRole('dialog').waitFor({ state: 'hidden' })

    await row.getByRole('button', { name: 'QR Code', exact: true }).click()
    const subscription = page.getByRole('dialog').filter({ has: page.locator('canvas') })
    await subscription.waitFor()
    assert.equal(countLoads('subscription'), 1)
    await subscription.getByRole('button', { name: 'Close', exact: true }).click()
    await subscription.waitFor({ state: 'hidden' })
    await row.getByRole('button', { name: 'QR Code', exact: true }).click()
    await subscription.waitFor()
    assert.equal(countLoads('subscription'), 1)
    await subscription.getByRole('button', { name: 'Close', exact: true }).click()
    await subscription.waitFor({ state: 'hidden' })
    assert.deepEqual(errors, [], 'Browser runtime errors')
    console.log('Passed: closed dialogs and charts deferred; cancel while loading; create/edit values; usage chart; subscription QR; close/reopen without downloading again.')

    // Revisit at a narrow viewport to cover the shared create dialog on mobile.
    await page.setViewportSize({ width: 390, height: 844 })
    await page.reload()
    await page.getByText(user.username, { exact: true }).first().waitFor()
    await page.getByRole('button', { name: 'Create User', exact: true }).click()
    await page.getByRole('dialog', { name: 'Create User', exact: true }).getByRole('textbox', { name: 'Enter username', exact: true }).waitFor()
    await page.getByRole('dialog').getByRole('button', { name: 'Cancel', exact: true }).click()
    await page.getByRole('dialog').waitFor({ state: 'hidden' })
    assert.deepEqual(errors, [], 'Mobile runtime errors')
    console.log('Passed: mobile create and cancel.')

    // Automatic chunking also changes the shell: exercise the login and dashboard routes.
    await page.goto(base + '/#/')
    await page.getByRole('heading', { name: 'Dashboard', exact: true }).waitFor()
    await page.locator('.recharts-wrapper').first().waitFor()
    await page.goto(base + '/#/login')
    await page.getByPlaceholder('Username', { exact: true }).waitFor()
    await page.getByPlaceholder('Password', { exact: true }).waitFor()
    assert.deepEqual(errors, [], 'Shell route runtime errors')
    console.log('Passed: dashboard chart and login routes.')
  } finally {
    await browser.close()
    server.close()
  }
})().catch(e => {
  console.error(e)
  server.close()
  process.exitCode = 1
})
