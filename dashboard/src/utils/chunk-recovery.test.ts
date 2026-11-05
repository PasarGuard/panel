import { test } from 'node:test'
import assert from 'node:assert/strict'

import { importWithChunkRecovery, installChunkLoadRecovery, isChunkLoadError } from './chunk-recovery.ts'

// What Chromium, Firefox and Safari report for a chunk that cannot be fetched, and what Vite's preload
// helper reports for a stylesheet it cannot load.
const staleChunkErrors = [
  new TypeError('Failed to fetch dynamically imported module: https://panel.example/statics/login-Abc123.js'),
  new TypeError('error loading dynamically imported module: https://panel.example/statics/login-Abc123.js'),
  new TypeError('Importing a module script failed.'),
  new Error('Unable to preload CSS for /statics/editor-Abc123.css'),
]

// The error Safari 15 gives for a class static block.
const parseError = new SyntaxError("Unexpected token '{'. Expected an opening '(' before a method's parameter list.")

const tick = () => new Promise(resolve => setTimeout(resolve, 0))

// Reports a failed import the way Vite's preload helper does: if a vite:preloadError listener calls
// preventDefault(), the import resolves with undefined. Otherwise it rejects with the original error.
function vitePreload<T>(load: () => Promise<T>): Promise<T | undefined> {
  return load().catch((error: unknown) => {
    const event = new Event('vite:preloadError', { cancelable: true }) as Event & { payload?: unknown }
    event.payload = error
    window.dispatchEvent(event)
    if (!event.defaultPrevented) throw error
    return undefined
  })
}

async function settlesWithin(promise: Promise<unknown>, ms = 20): Promise<boolean> {
  const settled = promise.then(
    () => true,
    () => true,
  )
  return Promise.race([settled, new Promise<boolean>(resolve => setTimeout(() => resolve(false), ms))])
}

async function withBrowser(run: (reloads: () => number) => Promise<void>) {
  const previous = Object.getOwnPropertyDescriptor(globalThis, 'window')
  const storage = new Map<string, string>()
  let reloads = 0
  const fakeWindow = Object.assign(new EventTarget(), {
    sessionStorage: {
      getItem: (key: string) => storage.get(key) ?? null,
      setItem: (key: string, value: string) => {
        storage.set(key, value)
      },
    },
    location: {
      reload: () => {
        reloads += 1
      },
    },
  })
  Object.defineProperty(globalThis, 'window', { configurable: true, value: fakeWindow })
  try {
    installChunkLoadRecovery()
    await run(() => reloads)
  } finally {
    if (previous) Object.defineProperty(globalThis, 'window', previous)
    else Reflect.deleteProperty(globalThis, 'window')
  }
}

test('stale chunk errors are recognized, errors from the module code are not', () => {
  for (const error of staleChunkErrors) assert.equal(isChunkLoadError(error), true, error.message)
  assert.equal(isChunkLoadError(parseError), false)
  assert.equal(isChunkLoadError(new TypeError("Cannot read properties of undefined (reading 'map')")), false)
})

test('an import that fails for another reason rejects with its own error and does not reload', async () => {
  await withBrowser(async reloads => {
    // This used to resolve with undefined. React.lazy then crashed with "Cannot read properties of
    // undefined (reading 'default')", and Safari showed "undefined is not an object (evaluating 'e._result.default')".
    await assert.rejects(
      importWithChunkRecovery(() => vitePreload(() => Promise.reject(parseError))),
      error => error === parseError,
    )
    await tick()
    assert.equal(reloads(), 0)
  })
})

test('a stale chunk reloads the page once and keeps the route suspended until then', async () => {
  for (const error of staleChunkErrors) {
    await withBrowser(async reloads => {
      const route = importWithChunkRecovery(() => vitePreload(() => Promise.reject(error)))
      assert.equal(await settlesWithin(route), false, error.message)
      assert.equal(reloads(), 1, error.message)
    })
  }
})

test('a stale chunk error repeated within the reload window surfaces instead of reloading again', async () => {
  await withBrowser(async reloads => {
    const error = new TypeError('Importing a module script failed.')
    void importWithChunkRecovery(() => vitePreload(() => Promise.reject(error)))
    await tick()
    await assert.rejects(
      importWithChunkRecovery(() => vitePreload(() => Promise.reject(error))),
      rejected => rejected === error,
    )
    assert.equal(reloads(), 1)
  })
})

test('a module that loads is returned unchanged', async () => {
  await withBrowser(async reloads => {
    const module = { default: () => null }
    assert.equal(await importWithChunkRecovery(() => vitePreload(() => Promise.resolve(module))), module)
    assert.equal(reloads(), 0)
  })
})
