import { afterAll, describe, expect, it, mock } from 'bun:test'

mock.module('../src/utils/authStorage', () => ({ getAuthToken: () => null }))
mock.module('../src/utils/dateFormatter', () => ({ dateUtils: { getSystemTimeZone: () => 'UTC' } }))
const { orvalFetcher } = await import('../src/service/http')

const server = Bun.serve({
  hostname: '127.0.0.1',
  port: 0,
  async fetch(request) {
    if (new URL(request.url).pathname === '/slow') await Bun.sleep(250)
    if (new URL(request.url).pathname === '/redirect') return Response.redirect(new URL('/admin', request.url), 302)
    return Response.json({ username: 'test', timezone: request.headers.get('X-Client-Timezone') })
  },
})
afterAll(() => server.stop(true))

describe('generated API mutator contract', () => {
  it('returns the body, not an HTTP response wrapper', async () => {
    const result = await orvalFetcher<{ username: string; timezone: string }>(new URL('/admin', server.url).href)
    expect(result).toEqual({ username: 'test', timezone: 'UTC' })
  })

  it('forwards abort signals to the HTTP request', async () => {
    const controller = new AbortController()
    const request = orvalFetcher(new URL('/slow', server.url).href, { signal: controller.signal })
    controller.abort()
    await expect(request).rejects.toThrow()
  })
})

// An explicit redirect policy must survive the generated API mutator.
it('preserves RequestInit redirect policy', async () => {
  await expect(orvalFetcher(new URL('/redirect', server.url).href, { redirect: 'error' })).rejects.toThrow()
})
