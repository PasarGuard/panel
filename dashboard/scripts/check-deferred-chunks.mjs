// Build with `vite build --manifest --outDir <fresh-directory>`, then run:
// node scripts/check-deferred-chunks.mjs <directory> [--report-only]
// Measures JS dependency sets, not CSS or network latency. The final scenario
// includes the dashboard's existing deferred chart as well as its static imports.
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { gzipSync } from 'node:zlib'
import { runInNewContext } from 'node:vm'

const directory = resolve(process.argv[2] || 'build')
const reportOnly = process.argv.includes('--report-only')
const manifest = JSON.parse(readFileSync(resolve(directory, '.vite/manifest.json'), 'utf8'))
const dialogs = ['src/features/users/dialogs/user-modal.tsx', 'src/features/users/dialogs/usage-modal.tsx', 'src/features/subscriptions/dialogs/subscription-modal.tsx']

function staticDependencies(roots) {
  const visited = new Set()
  function visit(key) {
    if (visited.has(key)) return
    assert(manifest[key], `Missing manifest entry: ${key}`)
    visited.add(key)
    for (const dependency of manifest[key].imports || []) visit(dependency)
  }
  roots.forEach(visit)
  return [...visited]
}

const scenarios = {
  shell: ['index.html'],
  dashboard: ['index.html', 'src/pages/_dashboard.tsx', 'src/pages/_dashboard._index.tsx'],
  users: ['index.html', 'src/pages/_dashboard.tsx', 'src/pages/_dashboard.users.tsx'],
  dashboardWithChart: ['index.html', 'src/pages/_dashboard.tsx', 'src/pages/_dashboard._index.tsx', 'src/features/dashboard/components/data-usage-chart.tsx'],
}
const results = {}
for (const [name, roots] of Object.entries(scenarios)) {
  const dependencies = staticDependencies(roots)
  const files = [...new Set(dependencies.map(key => manifest[key].file))]
  const chunks = files.map(file => readFileSync(resolve(directory, file)))
  results[name] = {
    jsFiles: files.length,
    bytes: chunks.reduce((total, chunk) => total + chunk.length, 0),
    gzipBytes: chunks.reduce((total, chunk) => total + gzipSync(chunk).length, 0),
  }
  if (!reportOnly) {
    for (const dialog of dialogs) {
      assert(manifest[dialog]?.isDynamicEntry, `${dialog} must remain a dynamic entry`)
      assert(!dependencies.includes(dialog), `${name} eagerly imports ${dialog}`)
    }
    // This DOM class lives in Recharts' chart renderer (not our chart icon).
    if (name !== 'dashboardWithChart') {
      assert(!chunks.some(chunk => chunk.includes('recharts-wrapper')), `${name} eagerly loads the chart renderer`)
    }
  }
}

// Editing a user should not download the usage chart until its own dialog opens.
if (!reportOnly) {
  const editDependencies = staticDependencies([dialogs[0]])
  assert(!editDependencies.includes(dialogs[1]), 'User editor eagerly imports the usage dialog')
  assert(!editDependencies.some(key => readFileSync(resolve(directory, manifest[key].file)).includes('recharts-wrapper')), 'User editor eagerly loads the chart renderer')
}
console.log(JSON.stringify(results, null, 2))
if (!reportOnly) console.log('Deferred dialog and chart boundaries passed.')

// Read the generated precache with a stubbed Workbox module; no worker is installed.
let precache
const define = (_dependencies, factory) =>
  factory({
    precacheAndRoute: entries => {
      precache = entries
    },
    registerRoute() {},
    createHandlerBoundToURL() {},
    NavigationRoute: class {},
    CacheFirst: class {},
    CacheableResponsePlugin: class {},
    ExpirationPlugin: class {},
  })
runInNewContext(readFileSync(resolve(directory, 'sw.js'), 'utf8'), { self: { define, addEventListener() {} }, define })
assert(precache, 'Generated service worker has no precache')
const precachedJavaScript = precache.map(entry => entry.url).filter(url => url.endsWith('.js'))
const shellFiles = staticDependencies(['index.html'])
  .map(key => manifest[key].file)
  .filter(file => file.endsWith('.js'))
console.log(JSON.stringify({ precacheEntries: precache.length, precachedJavaScript: precachedJavaScript.length }))
if (!reportOnly) {
  assert.deepEqual([...precachedJavaScript].sort(), shellFiles.sort(), 'Precache must contain exactly the shell JavaScript dependency set')
  assert(
    precache.some(entry => entry.url === 'index.html'),
    'HTML shell is not precached',
  )
  assert(
    precache.some(entry => entry.url.endsWith('.css')),
    'Shell CSS is not precached',
  )
  console.log('Passed: service worker precaches shell JavaScript only, plus HTML and CSS.')
}
